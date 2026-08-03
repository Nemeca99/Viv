"""CPU Steel Judge — absorbed from V2 steel_brain_core/judge.py.

Port of OrchestratorOfEquilibrium structural + S_n gate WITHOUT Luna CARMA /
3-LLM refinery dependencies. Viv uses this as a deterministic stability brake.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS
from lib.security_membrane import tool_gate

JUDGE_DIR = AUTO_ARTIFACTS / "steel_judge"
EQUILIBRIUM = JUDGE_DIR / "equilibrium.json"
MEMORY = JUDGE_DIR / "steel_brain_memory.json"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def structural_rsr(current: str, previous: str) -> float:
    """V2 judge structural RSR — length + hash delta (no embeddings)."""
    if not previous:
        return 1.0
    len_c, len_p = len(current), len(previous)
    hash_c = int(hashlib.sha256(current.encode()).hexdigest()[:4], 16) / 65535.0
    hash_p = int(hashlib.sha256(previous.encode()).hexdigest()[:4], 16) / 65535.0
    len_delta = abs(len_c - len_p) / max(1, max(len_c, len_p))
    hash_delta = abs(hash_c - hash_p)
    # Same grace as V2 for short prompts
    if max(len_c, len_p) < 100:
        return max(0.0, 1.0 - (0.5 * len_delta + 0.5 * hash_delta))
    return max(0.0, 1.0 - (0.6 * len_delta + 0.4 * hash_delta))


def token_overlap(a: str, b: str) -> float:
    """Cheap semantic proxy until Nomic CARMA is absorbed."""
    ta = {t.lower() for t in a.split() if len(t) > 2}
    tb = {t.lower() for t in b.split() if len(t) > 2}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta | tb))


def evaluate(
    current: str,
    previous: str = "",
    *,
    master_s_n: float = 0.5,
    target_semantic: float = 0.35,
    target_structural: float = 0.70,
) -> dict[str, Any]:
    """Return pass/fail equilibrium verdict for a candidate text."""
    struct = structural_rsr(current or "", previous or "")
    sem = token_overlap(current or "", previous or "") if previous else 1.0
    structural_ok = struct >= target_structural
    # If no previous, only S_n + non-empty gate
    semantic_ok = True if not previous else sem >= target_semantic
    sn_ok = float(master_s_n) >= 0.37
    passed = bool(current.strip()) and structural_ok and semantic_ok and sn_ok
    verdict = {
        "at": _utc(),
        "passed": passed,
        "structural_rsr": round(struct, 4),
        "token_overlap": round(sem, 4),
        "master_s_n": round(float(master_s_n), 4),
        "gates": {
            "structural_ok": structural_ok,
            "semantic_ok": semantic_ok,
            "sn_ok": sn_ok,
            "nonempty": bool((current or "").strip()),
        },
        "targets": {"structural": target_structural, "semantic": target_semantic, "dormancy": 0.37},
        "source": "viv_steel_judge_absorbed_from_v2",
    }
    return verdict


def persist_verdict(verdict: dict[str, Any], *, s_n: float) -> dict[str, Any]:
    JUDGE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": _utc(), "last": verdict}
    text = json.dumps(payload, indent=2)
    gate = str(EQUILIBRIUM).replace("\\", "/")
    v = tool_gate("write_file", {"path": gate, "content": text}, s_n)
    if not v.get("allowed"):
        return {
            "ok": True,
            "deferred": True,
            "error": v.get("reason"),
            "verdict": verdict,
            "note": "evaluate_ok_persist_blocked_by_membrane",
        }
    EQUILIBRIUM.write_text(text, encoding="utf-8")
    if not MEMORY.is_file():
        mem = {"Judge": 0.70, "absorbed_from": "AIOS_V2/steel_brain_core/judge.py", "at": _utc()}
        mt = json.dumps(mem, indent=2)
        mg = tool_gate("write_file", {"path": str(MEMORY).replace("\\", "/"), "content": mt}, s_n)
        if mg.get("allowed"):
            MEMORY.write_text(mt, encoding="utf-8")
    return {"ok": True, "path": gate, "verdict": verdict}
