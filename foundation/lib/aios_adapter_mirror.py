"""Callable mirror_core adapter — Viv introspection dashboard (REAL).

Registry id: mirror_core
V2 source (read-only): L:/Continue/FSAA/Luna/AIOS_V2/mirror_core

API: status(), introspect(), plant_snapshot(), run_smoke()

Maps V2 rich socket dashboard onto Viv organism status + aios_self.understand_self
+ master RID plant. Does not open V2 steel-brain socket or invent UI telemetry.
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
    ORGANISM_LATEST,
    ORGANISM_STATE,
    status as organism_status,
)
from lib.aios_self import SELF_MD, SELF_MAP, understand_self  # noqa: E402
from lib.paths import AUTO_ARTIFACTS, SANDBOX_ROOT  # noqa: E402

ADAPTER_ID = "mirror_core"
REGISTRY_ID = "mirror_core"

V2_MIRROR = Path(r"L:/Continue/FSAA/Luna/AIOS_V2/mirror_core")
EVIDENCE_DIR = AUTO_ARTIFACTS / "mirror"
ADAPTER_EVIDENCE = EVIDENCE_DIR / "adapter_smoke.json"
PLANT_LAST = AUTO_ARTIFACTS / "plant" / "last_stability_capture.json"
PLANT_TREND = AUTO_ARTIFACTS / "plant" / "plant_trend_scorecard.json"
MASTER_RID = AUTO_ARTIFACTS / "master_rid.json"


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


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _v2_presence() -> dict[str, Any]:
    mirror_py = V2_MIRROR / "mirror.py"
    return {
        "v2_mirror_readable": V2_MIRROR.is_dir(),
        "v2_mirror_py": mirror_py.is_file(),
        "v2_socket_dashboard": True if mirror_py.is_file() else False,
        "viv_executes_v2": False,
        "viv_opens_steel_socket": False,
        "viv_mode": "organism_status_plus_self_introspect",
        "note": (
            "V2 mirror.py (rich Live dashboard on 127.0.0.1:5151) surveyed "
            "read-only; Viv uses organism/self/plant JSON surfaces."
        ),
    }


def status() -> dict[str, Any]:
    """Compact dashboard from organism + RID (Viv-native mirror)."""
    try:
        org = organism_status()
        rid = org.get("rid") if isinstance(org.get("rid"), dict) else {}
        gate = org.get("gate") if isinstance(org.get("gate"), dict) else {}
        systems = org.get("systems") if isinstance(org.get("systems"), dict) else {}
        beat = _load_json(ORGANISM_LATEST) or {}
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "registry_id": REGISTRY_ID,
                "op": "status",
                "at": _utc(),
                "s_n": _s_n(),
                "halted": bool(org.get("halted")),
                "organism_state_exists": ORGANISM_STATE.is_file(),
                "latest_beat_exists": ORGANISM_LATEST.is_file(),
                "beat_mode": beat.get("mode"),
                "beat_timestamp": beat.get("timestamp"),
                "rid": rid,
                "gate_allow": gate.get("allow") if "allow" in gate else gate.get("ok"),
                "systems_counts": systems.get("counts"),
                "systems_next": systems.get("next"),
                "self_md_exists": SELF_MD.is_file(),
                "self_map_exists": SELF_MAP.is_file(),
                "sandbox_root": _as_posix(SANDBOX_ROOT),
                "viv_module": "lib.aios_organism.status",
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


def introspect() -> dict[str, Any]:
    """Run aios_self.understand_self — honest self snapshot, no V2 socket."""
    try:
        understanding = understand_self()
        plant = understanding.get("plant") if isinstance(understanding.get("plant"), dict) else {}
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "introspect",
                "at": _utc(),
                "who": understanding.get("who"),
                "understanding": understanding.get("understanding"),
                "s_n": understanding.get("s_n"),
                "plant": plant,
                "tools_authored_n": len(understanding.get("tools_authored") or []),
                "dream_files": understanding.get("dream_files"),
                "gaps": understanding.get("gaps"),
                "security": understanding.get("security"),
                "voice": understanding.get("voice"),
                "source": "lib.aios_self.understand_self",
                "viv_opens_steel_socket": False,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "introspect",
                "at": _utc(),
                "error": str(exc),
            },
        }


def plant_snapshot() -> dict[str, Any]:
    """Plant / RID / trend scorecard pointers for mirror physics pane."""
    try:
        from lib.master_rid import load_master_rid

        m = load_master_rid()
        last = _load_json(PLANT_LAST) or {}
        trend = _load_json(PLANT_TREND) or {}
        verdict = last.get("verdict") if isinstance(last.get("verdict"), dict) else {}
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "plant_snapshot",
                "at": _utc(),
                "master_s_n": m.master_s_n,
                "status": m.status,
                "rsr": m.master_rsr,
                "ltp": m.master_ltp,
                "rle": m.master_rle,
                "master_rid_path": _as_posix(MASTER_RID),
                "master_rid_exists": MASTER_RID.is_file(),
                "last_stability_exists": PLANT_LAST.is_file(),
                "last_verdict": verdict.get("verdict"),
                "last_n_logged": verdict.get("n_logged"),
                "trend_exists": PLANT_TREND.is_file(),
                "trend_verdict": trend.get("verdict") or trend.get("ok"),
                "trend_n": trend.get("n_s_n") or trend.get("n"),
                "viv_fake_dashboard": False,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "plant_snapshot",
                "at": _utc(),
                "error": str(exc),
            },
        }


def run_smoke() -> dict[str, Any]:
    """Prove status + introspect + plant snapshot; assert no V2 socket open."""
    st = status()
    inn = introspect()
    plant = plant_snapshot()
    sev = st.get("evidence") or {}
    iev = inn.get("evidence") or {}
    pev = plant.get("evidence") or {}
    v2 = sev.get("v2") or {}
    ok = (
        bool(st.get("ok"))
        and bool(inn.get("ok"))
        and bool(plant.get("ok"))
        and bool(sev.get("organism_state_exists") or sev.get("latest_beat_exists"))
        and bool(iev.get("understanding"))
        and pev.get("master_s_n") is not None
        and v2.get("viv_executes_v2") is False
        and v2.get("viv_opens_steel_socket") is False
        and iev.get("viv_opens_steel_socket") is False
        and pev.get("viv_fake_dashboard") is False
    )
    evidence = {
        "adapter": ADAPTER_ID,
        "op": "smoke",
        "at": _utc(),
        "status_ok": bool(st.get("ok")),
        "introspect_ok": bool(inn.get("ok")),
        "plant_ok": bool(plant.get("ok")),
        "understanding": iev.get("understanding"),
        "tools_authored_n": iev.get("tools_authored_n"),
        "gaps": iev.get("gaps"),
        "plant_s_n": pev.get("master_s_n"),
        "plant_status": pev.get("status"),
        "beat_mode": sev.get("beat_mode"),
        "v2_mirror_readable": v2.get("v2_mirror_readable"),
        "viv_executes_v2": v2.get("viv_executes_v2"),
        "viv_opens_steel_socket": v2.get("viv_opens_steel_socket"),
        "status": st,
        "introspect": inn,
        "plant_snapshot": plant,
    }
    try:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        slim = {
            "ok": ok,
            "at": evidence["at"],
            "understanding": iev.get("understanding"),
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
