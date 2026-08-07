"""Skeleton security adapter — plan-only membrane observe (no Rust mutate).

Fills bus slots security_in / security_out as PARTIAL until compute core
owns the envelope end-to-end.
"""
from __future__ import annotations

from typing import Any

from lib.aios_skeleton_stub import skeleton_cpu_plan, wrap_existing_plan

ADAPTER_ID = "security_core"
REGISTRY_ID = "security_core"


def status() -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "adapter": ADAPTER_ID,
        "registry_id": REGISTRY_ID,
        "read_only": True,
        "mutates_security_core": False,
    }
    try:
        from lib.security_membrane import membrane_status  # type: ignore

        evidence["membrane"] = membrane_status()
        return {"ok": True, "evidence": evidence, "build_state": "PARTIAL"}
    except Exception:
        pass
    try:
        from lib.security_bridge import integrity_status, rust_available

        evidence["bridge"] = {
            "rust_available": bool(rust_available()),
            "integrity": integrity_status(),
        }
        return {"ok": True, "evidence": evidence, "build_state": "PARTIAL"}
    except Exception as exc:  # noqa: BLE001
        evidence["bridge_error"] = f"{type(exc).__name__}: {exc}"
        return {
            "ok": True,
            "evidence": evidence,
            "build_state": "SKELETON",
            "note": "Security surfaces present elsewhere; adapter is observe-only scaffold",
        }


def cpu_plan(**_kwargs: Any) -> dict[str, Any]:
    st = status()
    plan = skeleton_cpu_plan(
        core_id=REGISTRY_ID,
        role="Security IN/OUT membrane (skeleton observe)",
        build_state=str(st.get("build_state") or "SKELETON"),
        notes="Plan-only security slot — no authorize/mutate from skeleton map",
        cold_start_phase=1,
        bus_slots=["security_in", "security_out"],
        extra={"status": st},
        delegates_to="lib.security_membrane / Viv/security_core",
    )
    return wrap_existing_plan(plan, core_id=REGISTRY_ID, build_state=plan["build_state"])
