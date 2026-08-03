"""Guardian v2 — deterministic CPU intent gate (no LLM).

Spec: Continue/Dev-Tests-External/theory/intent.txt
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from lib.paths import FOUNDATION_ROOT
from lib.security_membrane import ingress_gate
from lib.rid_telemetry import DORMANCY_THRESHOLD

DEFAULT_TARIFF = FOUNDATION_ROOT / "artifacts" / "auto" / "guardian_tariff.json"

PHYSICAL_TOKENS = ("temp_", "gpio", "motor", "pid_", "freq")
INFO_TOKENS = ("carma_", "write_file", "read_file", ".json", ".txt", ".jsonl")
ACTION_TOKENS = ("run", "exec", "execute", "delete", "rm", "patch", "eval", "tool", "dispatch")

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*|\[[^\]]*\]|>[^<]*<|\{[^}]*\}|\([^)]*\)")


@dataclass
class VectorFlags:
    physical: bool = False
    informational: bool = False
    action: bool = False
    depths: dict[str, int] = field(default_factory=dict)
    tokens: list[str] = field(default_factory=list)


@dataclass
class GuardianVerdict:
    allowed: bool
    stage: str
    s_n: float
    ltp: float
    demand_d_n: float
    dormant: bool
    vectors: VectorFlags
    sanctuary_triggered: bool
    sanctuary_reason: str
    flagged_tokens: list[str]
    normalized: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["vectors"] = asdict(self.vectors)
        return data


def load_tariff(path: Path | None = None) -> dict[str, Any]:
    src = path or DEFAULT_TARIFF
    if not src.is_file():
        return {"base_demand": 1.0, "hardware_capacity": 100.0, "penalty_weight": {}}
    return json.loads(src.read_text(encoding="utf-8"))


def _token_depth(token: str) -> int:
    return max(token.count("["), token.count("{"), token.count("("))


def _classify_token(token: str) -> tuple[str, ...]:
    low = token.lower()
    hits: list[str] = []
    if any(k in low for k in PHYSICAL_TOKENS):
        hits.append("physical")
    if any(k in low for k in INFO_TOKENS):
        hits.append("informational")
    if any(k in low for k in ACTION_TOKENS):
        hits.append("action")
    return tuple(hits)


def normalize_input(text: str) -> str:
    """Strip noise; attempt UML verify on bracket expressions."""
    from lib.uml_engine import evaluate, strip_comments

    raw = strip_comments(text.strip())
    parts = TOKEN_RE.findall(raw)
    normalized_parts: list[str] = []
    for part in parts:
        if part.startswith("[") or part.startswith("(") or part.startswith("{"):
            try:
                val, _, _, _ = evaluate(part)
                normalized_parts.append(f"uml:{part}={val}")
            except Exception:
                normalized_parts.append(part)
        else:
            normalized_parts.append(part)
    return " ".join(normalized_parts) if normalized_parts else raw


def classify_vectors(text: str) -> VectorFlags:
    flags = VectorFlags()
    tokens = TOKEN_RE.findall(text)
    flags.tokens = tokens
    for token in tokens:
        for kind in _classify_token(token):
            flags.depths[kind] = max(flags.depths.get(kind, 0), _token_depth(token))
            if kind == "physical":
                flags.physical = True
            elif kind == "informational":
                flags.informational = True
            elif kind == "action":
                flags.action = True
    return flags


def check_sanctuary(text: str, vectors: VectorFlags) -> tuple[bool, str]:
    channel_count = sum((vectors.physical, vectors.informational, vectors.action))
    if channel_count == 0 and text.strip():
        return True, "zero_channels_flagged"
    if vectors.physical and vectors.action:
        pd, ad = vectors.depths.get("physical", 0), vectors.depths.get("action", 0)
        if ad < pd:
            return True, "action_not_outermost"
    try:
        normalize_input(text)
    except (SyntaxError, NameError) as ex:
        return True, f"parse_error:{type(ex).__name__}"
    except Exception as ex:
        return True, f"normalize_error:{type(ex).__name__}"
    return False, ""


def tariff_demand(text: str, tariff: dict[str, Any]) -> tuple[float, list[str]]:
    weights: dict[str, float] = tariff.get("penalty_weight") or {}
    base = float(tariff.get("base_demand", 1.0))
    flagged: list[str] = []
    total = base
    low = text.lower()
    for token, weight in weights.items():
        if token in low:
            flagged.append(token)
            total += float(weight)
    return total, flagged


def compute_ltp(hardware_capacity: float, demand_d_n: float) -> float:
    if demand_d_n <= 0:
        return 0.0
    return min(1.0, hardware_capacity / demand_d_n)


def evaluate_guardian(
    text: str,
    *,
    s_n: float = 1.0,
    tariff_path: Path | None = None,
) -> GuardianVerdict:
    rust_in = ingress_gate(text, s_n)
    if not rust_in.get("allowed"):
        return GuardianVerdict(
            allowed=False,
            stage=str(rust_in.get("stage", "security_in")),
            s_n=s_n,
            ltp=0.0,
            demand_d_n=0.0,
            dormant=s_n < DORMANCY_THRESHOLD,
            vectors=VectorFlags(),
            sanctuary_triggered=False,
            sanctuary_reason="",
            flagged_tokens=[],
            normalized=text,
            message=str(rust_in.get("reason", "SECURITY IN blocked")),
        )

    tariff = load_tariff(tariff_path)
    normalized = normalize_input(text)
    vectors = classify_vectors(normalized)
    sanctuary, sanctuary_reason = check_sanctuary(text, vectors)
    demand, flagged = tariff_demand(normalized, tariff)
    hw_cap = float(tariff.get("hardware_capacity", 100.0))
    ltp = compute_ltp(hw_cap, demand)
    dormant = s_n < DORMANCY_THRESHOLD

    if sanctuary:
        return GuardianVerdict(
            allowed=False,
            stage="linguistic_sanctuary",
            s_n=s_n,
            ltp=ltp,
            demand_d_n=demand,
            dormant=dormant,
            vectors=vectors,
            sanctuary_triggered=True,
            sanctuary_reason=sanctuary_reason,
            flagged_tokens=flagged,
            normalized=normalized,
            message=f"SANCTUARY: {sanctuary_reason}",
        )
    if dormant:
        return GuardianVerdict(
            allowed=False,
            stage="soft_oblivion",
            s_n=s_n,
            ltp=ltp,
            demand_d_n=demand,
            dormant=True,
            vectors=vectors,
            sanctuary_triggered=False,
            sanctuary_reason="",
            flagged_tokens=flagged,
            normalized=normalized,
            message=f"DORMANT: S_n {s_n:.4f} below {DORMANCY_THRESHOLD}",
        )
    if ltp < 0.45:
        return GuardianVerdict(
            allowed=False,
            stage="tariff_interlock",
            s_n=s_n,
            ltp=ltp,
            demand_d_n=demand,
            dormant=False,
            vectors=vectors,
            sanctuary_triggered=False,
            sanctuary_reason="",
            flagged_tokens=flagged,
            normalized=normalized,
            message=f"BLOCKED: LTP {ltp:.4f} after tariff demand {demand:.2f}",
        )
    return GuardianVerdict(
        allowed=True,
        stage="cleared",
        s_n=s_n,
        ltp=ltp,
        demand_d_n=demand,
        dormant=False,
        vectors=vectors,
        sanctuary_triggered=False,
        sanctuary_reason="",
        flagged_tokens=flagged,
        normalized=normalized,
        message="CLEARED: classification and stability gates passed",
    )
