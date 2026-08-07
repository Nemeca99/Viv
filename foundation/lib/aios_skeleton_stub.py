"""Shared skeleton / stub helpers for AIOS structural coverage.

Honest emptiness: plans declare ``status: skeleton`` and ``build_state:
SKELETON|STUB|PARTIAL``. Never claim BUILT from these helpers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def skeleton_cpu_plan(
    *,
    core_id: str,
    role: str | None = None,
    build_state: str = "SKELETON",
    notes: str | None = None,
    delegates_to: str | None = None,
    cold_start_phase: int | None = None,
    bus_slots: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a structured plan-only skeleton response for a missing or thin core."""
    state = str(build_state or "SKELETON").upper()
    if state not in {"SKELETON", "STUB", "PARTIAL"}:
        state = "SKELETON"
    out: dict[str, Any] = {
        "ok": True,
        "status": "skeleton" if state == "SKELETON" else state.lower(),
        "build_state": state,
        "core_id": core_id,
        "role": role,
        "mode": "plan_only",
        "at": _utc(),
        "notes": notes
        or (
            "Structural scaffold only — flesh later. Compute core (UML Nested-PEMDAS "
            "+ RID/PID plant + mouth/security surfaces) wires in via aios_skeleton_bus."
        ),
        "delegates_to": delegates_to,
        "cold_start_phase": cold_start_phase,
        "bus_slots": list(bus_slots or []),
        "aios_runtime_started": False,
        "execution_approved": False,
        "writes_performed": False,
        "llm_authority": False,
        "gpu_train_started": False,
        "soft_0_99": False,
    }
    if extra:
        out["extra"] = dict(extra)
    return out


def wrap_existing_plan(
    plan: dict[str, Any],
    *,
    core_id: str,
    build_state: str = "PARTIAL",
    delegates_to: str | None = None,
) -> dict[str, Any]:
    """Annotate an existing planner result as skeleton-map compatible."""
    out = dict(plan) if isinstance(plan, dict) else {"wrapped": plan}
    out.setdefault("ok", True)
    out.setdefault("core_id", core_id)
    out.setdefault("status", "partial" if build_state == "PARTIAL" else "skeleton")
    out["build_state"] = str(build_state).upper()
    out.setdefault("mode", "plan_only")
    out.setdefault("aios_runtime_started", False)
    out.setdefault("execution_approved", False)
    out.setdefault("writes_performed", False)
    out.setdefault("llm_authority", False)
    if delegates_to:
        out["delegates_to"] = delegates_to
    out.setdefault("at", _utc())
    return out
