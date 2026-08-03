"""Fail-closed executor for CPU action contracts.

Only the idle action is currently bound, and it is a verified no-op. Real
effects remain closed until an effect-specific binding is implemented.
"""
from __future__ import annotations

from typing import Any, Mapping

from lib.cpu_action_contract import make_receipt, verify_contract


def execute_contract(contract: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    verification = verify_contract(contract, state)
    if not verification.get("ok"):
        return {"ok": False, "state": "DENIED", "reason": "contract_verification_failed", "verification": verification, "action_executed": False, "writes_performed": False, "receipt": make_receipt(contract, verification)}
    action = str(contract.get("action") or "").casefold()
    effects = contract.get("allowed_effects") if isinstance(contract.get("allowed_effects"), list) else []
    if action == "idle" and not contract.get("side_effects_allowed") and not effects:
        result = {"ok": True, "state": "EXECUTED_NOOP", "reason": "idle_noop", "verification": verification, "action_executed": True, "writes_performed": False, "effect": None}
    elif action == "restore" and contract.get("side_effects_allowed") and "dream_consolidation" in effects:
        try:
            from lib.aios_dream import perform_dream_cycle

            dream = perform_dream_cycle(force=False)
            performed = bool(dream.get("ok")) and not bool(dream.get("skipped"))
            result = {"ok": performed, "state": "EXECUTED" if performed else "NOOP", "reason": "dream_consolidation" if performed else str(dream.get("skipped") or dream.get("reason") or "dream_not_performed"), "verification": verification, "action_executed": performed, "writes_performed": performed, "effect": "dream_consolidation", "effect_result": dream}
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "state": "DENIED", "reason": f"dream_effect_error:{exc}", "verification": verification, "action_executed": False, "writes_performed": False, "effect": "dream_consolidation"}
    else:
        result = {"ok": False, "state": "DENIED", "reason": "effect_binding_closed", "verification": verification, "action_executed": False, "writes_performed": False, "effect": None}
    result["receipt"] = make_receipt(contract, {**verification, "execution_state": result["state"], "action_executed": result["action_executed"]})
    result["llm_authority"] = False
    return result
