"""Callable consciousness_core adapter — Viv organism + plant pulse (REAL).

Registry id: consciousness_core
V2 source (read-only): L:/Continue/FSAA/Luna/AIOS_V2/consciousness_core

API: status(), latest_beat(), plant_pulse(), run_smoke()

Maps V2 pulse/fragments/hemispheres role onto Viv organism state + RID plant.
Does not invent hemisphere cognition or execute V2 Aria/biological loops.
Does not mutate security_core.
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

from lib.aios_organism import (  # noqa: E402
    HALT_FLAG,
    ORGANISM_EVENTS,
    ORGANISM_LATEST,
    ORGANISM_ROOT,
    ORGANISM_STATE,
    status as organism_status,
)
from lib.paths import AUTO_ARTIFACTS  # noqa: E402

ADAPTER_ID = "consciousness_core"
REGISTRY_ID = "consciousness_core"

V2_CONSCIOUSNESS = Path(r"L:/Continue/FSAA/Luna/AIOS_V2/consciousness_core")
EVIDENCE_DIR = AUTO_ARTIFACTS / "consciousness"
ADAPTER_EVIDENCE = EVIDENCE_DIR / "adapter_smoke.json"
PLANT_LAST = AUTO_ARTIFACTS / "plant" / "last_stability_capture.json"


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


def _v2_presence() -> dict[str, Any]:
    bio = V2_CONSCIOUSNESS / "biological"
    markers = {
        "aria_agent_py": (V2_CONSCIOUSNESS / "aria_agent.py").is_file(),
        "brainstem_py": (bio / "brainstem.py").is_file(),
        "hemispheres_py": (bio / "hemispheres.py").is_file(),
        "heart_py": (bio / "heart.py").is_file(),
        "soul_py": (bio / "soul.py").is_file(),
        "dream_state_py": (bio / "dream_state.py").is_file(),
    }
    return {
        "v2_consciousness_readable": V2_CONSCIOUSNESS.is_dir(),
        "v2_biological_dir": bio.is_dir(),
        "markers": markers,
        "viv_executes_v2": False,
        "viv_mode": "organism_state_plus_plant_pulse",
        "note": (
            "V2 biological/aria surveyed read-only; Viv uses aios_organism + "
            "master_rid plant surfaces (no fake hemispheres)."
        ),
    }


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def status() -> dict[str, Any]:
    """Organism dashboard + V2 survey. Returns {ok, evidence}."""
    try:
        org = organism_status()
        state = _load_json(ORGANISM_STATE) or {}
        events_n = 0
        if ORGANISM_EVENTS.is_file():
            try:
                with ORGANISM_EVENTS.open("r", encoding="utf-8", errors="replace") as fh:
                    events_n = sum(1 for _ in fh)
            except OSError:
                events_n = 0
        rid = org.get("rid") if isinstance(org.get("rid"), dict) else {}
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "registry_id": REGISTRY_ID,
                "op": "status",
                "at": _utc(),
                "s_n": _s_n(),
                "organism_root": _as_posix(ORGANISM_ROOT),
                "organism_state_exists": ORGANISM_STATE.is_file(),
                "latest_beat_exists": ORGANISM_LATEST.is_file(),
                "halted": HALT_FLAG.is_file(),
                "events_count": events_n,
                "boot_ok": state.get("ok"),
                "boot_steps": state.get("steps"),
                "rid": rid,
                "gate": org.get("gate"),
                "viv_module": "lib.aios_organism",
                "v2": _v2_presence(),
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


def latest_beat() -> dict[str, Any]:
    """Read latest organism beat artifact (pulse/journal steps — not V2 Aria)."""
    try:
        beat = _load_json(ORGANISM_LATEST)
        if beat is None:
            return {
                "ok": False,
                "evidence": {
                    "adapter": ADAPTER_ID,
                    "op": "latest_beat",
                    "at": _utc(),
                    "error": "no_latest_beat",
                    "path": _as_posix(ORGANISM_LATEST),
                },
            }
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "latest_beat",
                "at": _utc(),
                "path": _as_posix(ORGANISM_LATEST),
                "timestamp": beat.get("timestamp"),
                "mode": beat.get("mode"),
                "master_s_n": beat.get("master_s_n"),
                "steps": beat.get("steps"),
                "ok_flag": beat.get("ok"),
                "beat_keys": sorted(beat.keys())[:24],
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "latest_beat",
                "at": _utc(),
                "error": str(exc),
            },
        }


def plant_pulse() -> dict[str, Any]:
    """Live master RID + last stability capture pointer (plant surface)."""
    try:
        from lib.master_rid import load_master_rid

        m = load_master_rid()
        plant = _load_json(PLANT_LAST) or {}
        verdict = plant.get("verdict") if isinstance(plant.get("verdict"), dict) else {}
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "plant_pulse",
                "at": _utc(),
                "master_s_n": m.master_s_n,
                "status": m.status,
                "rsr": m.master_rsr,
                "ltp": m.master_ltp,
                "rle": m.master_rle,
                "n_subsystems": getattr(m, "n_subsystems", None),
                "last_stability_path": _as_posix(PLANT_LAST),
                "last_stability_exists": PLANT_LAST.is_file(),
                "last_verdict": verdict.get("verdict"),
                "last_n_logged": verdict.get("n_logged"),
                "viv_fake_cognition": False,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "plant_pulse",
                "at": _utc(),
                "error": str(exc),
            },
        }


def run_smoke() -> dict[str, Any]:
    """Prove organism + plant read paths; assert no V2 biological execution."""
    st = status()
    beat = latest_beat()
    pulse = plant_pulse()
    sev = st.get("evidence") or {}
    bev = beat.get("evidence") or {}
    pev = pulse.get("evidence") or {}
    v2 = sev.get("v2") or {}
    ok = (
        bool(st.get("ok"))
        and bool(beat.get("ok"))
        and bool(pulse.get("ok"))
        and bool(sev.get("organism_state_exists"))
        and bool(sev.get("latest_beat_exists"))
        and pev.get("master_s_n") is not None
        and v2.get("viv_executes_v2") is False
        and pev.get("viv_fake_cognition") is False
    )
    evidence = {
        "adapter": ADAPTER_ID,
        "op": "smoke",
        "at": _utc(),
        "status_ok": bool(st.get("ok")),
        "latest_beat_ok": bool(beat.get("ok")),
        "plant_pulse_ok": bool(pulse.get("ok")),
        "organism_state_exists": sev.get("organism_state_exists"),
        "latest_beat_exists": sev.get("latest_beat_exists"),
        "beat_mode": bev.get("mode"),
        "beat_s_n": bev.get("master_s_n"),
        "plant_s_n": pev.get("master_s_n"),
        "plant_status": pev.get("status"),
        "v2_readable": v2.get("v2_consciousness_readable"),
        "viv_executes_v2": v2.get("viv_executes_v2"),
        "status": st,
        "latest_beat": beat,
        "plant_pulse": pulse,
    }
    try:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        slim = {
            "ok": ok,
            "at": evidence["at"],
            "beat_mode": bev.get("mode"),
            "beat_s_n": bev.get("master_s_n"),
            "plant_s_n": pev.get("master_s_n"),
            "plant_status": pev.get("status"),
            "viv_executes_v2": v2.get("viv_executes_v2"),
        }
        ADAPTER_EVIDENCE.write_text(json.dumps(slim, indent=2), encoding="utf-8")
        evidence["evidence_path"] = _as_posix(ADAPTER_EVIDENCE)
    except OSError as exc:
        evidence["evidence_write_error"] = str(exc)
    return {"ok": ok, "evidence": evidence}


if __name__ == "__main__":
    result = run_smoke()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("ok") else 1)
