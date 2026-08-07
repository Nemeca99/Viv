#!/usr/bin/env python3
"""UML equation registry: Universal Machine Language + Universal Mathematical Language.

Enigma-style encode/decode between characters (machine indices) and Nested-PEMDAS
equations (math forms). Canonical form = most efficient (lowest symbolic_cost).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Sequence

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib import uml_engine  # noqa: E402

SCHEMA_VERSION = "uml_equation_registry_v1.2"
GENERATOR_ID = "nested_pemdas_equivalents_v1_2"
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
SANDBOX96_ARTIFACT = DEFAULT_DATA_DIR / "uml_registry_v1_sandbox96.json"
DEFAULT_EQUIVALENTS_LIMIT = 16


def _approx_eq(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(float(a) - float(b)) <= tol


def _eval_value(expr: str) -> float:
    value, _node, _notation, _trace = uml_engine.evaluate(expr)
    if isinstance(value, complex):
        if abs(value.imag) > 1e-12:
            raise ValueError(f"uml_registry_complex_unsupported:{expr}")
        return float(value.real)
    return float(value)


def _domains_in_expr_raw(expr: str) -> frozenset[str]:
    """Surface-op domain tag (no guarded cancel)."""
    found: set[str] = set()
    text = str(expr)
    if "**" in text:
        found.add("M")
        text = text.replace("**", " ")
    for op, dom in (("+", "A"), ("-", "S"), ("*", "M"), ("/", "D")):
        if op in text:
            found.add(dom)
    return frozenset(found)


def _domains_in_expr(expr: str) -> frozenset[str]:
    """Tag A/S/M/D domains for federation labels.

    When guarded U cancel is enabled (default), cancelable MD drag such as
    (V*K)/K is subtracted before federation tagging so it does not count as
    U_MD demand. Non-MD surface tags (including **) are unchanged.
    """
    from lib.uml_guarded_canonicalize import federation_domains_for, is_enabled

    raw = _domains_in_expr_raw(expr)
    if not is_enabled() or raw != frozenset({"M", "D"}):
        return raw
    return federation_domains_for(expr)


def _symbolic_cost(expr: str) -> int:
    return int(uml_engine.uml_cost(expr)["symbolic_cost"])


def _candidate_forms(value: int) -> list[str]:
    """Bounded deterministic Nested-PEMDAS equations equal to ``value``.

    v1.1 grows equivalent diversity for learning; canonical still prefers
    lowest symbolic_cost (often the literal integer).
    """
    v = int(value)
    forms: list[str] = [
        f"{v}",
        f"(({v}))",
        f"{v}+0",
        f"0+{v}",
        f"{v}-0",
        f"{v}*1",
        f"1*{v}",
        f"{v}/1",
        f"{v}**1",
    ]

    # Neighbor cancel / shift identities (bounded k).
    for k in range(1, 9):
        forms.append(f"({v}+{k})-{k}")
        forms.append(f"{v + k}-{k}")
        if v >= k:
            forms.append(f"({v}-{k})+{k}")
            forms.append(f"{v - k}+{k}")

    # Additive partitions.
    for a in range(1, min(12, max(v, 0)) + 1):
        b = v - a
        if b < 0:
            continue
        forms.append(f"{a}+{b}")
        forms.append(f"({a}+{b})")
        forms.append(f"{b}+{a}")

    # Factorizations. Do NOT emit pure scale-cancel drag ((V*K)/K): guarded U
    # cancel subtracts those at federation time; training banks should not
    # manufacture the waste (Saint-Exupéry / PASS_SUBTRACT_MD_DRAG).
    if v != 0:
        forms.extend(
            [
                f"({v}+{v})-{v}",
            ]
        )
        limit = abs(v)
        for d in range(2, min(limit, 24) + 1):
            if v % d == 0:
                q = v // d
                forms.append(f"{d}*{q}")
                forms.append(f"{q}*{d}")
                forms.append(f"({d}*{q})")
                forms.append(f"({v}/{d})*{d}")
                forms.append(f"({d}*{q})+0")

    if v == 0:
        forms.extend(
            [
                "0*1",
                "1*0",
                "1-1",
                "2-2",
                "0+0",
                "0/1",
                "0**1",
                "(1-1)*5",
                "(2*3)-6",
            ]
        )
    if v == 1:
        forms.extend(
            [
                "1*1",
                "1/1",
                "2-1",
                "0+1",
                "3-2",
                "4/4",
                "2**0",
                "(3*1)-2",
            ]
        )
    if v == 2:
        forms.extend(["1+1", "4/2", "3-1", "2**1", "(1*4)/2"])

    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for form in forms:
        if form not in seen:
            seen.add(form)
            out.append(form)
    return out


def _efficiency_key(expr: str) -> tuple[int, int, str]:
    return (_symbolic_cost(expr), len(expr), expr)


def pick_canonical(
    value: int,
    *,
    equivalents_limit: int = DEFAULT_EQUIVALENTS_LIMIT,
    federation_diversity_slots: int | None = None,
) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Return (canonical, equivalents, scored_candidates) for integer token value.

    Canonical remains lowest symbolic_cost. Equivalents are mostly cost-ordered,
    with reserved slots for mixed-domain federations (AS/AM/…) when present in
    the candidate generator — so the prepared bank can train composition, not
    only monolithic cheap routes.
    """
    scored: list[dict[str, Any]] = []
    for expr in _candidate_forms(value):
        try:
            got = _eval_value(expr)
        except Exception:
            continue
        if not _approx_eq(got, float(value)):
            continue
        cost = _symbolic_cost(expr)
        scored.append(
            {
                "expr": expr,
                "symbolic_cost": cost,
                "length": len(expr),
                "domains": sorted(_domains_in_expr(expr)),
                "federation": "".join(d for d in ("A", "S", "M", "D") if d in _domains_in_expr(expr))
                or "LIT",
            }
        )
    if not scored:
        lit = f"{int(value)}"
        scored.append(
            {
                "expr": lit,
                "symbolic_cost": _symbolic_cost(lit),
                "length": len(lit),
                "domains": [],
                "federation": "LIT",
            }
        )
    scored.sort(key=lambda row: (row["symbolic_cost"], row["length"], row["expr"]))
    canonical = str(scored[0]["expr"])
    div = (
        int(federation_diversity_slots)
        if federation_diversity_slots is not None
        else max(2, equivalents_limit // 4)
    )
    div = max(0, min(div, equivalents_limit))
    primary_n = max(0, equivalents_limit - div)
    equivalents: list[str] = []
    seen: set[str] = {canonical}
    for row in scored[1 : primary_n + 1]:
        expr = str(row["expr"])
        if expr in seen:
            continue
        equivalents.append(expr)
        seen.add(expr)
    # Diversity fill: mixed-domain federations first.
    for row in scored[1:]:
        if len(equivalents) >= equivalents_limit:
            break
        expr = str(row["expr"])
        if expr in seen:
            continue
        if len(row.get("domains") or []) >= 2:
            equivalents.append(expr)
            seen.add(expr)
    # Remainder: continue cost order.
    for row in scored[1:]:
        if len(equivalents) >= equivalents_limit:
            break
        expr = str(row["expr"])
        if expr in seen:
            continue
        equivalents.append(expr)
        seen.add(expr)
    return canonical, equivalents, scored


@dataclass
class UMLEquationRegistry:
    """Machine index + mathematical forms for a sealed vocabulary."""

    vocab: list[str]
    schema_version: str = SCHEMA_VERSION
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    value_to_char: dict[int, str] = field(default_factory=dict)
    vocab_sha256: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.vocab_sha256:
            self.vocab_sha256 = sha256("".join(self.vocab).encode("utf-8")).hexdigest()
        if not self.entries:
            self._build_entries()
        else:
            self.value_to_char = {
                int(row["value"]): str(ch) for ch, row in self.entries.items()
            }

    def _build_entries(self) -> None:
        self.entries = {}
        self.value_to_char = {}
        for token_id, ch in enumerate(self.vocab):
            canonical, equivalents, scored = pick_canonical(token_id)
            self.entries[ch] = {
                "char": ch,
                "token_id": token_id,
                "value": token_id,
                "canonical": canonical,
                "equivalents": equivalents,
                "canonical_cost": scored[0]["symbolic_cost"],
            }
            self.value_to_char[token_id] = ch

    def encode_char(self, ch: str) -> str:
        if ch not in self.entries:
            raise KeyError(f"uml_registry_unknown_char:{ch!r}")
        return str(self.entries[ch]["canonical"])

    def decode_eq(self, expr: str) -> str:
        value = _eval_value(expr)
        # Token values are integers 0..n-1
        nearest = int(round(value))
        if not _approx_eq(value, float(nearest)):
            raise ValueError(f"uml_registry_non_integer_value:{expr}:{value}")
        if nearest not in self.value_to_char:
            raise KeyError(f"uml_registry_value_not_in_vocab:{nearest}")
        return self.value_to_char[nearest]

    def encode_text(self, text: str) -> list[str]:
        return [self.encode_char(ch) for ch in text]

    def decode_equations(self, equations: Sequence[str]) -> str:
        return "".join(self.decode_eq(expr) for expr in equations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "vocab_sha256": self.vocab_sha256,
            "vocab_size": len(self.vocab),
            "vocab": self.vocab,
            "entries": self.entries,
            "meta": {
                **self.meta,
                "canonical_rule": "lowest_symbolic_cost_then_shortest_then_lex",
                "dual": ["Universal Machine Language", "Universal Mathematical Language"],
                "generator_id": GENERATOR_ID,
                "equivalents_limit": DEFAULT_EQUIVALENTS_LIMIT,
            },
        }

    def registry_sha256(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def from_vocab(cls, vocab: Sequence[str], *, meta: dict[str, Any] | None = None) -> "UMLEquationRegistry":
        return cls(vocab=list(vocab), meta=dict(meta or {}))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UMLEquationRegistry":
        return cls(
            vocab=list(payload["vocab"]),
            schema_version=str(payload.get("schema_version") or SCHEMA_VERSION),
            entries=dict(payload.get("entries") or {}),
            vocab_sha256=str(payload.get("vocab_sha256") or ""),
            meta=dict(payload.get("meta") or {}),
        )

    @classmethod
    def load(cls, path: Path | str) -> "UMLEquationRegistry":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def save(self, path: Path | str) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict()
        payload["registry_sha256"] = self.registry_sha256()
        with out.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        return out


def load_sandbox96_vocab(vocab_manifest: Path | str) -> list[str]:
    data = json.loads(Path(vocab_manifest).read_text(encoding="utf-8"))
    vocab = list(data["vocab"])
    if len(vocab) != 96:
        raise ValueError(f"uml_registry_expected_96_got_{len(vocab)}")
    return vocab


def build_sandbox96_registry(
    vocab_manifest: Path | str,
    *,
    out_path: Path | str | None = None,
) -> UMLEquationRegistry:
    vocab_path = Path(vocab_manifest)
    vocab = load_sandbox96_vocab(vocab_path)
    reg = UMLEquationRegistry.from_vocab(
        vocab,
        meta={
            "vocab_source": str(vocab_path).replace("\\", "/"),
            "slice": "sandbox96_identity",
            "refine": "v1.1",
            "generator_id": GENERATOR_ID,
        },
    )
    target = Path(out_path) if out_path else SANDBOX96_ARTIFACT
    reg.save(target)
    return reg


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build UML sandbox96 equation registry")
    parser.add_argument(
        "--vocab",
        default=r"L:\Continue\Viv\foundation\models\Training\data\identity\v61_stratified_preservation_replay\VOCAB.json",
    )
    parser.add_argument("--out", default=str(SANDBOX96_ARTIFACT))
    args = parser.parse_args()
    reg = build_sandbox96_registry(args.vocab, out_path=args.out)
    print(
        f"UML_REGISTRY_BUILT size={len(reg.vocab)} sha={reg.registry_sha256()[:16]}... "
        f"out={Path(args.out)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
