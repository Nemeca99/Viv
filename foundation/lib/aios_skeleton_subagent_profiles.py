"""Plan-only subagent profile index mirrored from skeleton bus slots.

`subagent_spawn` is bound to ``lib.aios_subagent_v1`` (real runner).
``uml_invoke`` remains vacant for compute-core. Other slots stay SKIP index
rows unless the worker-bus profile registry covers them.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lib.aios_skeleton_bus import BUS_SLOTS

SCHEMA_VERSION = "aios_skeleton_subagent_profiles_v1"


def list_profiles() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slot in BUS_SLOTS:
        if slot == "subagent_spawn":
            rows.append(
                {
                    "profile_id": f"subagent_{slot}",
                    "bus_slot": slot,
                    "default_mode": "plan_only",
                    "execute_allowed": False,
                    "status": "BOUND",
                    "build_state": "PARTIAL",
                    "body": "aios_subagent_v1.run_subagent",
                    "constraints": (
                        "plan_only_default",
                        "no_aios_runtime",
                        "no_gpu",
                        "cpu_owned_receipts",
                    ),
                    "note": (
                        "Bound to skeleton worker bus "
                        "(lib.aios_subagent_v1 / run_aios_subagent_v1.py)."
                    ),
                }
            )
            continue
        if slot == "uml_invoke":
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
                        "reserved_for_compute_core_wire_in",
                    ),
                    "note": (
                        f"SKIP stub for bus slot `{slot}` — vacant for compute-core."
                    ),
                }
            )
            continue
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
                    "skeleton_slot_profile",
                ),
                "note": (
                    f"SKIP index row for bus slot `{slot}` — "
                    "worker-bus profiles may cover the same surface."
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
        "status": "PLAN",
        "build_state": "SKELETON",
        "schema_version": SCHEMA_VERSION,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "mode": "plan_only",
        "profiles": profiles,
        "spawned": 0,
        "aios_runtime_started": False,
        "execution_approved": False,
        "subagent_spawn_bound": True,
        "uml_invoke_vacant": True,
    }
