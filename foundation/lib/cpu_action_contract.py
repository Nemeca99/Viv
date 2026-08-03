"""Explicit precondition contracts and receipts for CPU action decisions."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from lib.cpu_choice_simulator import ACTIONS

CONTRACT_VERSION = "cpu_action_contract_v1"


def _hash(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def state_hash(state: Mapping[str, Any]) -> str:
    return _hash(dict(state))


def build_contract(*, task_id: str, action: str, state: Mapping[str, Any], allowed_effects: tuple[str, ...] = (), side_effects_allowed: bool = False, effect_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    selected = str(action).strip().casefold()
    return {
        "version": CONTRACT_VERSION,
        "task_id": str(task_id),
        "action": selected,
        "state_hash": state_hash(state),
        "preconditions": {"state_snapshot_required": True, "s_n_fresh_required": True},
        "allowed_effects": list(allowed_effects),
        "side_effects_allowed": bool(side_effects_allowed),
        "effect_payload": dict(effect_payload or {}),
        "effect_payload_hash": _hash(dict(effect_payload or {})),
        "execution_authority": "not_granted",
    }


def verify_contract(contract: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    expected = str(contract.get("state_hash") or "")
    actual = state_hash(state)
    action = str(contract.get("action") or "").casefold()
    effect_payload = contract.get("effect_payload") if isinstance(contract.get("effect_payload"), Mapping) else {}
    payload_ok = str(contract.get("effect_payload_hash") or "") == _hash(dict(effect_payload))
    ok = str(contract.get("version")) == CONTRACT_VERSION and action in ACTIONS and bool(expected) and expected == actual and payload_ok
    return {"ok": ok, "state": "VERIFIED" if ok else "DENIED", "reason": "preconditions_hold" if ok else "state_drift_or_invalid_contract", "expected_state_hash": expected, "actual_state_hash": actual, "effect_payload_valid": payload_ok, "action": action, "execution_authority": "not_granted"}


def make_receipt(contract: Mapping[str, Any], verification: Mapping[str, Any]) -> dict[str, Any]:
    body = {"contract": dict(contract), "verification": dict(verification), "action_executed": False, "writes_performed": False, "llm_authority": False}
    return {"receipt_version": "cpu_action_receipt_v1", "receipt_hash": _hash(body), "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), **body}
