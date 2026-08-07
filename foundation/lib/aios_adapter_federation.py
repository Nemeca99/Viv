"""Federation / node / distributed skeleton — Phase 8 plan-only slot.

Reuses existing node_federation* protocol modules for presence/readiness survey.
Never activates endpoints, opens sockets, or contacts peers.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.aios_skeleton_stub import skeleton_cpu_plan

ADAPTER_ID = "federation_core"
REGISTRY_ID = "federation_core"
BUS_SLOT = "federation_plan"

_LIB = Path(__file__).resolve().parent
_MARKERS = (
    "node_federation.py",
    "node_federation_loopback.py",
    "node_federation_readiness.py",
    "node_federation_activation_readiness.py",
    "node_federation_transport.py",
)


def _module_presence() -> dict[str, Any]:
    markers = {name: (_LIB / name).is_file() for name in _MARKERS}
    return {
        "markers": markers,
        "marker_hits": sum(1 for v in markers.values() if v),
        "marker_total": len(markers),
        "activation_allowed": False,
        "network_contact": False,
        "note": (
            "node_federation* protocol surface present; adapter is plan-only "
            "HOLD — real endpoint activation needs operator authority"
        ),
    }


def status() -> dict[str, Any]:
    presence = _module_presence()
    return {
        "ok": True,
        "adapter": ADAPTER_ID,
        "registry_id": REGISTRY_ID,
        "build_state": "SKELETON",
        "presence": presence,
        "federation_activation": False,
        "aios_runtime_started": False,
    }


def cpu_plan(*, loopback_only: bool = True) -> dict[str, Any]:
    presence = _module_presence()
    # Optional read-only contract path probe (no mutation).
    contract_present = False
    try:
        from lib.node_federation import DEFAULT_FEDERATION_CONTRACT

        contract_present = Path(DEFAULT_FEDERATION_CONTRACT).is_file()
    except Exception:  # noqa: BLE001
        contract_present = False

    return skeleton_cpu_plan(
        core_id=REGISTRY_ID,
        role="federation / node / distributed skeleton (Phase 8)",
        build_state="SKELETON",
        notes=(
            "Plan-only federation slot. Loopback dry-plan posture; no peer contact, "
            "no activation, no deploy. Reuses node_federation* modules as evidence."
        ),
        cold_start_phase=8,
        bus_slots=[BUS_SLOT],
        delegates_to="lib.node_federation*",
        extra={
            "presence": presence,
            "contract_present": contract_present,
            "loopback_only": bool(loopback_only),
            "federation_activation": False,
            "network_accessed": False,
            "decision": "HOLD",
        },
    )


def run_smoke() -> dict[str, Any]:
    plan = cpu_plan()
    presence = (plan.get("extra") or {}).get("presence") or {}
    hits = int(presence.get("marker_hits") or 0)
    ok = (
        bool(plan.get("ok"))
        and plan.get("build_state") == "SKELETON"
        and hits >= 3
        and plan.get("extra", {}).get("federation_activation") is False
    )
    return {
        "ok": ok,
        "state": "PASS" if ok else "INCONCLUSIVE",
        "plan": plan,
        "authority": "cpu_adapter_observation",
        "adapter_output_is_authority": False,
    }
