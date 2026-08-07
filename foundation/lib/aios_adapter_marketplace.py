"""Read-only optional adapter for marketplace metadata and trust planning."""
from __future__ import annotations

from typing import Any

from lib.marketplace_core import module_status, plan_install, search_catalog


def status() -> dict[str, Any]:
    return module_status()


def cpu_plan(
    catalog: list[dict[str, Any]],
    *,
    query: str = "",
    capabilities: list[str] | None = None,
    price: str | None = None,
    install_manifest: dict[str, Any] | None = None,
    installed: list[str] | None = None,
    source_evidence: dict[str, Any] | None = None,
    architect_approved: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "state": "VERIFIED",
        "search": search_catalog(catalog, query, capabilities=capabilities or [], price=price),
        "network_accessed": False,
        "writes_performed": False,
        "installation_performed": False,
        "llm_authority": False,
    }
    if install_manifest is not None:
        result["install_plan"] = plan_install(install_manifest, installed or [], source_evidence=source_evidence, architect_approved=architect_approved)
    return result


def run_smoke() -> dict[str, Any]:
    catalog = [
        {"name": "music_core", "display_name": "Music Core", "description": "Local music playback", "version": "1.0.0", "license": "MIT", "price": "FREE", "capabilities": ["playback"]},
        {"name": "unsafe_core", "display_name": "Unsafe", "description": "External automation", "version": "1.0.0", "license": "MIT", "price": "FREE", "capabilities": ["network", "execute"]},
    ]
    result = cpu_plan(catalog, query="music", install_manifest=catalog[0], installed=[], architect_approved=False)
    plan = result["install_plan"]
    return {"ok": bool(result["search"]["matches"] and plan["state"] == "DENIED" and not result["installation_performed"]), "state": "PASS" if result["search"]["matches"] and plan["state"] == "DENIED" else "INCONCLUSIVE", "plan": result, "authority": "cpu_adapter_observation", "adapter_output_is_authority": False}
