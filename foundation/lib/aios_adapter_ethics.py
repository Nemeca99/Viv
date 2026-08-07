"""Ethics + adaptive-behavior skeleton — Phase 7 plan-only slot.

Dream cycle is already covered by service/dream adapters; this fills the vacant
ethics / symbiotic-adaptive slice (VIV_BUILD_STATUS §14 NONE).
Never executes adaptive loops or soft-0.99.
"""
from __future__ import annotations

from typing import Any

from lib.aios_skeleton_stub import skeleton_cpu_plan

ADAPTER_ID = "ethics_core"
REGISTRY_ID = "ethics_core"
BUS_SLOT = "ethics_plan"


def status() -> dict[str, Any]:
    return {
        "ok": True,
        "adapter": ADAPTER_ID,
        "registry_id": REGISTRY_ID,
        "build_state": "SKELETON",
        "slices": {
            "dream_cycle": {
                "build_state": "PARTIAL",
                "source": "lib.aios_adapter_dream / service_cores",
                "note": "Covered elsewhere; not duplicated here",
            },
            "ethics": {
                "build_state": "SKELETON",
                "source": None,
                "note": "Symbiotic ethics loop NONE — structural slot only",
            },
            "adaptive_behavior": {
                "build_state": "SKELETON",
                "source": None,
                "note": "Adaptive behavior loop vacant; no soft-0.99",
            },
        },
        "soft_0_99": False,
        "aios_runtime_started": False,
    }


def cpu_plan(*, slice_id: str | None = None) -> dict[str, Any]:
    st = status()
    slices = dict(st.get("slices") or {})
    if slice_id:
        if slice_id not in slices:
            return {
                "ok": False,
                "status": "skeleton",
                "build_state": "SKELETON",
                "core_id": REGISTRY_ID,
                "reason": f"unknown_slice:{slice_id}",
                "mode": "plan_only",
                "aios_runtime_started": False,
            }
        slices = {slice_id: slices[slice_id]}
    return skeleton_cpu_plan(
        core_id=REGISTRY_ID,
        role="ethics + adaptive behavior skeleton (Phase 7)",
        build_state="SKELETON",
        notes=(
            "Plan-only ethics/adaptive scaffold. Dream remains on service bus; "
            "this slot holds vacant ethics + adaptive_behavior only. No soft-0.99."
        ),
        cold_start_phase=7,
        bus_slots=[BUS_SLOT],
        extra={
            "slices": slices,
            "soft_0_99": False,
            "adaptive_loop_started": False,
            "dream_execute": False,
        },
    )


def run_smoke() -> dict[str, Any]:
    plan = cpu_plan()
    slices = (plan.get("extra") or {}).get("slices") or {}
    ok = (
        bool(plan.get("ok"))
        and plan.get("build_state") == "SKELETON"
        and "ethics" in slices
        and "adaptive_behavior" in slices
        and plan.get("extra", {}).get("soft_0_99") is False
    )
    return {
        "ok": ok,
        "state": "PASS" if ok else "INCONCLUSIVE",
        "plan": plan,
        "authority": "cpu_adapter_observation",
        "adapter_output_is_authority": False,
    }
