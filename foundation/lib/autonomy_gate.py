"""Tiered run authority for autonomous AIOS operation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from lib.auto_rid_journal import HEARTBEAT_PATH, read_supervisor_state
from lib.foundation_health import evaluate_foundation_gate
from lib.paths import AUTO_ARTIFACTS, AUTOMATION_ROOT, FOUNDATION_ROOT
from lib.piston_engine import HALT_FLAG, is_halted

RID_BODY = AUTOMATION_ROOT / "3_body"
QUORUM_POLICY = FOUNDATION_ROOT / "cpu_config.json"
AUTONOMOUS_STATE_PATH = AUTO_ARTIFACTS / "autonomous_state.json"

AutonomyMode = Literal["halted", "degraded", "nominal"]


def _body_on_path() -> None:
    import sys

    body = str(RID_BODY)
    if body not in sys.path:
        sys.path.insert(0, body)


def _load_cpu_config() -> dict[str, Any]:
    if not QUORUM_POLICY.is_file():
        return {}
    return json.loads(QUORUM_POLICY.read_text(encoding="utf-8"))


def _quorum_run() -> dict[str, Any]:
    from lib.auto_gate import quorum_run

    return quorum_run()


def _rid_gate(action_risk: str, irreversible: bool) -> dict[str, Any]:
    from lib.auto_gate import rid_gate

    return rid_gate(action_risk=action_risk, irreversible=irreversible)


def _autonomy_config() -> dict[str, Any]:
    cfg = _load_cpu_config()
    return cfg.get("autonomy") or {}


def _runtime_state_path() -> Path:
    from lib.paths import AUTO_ARTIFACTS

    return AUTO_ARTIFACTS / "agentic" / "runtime_state.json"


def runtime_needs_resume() -> bool:
    path = _runtime_state_path()
    if not path.is_file():
        return False
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("requires_operator_resume"))
    except (json.JSONDecodeError, OSError):
        return False


def resume_agentic_runtime() -> bool:
    """Clear requires_operator_resume on Viv agentic state."""
    from lib.agentic_runtime import resume

    out = resume()
    return bool(out.get("ok")) and not runtime_needs_resume()


def ensure_runtime_ready() -> dict[str, Any]:
    """Auto-resume Viv agentic runtime in solo_mode when foundation is healthy."""
    autonomy = _autonomy_config()
    if not autonomy.get("solo_mode"):
        return {"resumed": False, "reason": "solo_mode_off"}
    if not runtime_needs_resume():
        return {"resumed": False, "reason": "not_paused"}
    foundation = evaluate_foundation_gate(include_stress=False)
    if not foundation.get("allow"):
        return {"resumed": False, "reason": "foundation_denied"}
    ok = resume_agentic_runtime()
    return {"resumed": ok, "reason": "auto_resume" if ok else "resume_failed", "owner": "viv"}



def evaluate_tiered_gate(
    *,
    action_risk: str = "low",
    irreversible: bool = False,
    sample_s_n: float | None = None,
    sample_status: str | None = None,
) -> dict[str, Any]:
    """Foundation fail or halt.flag -> halted. Else telemetry always; runtime only when full allow."""
    foundation = evaluate_foundation_gate(include_stress=False)
    ts = datetime.now(timezone.utc).isoformat()

    if not foundation.get("allow"):
        return {
            "timestamp": ts,
            "mode": "halted",
            "allow_pulse": False,
            "allow_runtime": False,
            "reasons": ["foundation_gate_denied", foundation.get("failed")],
            "foundation_gate": foundation,
        }

    if is_halted():
        reason = "halt_flag"
        try:
            reason = json.loads(HALT_FLAG.read_text(encoding="utf-8")).get("reason", reason)
        except (json.JSONDecodeError, OSError):
            pass
        return {
            "timestamp": ts,
            "mode": "halted",
            "allow_pulse": False,
            "allow_runtime": False,
            "reasons": [f"halt_flag:{reason}"],
            "foundation_gate": foundation,
        }

    rid = _rid_gate(action_risk=action_risk, irreversible=irreversible)
    autonomy = _autonomy_config()
    solo = bool(autonomy.get("solo_mode"))
    if solo:
        quorum = {"allow": True, "skipped": True, "reason": "solo_mode"}
    else:
        quorum = _quorum_run()
    heartbeat_allow = True
    if HEARTBEAT_PATH.is_file():
        try:
            hb = json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
            heartbeat_allow = bool(hb.get("allow_automation", False))
        except json.JSONDecodeError:
            heartbeat_allow = False

    plant_active = (
        sample_s_n is not None
        and sample_s_n >= 0.45
        and (sample_status or "").upper() == "ACTIVE"
    )
    solo_runtime = solo and plant_active and bool(autonomy.get("runtime_requires_active_sn", True))

    allow_runtime = solo_runtime or (
        bool(rid.get("allow"))
        and bool(quorum.get("allow", True))
        and heartbeat_allow
    )
    mode: AutonomyMode = "nominal" if allow_runtime else "degraded"
    reasons: list[str] = []
    if not allow_runtime:
        if not solo_runtime:
            if not rid.get("allow"):
                reasons.append("rid_gate_denied")
            if not quorum.get("allow", True):
                reasons.append("quorum_denied")
            if not heartbeat_allow:
                reasons.append("heartbeat_denied")
        else:
            reasons.append("plant_not_active")

    supervisor = read_supervisor_state()
    return {
        "timestamp": ts,
        "mode": mode,
        "allow_pulse": True,
        "allow_runtime": allow_runtime,
        "reasons": reasons,
        "foundation_gate": foundation,
        "rid_gate": rid,
        "quorum": quorum,
        "heartbeat_allow": heartbeat_allow,
        "solo_mode": solo,
        "plant_active": plant_active,
        "supervisor_control": (supervisor or {}).get("system_rid", {}).get("control"),
    }


def write_autonomous_state(payload: dict[str, Any]) -> Path:
    AUTONOMOUS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTONOMOUS_STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return AUTONOMOUS_STATE_PATH
