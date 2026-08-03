"""CPU automaton authority gates — RID supervisor + optional quorum + foundation."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.auto_rid_journal import HEARTBEAT_PATH, STATE_PATH, read_supervisor_state
from lib.foundation_health import evaluate_foundation_gate
from lib.paths import AUTO_ARTIFACTS, AUTOMATION_ROOT, FOUNDATION_ROOT

RID_BODY = AUTOMATION_ROOT / "3_body"
QUORUM_POLICY = FOUNDATION_ROOT / "cpu_config.json"
OPERATOR_PATH = AUTO_ARTIFACTS / "operator_present.json"
FOUNDATION_GATE_PATH = AUTO_ARTIFACTS / "foundation_gate.json"


def _body_on_path() -> None:
    body = str(RID_BODY)
    if body not in sys.path:
        sys.path.insert(0, body)


def _load_cpu_config() -> dict[str, Any]:
    if not QUORUM_POLICY.is_file():
        return {}
    return json.loads(QUORUM_POLICY.read_text(encoding="utf-8"))


def write_operator_present(*, active: bool = True) -> None:
    OPERATOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone

    payload = {
        "status": "verified" if active else "absent",
        "valid": active,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "viv_cpu_automaton",
    }
    OPERATOR_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def rid_gate(action_risk: str = "normal", irreversible: bool = False) -> dict[str, Any]:
    _body_on_path()
    from rid_action_gate import gate, read_state

    return gate(read_state(STATE_PATH), action_risk, irreversible)


def quorum_run() -> dict[str, Any]:
    cfg = _load_cpu_config()
    policy_path = cfg.get("quorum_policy")
    if not policy_path:
        return {"allow": True, "skipped": True, "reason": "no_quorum_policy"}
    policy_file = Path(str(policy_path))
    if not policy_file.is_file():
        return {"allow": False, "skipped": False, "reason": f"missing_policy:{policy_file}"}
    # The quorum gate belongs to the local CPU core.  Keep the relocated
    # automation tree as a compatibility fallback, but do not depend on it
    # being present for the Alpha runtime.
    try:
        from lib.aios_quorum_gate import evaluate_quorum, load_policy
    except ModuleNotFoundError:
        aut = str(AUTOMATION_ROOT)
        if aut not in sys.path:
            sys.path.insert(0, aut)
        from aios_quorum_gate import evaluate_quorum, load_policy

    result = evaluate_quorum("run", load_policy(policy_file))
    return {
        "allow": result.allow,
        "mode": result.mode,
        "valid_count": result.valid_count,
        "required": result.required,
        "generated_utc": result.generated_utc,
    }


def foundation_gate(*, include_stress: bool = False) -> dict[str, Any]:
    report = evaluate_foundation_gate(include_stress=include_stress)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **report,
    }
    FOUNDATION_GATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FOUNDATION_GATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def evaluate_run_gate(*, action_risk: str = "low", irreversible: bool = False) -> dict[str, Any]:
    foundation = foundation_gate(include_stress=False)
    rid = rid_gate(action_risk=action_risk, irreversible=irreversible)
    quorum = quorum_run()
    allow = bool(foundation.get("allow")) and bool(rid.get("allow")) and bool(quorum.get("allow", True))
    if HEARTBEAT_PATH.is_file():
        try:
            hb = json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
            if not hb.get("allow_automation", False):
                allow = False
                rid["reasons"] = list(rid.get("reasons") or []) + ["automaton_heartbeat_denied"]
        except json.JSONDecodeError:
            allow = False
    if not foundation.get("allow"):
        rid["reasons"] = list(rid.get("reasons") or []) + [
            f"foundation_gate_denied:{foundation.get('failed')}"
        ]
    supervisor = read_supervisor_state()
    return {
        "allow": allow,
        "foundation_gate": foundation,
        "rid_gate": rid,
        "quorum": quorum,
        "supervisor_control": (supervisor or {}).get("system_rid", {}).get("control"),
        "heartbeat_path": str(HEARTBEAT_PATH),
        "foundation_gate_path": str(FOUNDATION_GATE_PATH),
    }
