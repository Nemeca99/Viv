"""Callable steel_brain / steel_judge adapter — thin wrap over lib/steel_judge.

V2 steel_brain_core (read-only) includes OrchestratorOfEquilibrium + AdversarialRefinery
(3-LLM hot-potato). Viv absorbed the deterministic structural + S_n gate only
(lib/steel_judge.py). This adapter calls the real judge and reports honestly:
no fake 3-LLM refinery when that path is missing.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.steel_judge import (  # noqa: E402
    EQUILIBRIUM,
    JUDGE_DIR,
    MEMORY,
    evaluate as _evaluate,
    persist_verdict as _persist_verdict,
)

ADAPTER_ID = "steel"
V2_STEEL = Path(r"L:/Continue/FSAA/Luna/AIOS_V2/steel_brain_core")
_SMOKE_MARKER = "STEEL_ADAPTER_SMOKE"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_posix(p: Path | str) -> str:
    return str(p).replace("\\", "/")


def _s_n() -> float:
    try:
        from lib.master_rid import load_master_rid

        return float(load_master_rid().master_s_n)
    except Exception:  # noqa: BLE001
        return 0.5


def _refinery_available() -> dict[str, Any]:
    """Report V2 3-LLM refinery presence without inventing a fake loop."""
    refinery = V2_STEEL / "refinery.py"
    init = V2_STEEL / "__init__.py"
    present = V2_STEEL.is_dir() and refinery.is_file()
    # Viv path does not import or execute V2 refinery (Luna CARMA / 3-LLM deps).
    return {
        "v2_steel_brain_readable": V2_STEEL.is_dir(),
        "v2_refinery_py": refinery.is_file() if present else False,
        "v2_stabilize_entry": init.is_file() if V2_STEEL.is_dir() else False,
        "viv_3llm_refinery": False,
        "viv_mode": "deterministic_structural_sn_gate",
        "note": (
            "V2 AdversarialRefinery (3-LLM) is not wired into Viv; "
            "adapter uses lib/steel_judge.evaluate only."
        ),
    }


def judge(
    text: str,
    *,
    previous: str = "",
    persist: bool = True,
    master_s_n: float | None = None,
) -> dict[str, Any]:
    """Run real steel_judge.evaluate on text. Returns {ok, evidence}."""
    body = (text or "").strip()
    if not body:
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "judge",
                "at": _utc(),
                "error": "empty_text",
                "refinery": _refinery_available(),
            },
        }
    sn = float(master_s_n) if master_s_n is not None else _s_n()
    try:
        verdict = _evaluate(body, previous or "", master_s_n=sn)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "judge",
                "at": _utc(),
                "error": str(exc),
                "s_n": sn,
                "refinery": _refinery_available(),
            },
        }
    persist_out: dict[str, Any] | None = None
    if persist:
        try:
            persist_out = _persist_verdict(verdict, s_n=sn)
        except Exception as exc:  # noqa: BLE001
            persist_out = {"ok": False, "error": str(exc)}
    passed = bool(verdict.get("passed"))
    return {
        "ok": True,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "judge",
            "at": _utc(),
            "s_n": sn,
            "passed": passed,
            "verdict": verdict,
            "persist": persist_out,
            "source": verdict.get("source") or "viv_steel_judge",
            "refinery": _refinery_available(),
        },
    }


def status() -> dict[str, Any]:
    """Steel judge paths + last equilibrium snapshot. Returns {ok, evidence}."""
    try:
        last: dict[str, Any] | None = None
        if EQUILIBRIUM.is_file():
            try:
                payload = json.loads(EQUILIBRIUM.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    last = payload.get("last") if isinstance(payload.get("last"), dict) else payload
            except (OSError, json.JSONDecodeError):
                last = None
        mem: dict[str, Any] | None = None
        if MEMORY.is_file():
            try:
                raw = json.loads(MEMORY.read_text(encoding="utf-8"))
                mem = raw if isinstance(raw, dict) else None
            except (OSError, json.JSONDecodeError):
                mem = None
        refinery = _refinery_available()
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "status",
                "at": _utc(),
                "s_n": _s_n(),
                "judge_dir": _as_posix(JUDGE_DIR),
                "equilibrium_path": _as_posix(EQUILIBRIUM),
                "equilibrium_exists": EQUILIBRIUM.is_file(),
                "memory_path": _as_posix(MEMORY),
                "memory_exists": MEMORY.is_file(),
                "last_verdict": last,
                "memory": mem,
                "viv_judge_module": "lib.steel_judge",
                "refinery": refinery,
                "v2_path": _as_posix(V2_STEEL) if V2_STEEL.is_dir() else None,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "status",
                "at": _utc(),
                "error": str(exc),
            },
        }


def run_smoke() -> dict[str, Any]:
    """Prove real evaluate + status; assert no fake 3-LLM claim."""
    marker = f"{_SMOKE_MARKER}_{_utc().replace(':', '').replace('-', '')}"
    # Stable pair: high structural RSR + token overlap when previous is near-identical
    previous = (
        f"{marker} steel judge equilibrium structural gate proof baseline "
        "viv adapter smoke deterministic"
    )
    current = (
        f"{marker} steel judge equilibrium structural gate proof baseline "
        "viv adapter smoke deterministic pass"
    )
    j_empty = judge("", persist=False)
    j = judge(current, previous=previous, persist=True)
    st = status()
    ev = j.get("evidence") or {}
    verdict = ev.get("verdict") or {}
    refinery = ev.get("refinery") or {}
    # Must call real judge (ok) and honestly report viv_3llm_refinery=False
    honest = refinery.get("viv_3llm_refinery") is False
    has_gates = isinstance(verdict.get("gates"), dict)
    has_rsr = "structural_rsr" in verdict
    ok = (
        bool(j.get("ok"))
        and has_gates
        and has_rsr
        and honest
        and bool(st.get("ok"))
        and not bool(j_empty.get("ok"))
    )
    return {
        "ok": ok,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "smoke",
            "at": _utc(),
            "marker": marker,
            "empty_rejected": not bool(j_empty.get("ok")),
            "judge_ok": bool(j.get("ok")),
            "passed": ev.get("passed"),
            "structural_rsr": verdict.get("structural_rsr"),
            "token_overlap": verdict.get("token_overlap"),
            "source": verdict.get("source"),
            "viv_3llm_refinery": refinery.get("viv_3llm_refinery"),
            "viv_mode": refinery.get("viv_mode"),
            "status_ok": bool(st.get("ok")),
            "equilibrium_exists": (st.get("evidence") or {}).get("equilibrium_exists"),
            "persist": ev.get("persist"),
            "judge": j,
            "status": st,
        },
    }


if __name__ == "__main__":
    result = run_smoke()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("ok") else 1)
