"""CPU-only dispatcher for the manual-defined Viv core surfaces.

The autonomous CPU can inspect a named core through a fixed adapter allowlist.
Adapters are imported from Viv's foundation only; F:/ and D:/ remain
read-only source planes and are never executed.  A probe is observational and
does not grant the adapter authority over facts, routing, or security.
"""
from __future__ import annotations

import importlib
from datetime import datetime, timezone
from typing import Any


ADAPTERS: dict[str, str] = {
    "audit_core": "lib.aios_adapter_audit",
    "backup_core": "lib.aios_adapter_backup",
    "carma_core": "lib.aios_adapter_carma",
    "consciousness_core": "lib.aios_adapter_consciousness",
    "dataset_core": "lib.aios_adapter_dataset",
    "dream_core": "lib.aios_adapter_dream",
    "input_core": "lib.aios_adapter_input",
    "knowledge_core": "lib.aios_adapter_knowledge",
    "luna_core": "lib.aios_adapter_luna",
    "mirror_core": "lib.aios_adapter_mirror",
    "nox_forge_core": "lib.aios_adapter_nox",
    "rid_core": "lib.aios_adapter_rid",
    "security_core": "lib.aios_adapter_support",
    "steel_brain_core": "lib.aios_adapter_steel",
    "support_core": "lib.aios_adapter_support",
    "tool_core": "lib.aios_adapter_tool",
    "utils_core": "lib.aios_adapter_utils",
    "vision_core": "lib.aios_adapter_vision",
}


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def adapter_for(core_id: str) -> str | None:
    return ADAPTERS.get(str(core_id).strip().casefold())


def probe(core_id: str, *, operation: str = "status") -> dict[str, Any]:
    """Call only an allowlisted read/status operation on a Viv adapter."""
    key = str(core_id).strip().casefold()
    module_name = adapter_for(key)
    if module_name is None:
        return {"ok": False, "state": "INCONCLUSIVE", "reason": "core_adapter_not_allowlisted", "core_id": key, "at": _utc()}
    if operation not in {"status", "run_smoke"}:
        return {"ok": False, "state": "DENIED", "reason": "operation_not_allowlisted", "core_id": key, "operation": operation, "at": _utc()}
    try:
        module = importlib.import_module(module_name)
        fn = getattr(module, operation, None)
        if not callable(fn):
            return {"ok": False, "state": "INCONCLUSIVE", "reason": "adapter_operation_missing", "core_id": key, "module": module_name, "operation": operation, "at": _utc()}
        result = fn()
        return {
            "ok": bool(result.get("ok")) if isinstance(result, dict) else False,
            "state": "PASS" if isinstance(result, dict) and result.get("ok") else "INCONCLUSIVE",
            "core_id": key,
            "adapter": module_name,
            "operation": operation,
            "result": result,
            "authority": "cpu_adapter_observation",
            "adapter_output_is_authority": False,
            "at": _utc(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "state": "INCONCLUSIVE", "reason": f"adapter_probe_error:{exc}", "core_id": key, "adapter": module_name, "operation": operation, "at": _utc()}


def probe_many(core_ids: list[str], *, operation: str = "status") -> dict[str, Any]:
    rows = [probe(core_id, operation=operation) for core_id in core_ids]
    counts: dict[str, int] = {}
    for row in rows:
        state = str(row.get("state"))
        counts[state] = counts.get(state, 0) + 1
    return {"ok": all(row.get("state") == "PASS" for row in rows), "count": len(rows), "counts": counts, "rows": rows, "authority": "cpu_adapter_observation", "adapter_output_is_authority": False, "at": _utc()}


def available_cores() -> list[str]:
    return sorted(ADAPTERS)

