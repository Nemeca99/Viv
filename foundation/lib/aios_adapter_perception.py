"""Multi-sense perception skeleton — Phase 5 plan-only slot.

Covers vision / hearing / text as sense rows. Reuses existing vision_core and
input_core adapters when importable; hearing remains SKELETON (NONE in Viv).
Never opens cameras, mics, or effectors.
"""
from __future__ import annotations

from typing import Any

from lib.aios_skeleton_stub import skeleton_cpu_plan

ADAPTER_ID = "perception_core"
REGISTRY_ID = "perception_core"
BUS_SLOT = "perception_plan"


def _sense_row(sense: str, *, build_state: str, source: str | None, note: str) -> dict[str, Any]:
    return {
        "sense": sense,
        "build_state": build_state,
        "status": "skeleton" if build_state == "SKELETON" else build_state.lower(),
        "source": source,
        "note": note,
        "capture_started": False,
        "effector_used": False,
    }


def _probe_senses() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    # Vision — real adapter exists (artifact image meta only).
    try:
        from lib.aios_adapter_vision import status as vision_status

        st = vision_status()
        ok = bool(st.get("ok"))
        rows.append(
            _sense_row(
                "vision",
                build_state="PARTIAL" if ok else "SKELETON",
                source="lib.aios_adapter_vision",
                note="Artifact image meta only; no V2 effector/foveal/stereo",
            )
        )
    except Exception:  # noqa: BLE001 — skeleton stay fail-soft
        rows.append(
            _sense_row(
                "vision",
                build_state="SKELETON",
                source=None,
                note="vision adapter unavailable",
            )
        )

    # Hearing — no Viv pipeline (VIV_BUILD_STATUS §10 NONE).
    rows.append(
        _sense_row(
            "hearing",
            build_state="SKELETON",
            source=None,
            note="Hearing/audio pipeline NONE in Viv; structural slot only",
        )
    )

    # Text / event normalize — input_core adapter present.
    try:
        from lib.aios_adapter_input import status as input_status

        st = input_status()
        ok = bool(st.get("ok"))
        rows.append(
            _sense_row(
                "text",
                build_state="PARTIAL" if ok else "SKELETON",
                source="lib.aios_adapter_input",
                note="Inbox + ingress_gate normalize; no multimodal V2 absorb",
            )
        )
    except Exception:  # noqa: BLE001
        rows.append(
            _sense_row(
                "text",
                build_state="SKELETON",
                source=None,
                note="input adapter unavailable",
            )
        )

    return rows


def status() -> dict[str, Any]:
    senses = _probe_senses()
    return {
        "ok": True,
        "adapter": ADAPTER_ID,
        "registry_id": REGISTRY_ID,
        "build_state": "SKELETON",
        "senses": senses,
        "sense_count": len(senses),
        "aios_runtime_started": False,
    }


def cpu_plan(*, sense: str | None = None) -> dict[str, Any]:
    senses = _probe_senses()
    if sense:
        senses = [s for s in senses if s["sense"] == sense]
        if not senses:
            return {
                "ok": False,
                "status": "skeleton",
                "build_state": "SKELETON",
                "core_id": REGISTRY_ID,
                "reason": f"unknown_sense:{sense}",
                "mode": "plan_only",
                "aios_runtime_started": False,
            }
    return skeleton_cpu_plan(
        core_id=REGISTRY_ID,
        role="multi-sense perception skeleton (Phase 5)",
        build_state="SKELETON",
        notes=(
            "Plan-only multi-sense scaffold. Vision/text may report PARTIAL via "
            "existing adapters; hearing is SKELETON. No capture, no effector."
        ),
        cold_start_phase=5,
        bus_slots=[BUS_SLOT],
        extra={
            "senses": senses,
            "federation_activation": False,
            "capture_started": False,
        },
    )


def run_smoke() -> dict[str, Any]:
    plan = cpu_plan()
    senses = (plan.get("extra") or {}).get("senses") or []
    ok = bool(plan.get("ok")) and len(senses) >= 3 and plan.get("build_state") == "SKELETON"
    return {
        "ok": ok,
        "state": "PASS" if ok else "INCONCLUSIVE",
        "plan": plan,
        "authority": "cpu_adapter_observation",
        "adapter_output_is_authority": False,
    }
