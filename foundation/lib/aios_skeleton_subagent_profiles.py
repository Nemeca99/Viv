"""Plan-only SKIP subagent profiles for every skeleton bus slot.

Bodies are intentionally empty — compute-core wire-in later. Never spawns.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lib.aios_skeleton_bus import BUS_SLOTS

SCHEMA_VERSION = "aios_skeleton_subagent_profiles_v1"


def list_profiles() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slot in BUS_SLOTS:
        rows.append(
            {
                "profile_id": f"subagent_{slot}",
                "bus_slot": slot,
                "default_mode": "plan_only",
                "execute_allowed": False,
                "status": "SKIP",
                "build_state": "SKELETON",
                "body": "plan_only_SKIP",
                "constraints": (
                    "no_spawn",
                    "no_aios_runtime",
                    "no_gpu",
                    "reserved_for_compute_core_wire_in"
                    if slot in {"uml_invoke", "subagent_spawn"}
                    else "skeleton_slot_profile",
                ),
                "note": (
                    f"SKIP stub for bus slot `{slot}` — no spawn until compute core binds."
                ),
            }
        )
    return rows


def plan_only(*, slot: str | None = None) -> dict[str, Any]:
    profiles = list_profiles()
    if slot:
        profiles = [p for p in profiles if p["bus_slot"] == slot]
        if not profiles:
            return {
                "ok": False,
                "status": "SKIP",
                "build_state": "SKELETON",
                "reason": f"unknown_slot:{slot}",
                "aios_runtime_started": False,
            }
    return {
        "ok": True,
        "status": "SKIP",
        "build_state": "SKELETON",
        "schema_version": SCHEMA_VERSION,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "mode": "plan_only",
        "profiles": profiles,
        "spawned": 0,
        "aios_runtime_started": False,
        "execution_approved": False,
    }
