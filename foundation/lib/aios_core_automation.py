"""Local-first AIOS core automation registry, sibling bundles, and plan runners.

Extends the backup_core automation pattern and integrates sibling surfaces:
systems preflight, training automation, and backup. Profiles are tagged to
``COLD_START.md`` Phases 0–8 (no parallel roadmap).

Default posture is plan-only. Bundle ``execute_safe`` runs only preflight +
UML status measurement + backup uml_lane. Never starts AIOS, never GPU_LONG,
never activates federation, never promotes bridges.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from lib.paths import FOUNDATION_ROOT, VIV_ROOT

RECEIPTS_ROOT = FOUNDATION_ROOT / "artifacts" / "auto" / "aios_core_automation"
SCHEMA_VERSION = "viv_aios_core_automation_receipt_v1"
MODULE_ID = "aios_core_automation"
VERSION = "v1"
PYTHON = VIV_ROOT.parent / ".venv" / "Scripts" / "python.exe"
BACKUP_RUNNER = FOUNDATION_ROOT / "scripts" / "run_backup_core_automation_v1.py"

# Canonical rebuild docs — do not invent a parallel roadmap.
ROADMAP_REFS = {
    "cold_start": str(VIV_ROOT / "COLD_START.md").replace("\\", "/"),
    "triangulation": str(
        FOUNDATION_ROOT / "artifacts" / "audit" / "THREE_SOURCE_REBUILD_TRIANGULATION_20260803.md"
    ).replace("\\", "/"),
    "foundation_roadmap": str(FOUNDATION_ROOT / "FOUNDATION_ROADMAP.md").replace("\\", "/"),
    "build_status": str(FOUNDATION_ROOT / "VIV_BUILD_STATUS.md").replace("\\", "/"),
}

COLD_START_PHASES: dict[int, str] = {
    0: "documentation_and_inventory",
    1: "finish_foundation_spine",
    2: "consolidate_security_and_memory",
    3: "finish_voice_contract_and_training",
    4: "migrate_knowledge_and_ingestion",
    5: "restore_perception",
    6: "identity_sovereignty_transparency",
    7: "dream_ethics_adaptive_behavior",
    8: "hardware_agnosticism_and_distributed",
}


@dataclass(frozen=True)
class AutomationProfile:
    profile_id: str
    core_id: str
    description: str
    default_mode: str  # plan_only | execute
    execute_allowed: bool
    execute_kind: str  # none | backup_delegate | closed_smoke
    planner: str
    constraints: tuple[str, ...]
    cold_start_phase: int


# Ordered by COLD_START.md phase, then profile_id.
PROFILES: tuple[AutomationProfile, ...] = (
    AutomationProfile(
        "main",
        "main_core",
        "Catalog discovery + route planning (no boot/shutdown).",
        "plan_only",
        False,
        "none",
        "lib.main_core.plan_route",
        ("no_boot", "no_shutdown", "no_handler_invoke", "no_aios_runtime"),
        0,
    ),
    AutomationProfile(
        "utils",
        "utils_core",
        "Validation/retry/path classify planning.",
        "plan_only",
        True,
        "closed_smoke",
        "lib.aios_adapter_utils.cpu_plan",
        ("no_bridge_promotion", "no_writes", "no_aios_runtime"),
        0,
    ),
    AutomationProfile(
        "enterprise",
        "enterprise_core",
        "Compliance/audit event planning via audit adapter.",
        "plan_only",
        False,
        "none",
        "lib.aios_adapter_audit.cpu_plan",
        ("no_audit_append", "no_external_integration", "smoke_needs_live_audit_log", "no_aios_runtime"),
        0,
    ),
    AutomationProfile(
        "rid",
        "rid_core",
        "Read-only RID status/snapshot observe (no stress capture).",
        "plan_only",
        False,
        "none",
        "lib.aios_adapter_rid.status",
        ("no_stress", "no_120s_capture", "no_aios_runtime"),
        1,
    ),
    AutomationProfile(
        "support",
        "support_core",
        "Diagnostic/cache planning + health observation (no stress).",
        "plan_only",
        True,
        "closed_smoke",
        "lib.aios_adapter_support.cpu_plan",
        ("no_stress", "no_aios_runtime"),
        1,
    ),
    AutomationProfile(
        "fractal",
        "fractal_core",
        "Bounded multi-scale reasoning plan.",
        "plan_only",
        True,
        "closed_smoke",
        "lib.aios_adapter_fractal.cpu_plan",
        ("no_writes", "no_aios_runtime"),
        1,
    ),
    AutomationProfile(
        "backup_uml_lane",
        "backup_core",
        "Governed UML+backup vault lane (delegates to backup runner).",
        "execute",
        True,
        "backup_delegate",
        "lib.aios_adapter_backup.plan_automation",
        ("deny_weight_packs", "no_live_restore", "no_deletion", "no_aios_runtime"),
        2,
    ),
    AutomationProfile(
        "backup_safe",
        "backup_core",
        "Governed safe sovereign+UML vault lane (delegates to backup runner).",
        "execute",
        True,
        "backup_delegate",
        "lib.aios_adapter_backup.plan_automation",
        ("deny_weight_packs", "no_live_restore", "no_deletion", "no_aios_runtime"),
        2,
    ),
    AutomationProfile(
        "carma",
        "carma_core",
        "STM/LTM + retrieval planning on fixtures (no live remember).",
        "plan_only",
        False,
        "none",
        "lib.aios_adapter_carma.cpu_plan",
        ("no_live_memory_write", "execute_needs_operator", "no_aios_runtime"),
        2,
    ),
    AutomationProfile(
        "privacy",
        "privacy_core",
        "Retention/mode/consent planning only.",
        "plan_only",
        True,
        "closed_smoke",
        "lib.aios_adapter_privacy.cpu_plan",
        ("no_delete", "no_writes", "no_aios_runtime"),
        2,
    ),
    AutomationProfile(
        "luna",
        "luna_core",
        "Identity/response communication planning only.",
        "plan_only",
        False,
        "none",
        "lib.aios_adapter_luna.communication_plan",
        ("no_speak", "no_fake_converse", "no_aios_runtime"),
        3,
    ),
    AutomationProfile(
        "data",
        "data_core",
        "Import/export/cleanup/recovery planning on fixtures.",
        "plan_only",
        True,
        "closed_smoke",
        "lib.aios_adapter_data.cpu_plan",
        ("no_storage_mutate", "no_delete", "no_aios_runtime"),
        4,
    ),
    AutomationProfile(
        "consciousness",
        "consciousness_core",
        "Isolated pulse/reflection cycle with commit hold.",
        "plan_only",
        False,
        "none",
        "lib.aios_adapter_consciousness.cpu_plan",
        ("no_durable_commit", "no_aios_runtime"),
        6,
    ),
    AutomationProfile(
        "dream",
        "dream_core",
        "Idle trigger + consolidation planning (no dream cycle execute).",
        "plan_only",
        False,
        "none",
        "lib.aios_adapter_dream.cycle_plan",
        ("no_dream_cycle_execute", "no_archive_delete", "no_aios_runtime"),
        7,
    ),
    AutomationProfile(
        "infra",
        "infra_core",
        "CI/SLO/deployment gate planning only.",
        "plan_only",
        True,
        "closed_smoke",
        "lib.aios_adapter_infra.cpu_plan",
        ("no_deploy", "no_containers", "no_network", "no_aios_runtime"),
        8,
    ),
    AutomationProfile(
        "marketplace",
        "marketplace_core",
        "Manifest trust/install-gate planning only.",
        "plan_only",
        True,
        "closed_smoke",
        "lib.aios_adapter_marketplace.cpu_plan",
        ("no_install", "no_activation", "no_network", "no_aios_runtime"),
        8,
    ),
    AutomationProfile(
        "music",
        "music_core",
        "Playlist/play-intent planning only.",
        "plan_only",
        True,
        "closed_smoke",
        "lib.aios_adapter_music.cpu_plan",
        ("no_playback", "no_library_scan", "no_aios_runtime"),
        8,
    ),
    AutomationProfile(
        "game",
        "game_core",
        "Simulation/coaching planning only.",
        "plan_only",
        True,
        "closed_smoke",
        "lib.aios_adapter_game.cpu_plan",
        ("sandbox_only", "no_aios_runtime"),
        8,
    ),
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def list_profiles() -> list[dict[str, Any]]:
    return [asdict(profile) for profile in PROFILES]


def get_profile(profile_id: str) -> AutomationProfile | None:
    key = str(profile_id or "").strip().casefold()
    for profile in PROFILES:
        if profile.profile_id.casefold() == key:
            return profile
    return None


def inventory_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile in PROFILES:
        mode = "execute" if profile.execute_allowed else "plan_only"
        if profile.execute_kind == "backup_delegate":
            command = (
                "python scripts/run_aios_core_automation_v1.py "
                f"--profile {profile.profile_id}"
            )
        else:
            command = (
                "python scripts/run_aios_core_automation_v1.py "
                f"--profile {profile.profile_id} --plan-only"
            )
        rows.append(
            {
                "core": profile.core_id,
                "profile": profile.profile_id,
                "automatable": True,
                "mode": mode if profile.execute_allowed else "plan_only",
                "default_mode": profile.default_mode,
                "execute_allowed": profile.execute_allowed,
                "execute_kind": profile.execute_kind,
                "cold_start_phase": profile.cold_start_phase,
                "cold_start_phase_name": COLD_START_PHASES.get(profile.cold_start_phase),
                "command": command,
                "constraints": list(profile.constraints),
                "description": profile.description,
            }
        )
    # Explicit gaps (present in contract map / adapters but not auto-executed here).
    gaps = (
        ("federation", False, "plan_only", 8, "loopback dry-plan only; real endpoint activation needs operator authority"),
        ("rag_core", True, "plan_only", 4, "adapter exists; wire via knowledge Phase 4 — not auto-executed"),
        ("security_core", False, "plan_only", 2, "membrane/deny authority; not an automation execute surface"),
        ("tool_core", True, "plan_only", 1, "gated tools; execute needs explicit operator tool authority"),
        ("dataset_core", True, "plan_only", 4, "indexing/provenance; large scans need operator gate"),
        ("knowledge_core", True, "plan_only", 4, "absorption routes; Phase 4 — not auto-executed"),
        ("vision_core", True, "plan_only", 5, "Phase 5 perception; not auto-executed"),
        ("slm_core", False, "plan_only", 3, "deny weight packs / gpu multi-GB; catalog only with operator gate"),
        ("nox_forge_core", True, "plan_only", 1, "FFI governor; not auto-executed"),
        ("streamlit_core", False, "plan_only", 8, "UI-only disposition"),
        ("template_core", False, "plan_only", 0, "retired disposition"),
    )
    for core_id, automatable, mode, phase, note in gaps:
        rows.append(
            {
                "core": core_id,
                "profile": None,
                "automatable": automatable,
                "mode": mode,
                "default_mode": "plan_only",
                "execute_allowed": False,
                "execute_kind": "none",
                "cold_start_phase": phase,
                "cold_start_phase_name": COLD_START_PHASES.get(phase),
                "command": None,
                "constraints": ["orchestrator_gap", "operator_authority"],
                "description": note,
            }
        )
    return rows


def phase_map() -> dict[str, Any]:
    """Summarize bundle + profile coverage against COLD_START phases."""
    by_phase: dict[str, list[str]] = {str(p): [] for p in range(9)}
    for profile in PROFILES:
        by_phase[str(profile.cold_start_phase)].append(profile.profile_id)
    return {
        "roadmap_refs": ROADMAP_REFS,
        "phases": COLD_START_PHASES,
        "profiles_by_phase": by_phase,
        "bundle": {
            "plan_only": {
                "siblings": ["systems_preflight", "training_catalog", "backup_uml_lane_plan"],
                "cold_start_phases": [0, 1, 2, 3],
                "notes": "Phase 0 inventory preflight; Phase 1–3 training catalog + Phase 2 backup plan",
            },
            "execute_safe": {
                "siblings": ["systems_preflight", "training_uml_status", "backup_uml_lane_execute"],
                "cold_start_phases": [0, 1, 2, 3],
                "notes": "No GPU_LONG, no AIOS start; backup uml_lane is the only FS-effect sibling",
            },
        },
    }


def _base_result(*, profile: AutomationProfile, mode: str, ok: bool, **fields: Any) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "schema_version": SCHEMA_VERSION,
        "module": MODULE_ID,
        "version": VERSION,
        "profile": profile.profile_id,
        "core_id": profile.core_id,
        "mode": mode,
        "cold_start_phase": profile.cold_start_phase,
        "cold_start_phase_name": COLD_START_PHASES.get(profile.cold_start_phase),
        "at": _utc(),
        "aios_runtime_started": False,
        "deny_weight_packs": True,
        "federation_activation": False,
        "bridge_promotion": False,
        "soft_0_99": False,
        "gpu_long_launched": False,
        "constraints": list(profile.constraints),
        **fields,
    }


def plan_backup(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_backup import plan_automation

    backup_profile = "uml_lane" if profile.profile_id.endswith("uml_lane") else "safe"
    plan = plan_automation(trigger=f"aios_core_automation:{profile.profile_id}", profile=backup_profile)
    # Safe lane may ABSTAIN CPU intent on .venv security_core.pyd roots while files still expand.
    files_ok = int(plan.get("file_count") or 0) > 0 and plan.get("deny_weight_packs") is True
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=files_ok,
        backup_profile=backup_profile,
        plan=plan,
        execution_approved=False,
        cpu_intent_ok=bool((plan.get("cpu_intent") or {}).get("ok")),
    )


def plan_infra(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_infra import cpu_plan

    plan = cpu_plan(
        metrics={
            "pass_rate": 1.0,
            "p95_latency_ms": 20,
            "mean_latency_ms": 10,
            "boundary_drift": 0.0,
            "recall_at_5": 1.0,
            "error_rate": 0.0,
        },
        thresholds={
            "pass_rate_min": 0.9,
            "p95_latency_max_ms": 50,
            "mean_latency_max_ms": 30,
            "boundary_drift_max": 0.01,
            "recall_at_5_min": 0.9,
            "error_rate_max": 0.05,
        },
        ci_results=[{"stage": "syntax", "ok": True}, {"stage": "tests", "ok": True}],
        target="local",
        architect_approved=False,
        rollback_reason="automation_fixture",
        baseline_available=True,
    )
    ok = plan.get("deployment_changed") is False and plan.get("writes_performed") is False
    return _base_result(profile=profile, mode="plan_only", ok=ok and bool(plan.get("ok")), plan=plan)


def plan_privacy(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_privacy import cpu_plan

    plan = cpu_plan(
        {"mode": "standard"},
        requested_mode="strict",
        explicit_consent=False,
        retention_category="conversations",
    )
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=bool(plan.get("ok")) and plan.get("writes_performed") is False,
        plan=plan,
    )


def plan_music(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_music import cpu_plan

    library = [
        {"artist": "Miles Davis", "album": "Kind of Blue", "genre": "jazz", "mood": "calm"},
        {"artist": "Metallica", "album": "Master of Puppets", "genre": "metal", "mood": "energized"},
    ]
    plan = cpu_plan(library, [{"song": library[0], "mood": "calm"}], mood="calm", play_intent=True)
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=bool(plan.get("ok")) and plan.get("playback_started") is False,
        plan=plan,
    )


def plan_marketplace(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_marketplace import cpu_plan

    catalog = [
        {
            "name": "music_core",
            "display_name": "Music Core",
            "description": "Local music playback",
            "version": "1.0.0",
            "license": "MIT",
            "price": "FREE",
            "capabilities": ["playback"],
        }
    ]
    plan = cpu_plan(catalog, query="music", install_manifest=catalog[0], installed=[], architect_approved=False)
    install = plan.get("install_plan") or {}
    ok = (
        bool(plan.get("ok"))
        and plan.get("installation_performed") is False
        and install.get("state") == "DENIED"
    )
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=ok,
        plan=plan,
        install_performed=False,
    )


def plan_game(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_game import cpu_plan

    sessions = [
        {
            "session_id": "session_1",
            "game": "Example",
            "events": [
                {"type": "death", "data": {"location": "gate", "cause": "early roll"}},
                {"type": "win", "data": {"location": "gate", "strategy": "wait then dodge"}},
            ],
        }
    ]
    plan = cpu_plan(
        sessions,
        game_name="Example",
        event_intent={"session_id": "session_1", "event_type": "milestone", "data": {"name": "first clear"}},
    )
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=bool(plan.get("ok")) and plan.get("writes_performed") is False,
        plan=plan,
    )


def plan_fractal(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_fractal import cpu_plan

    plan = cpu_plan(
        "Explain the pattern and test the bounded plan.",
        spans=[
            {"id": "explain", "cost": 10, "value": 8, "kind": "logic"},
            {"id": "test", "cost": 12, "value": 9, "kind": "refactoring"},
        ],
        observations=[{"success": 0.8}],
        cache_entries=[{"hit": True}],
        global_budget=22,
    )
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=bool(plan.get("ok")) and plan.get("writes_performed") is False,
        plan=plan,
    )


def plan_enterprise(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_audit import cpu_plan

    good_source = '''
"""A fully described fixture module."""
import logging

logger = logging.getLogger(__name__)


def answer(value: str) -> str:
    """Return the supplied value."""
    try:
        logger.info("answer")
        return value
    except ValueError as exc:
        logger.error("failed: %s", exc)
        return ""
'''
    plan = cpu_plan(
        python_source=good_source,
        python_path="foundation/lib/example.py",
        json_config={"mode": "cpu", "enabled": True, "standard": "soc2"},
        required_keys=("mode",),
        observations=[{"path": "a.py", "state": "PASS", "score": 100}],
        controls=[{"id": "CC1", "state": "PASS", "evidence": "fixture"}],
        report_type="quality",
        audit_action="core_automation_plan",
    )
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=bool(plan.get("ok")) and plan.get("audit_write_performed") is False,
        plan=plan,
    )


def plan_utils(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_utils import cpu_plan

    plan = cpu_plan(
        value={"ok": True},
        value_kind="json",
        retry={"max_retries": 3, "base_delay_seconds": 2.0, "retryable": True},
        path="L:/Continue/Viv/foundation/lib/paths.py",
        path_operation="inspect",
        allowed_roots=("L:/Continue/Viv",),
    )
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=bool(plan.get("ok")) and plan.get("execution_performed") is False,
        plan=plan,
    )


def plan_support(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_support import cpu_plan
    from lib.support_core import make_cache_entry

    plan = cpu_plan(
        [{"name": "membrane", "ok": True}],
        [
            make_cache_entry("cached fragment", cache_id="cache-one", source="fixture", hit=True),
            make_cache_entry("another fragment", cache_id="cache-two", source="fixture", hit=False),
        ],
        sample_text="support automation fixture",
    )
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=bool(plan.get("ok")) and plan.get("writes_performed") is False,
        plan=plan,
    )


def plan_data(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_data import cpu_plan
    from lib.data_core import make_record

    rows = [
        make_record(
            {"kind": "fixture"},
            record_id="auto-data-1",
            record_type="fragment",
            source="aios_core_automation",
            provenance="fixture",
            created_utc="2026-01-01T00:00:00Z",
        )
    ]
    plan = cpu_plan(rows, source="aios_core_automation", explicit_cleanup_commit=False)
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=bool(plan.get("ok")) and plan.get("writes_performed") is False,
        plan=plan,
    )


def plan_carma(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_carma import cpu_plan
    from lib.carma_core import make_fragment

    fragments = [
        make_fragment("RID stability channels are continuous values", provenance="fixture"),
        make_fragment("UML Nested PEMDAS is deterministic structure", provenance="fixture"),
    ]
    plan = cpu_plan(fragments, query="RID stability", top=2, explicit_commit=False)
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=bool(plan.get("ok")) and plan.get("writes_performed") is False,
        plan=plan,
        durable_commit_performed=False,
    )


def plan_dream(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_dream import consolidation_plan, cycle_plan

    trigger = cycle_plan(
        idle_minutes=10.0,
        active_conversation=False,
        fragments_since_last=100,
        hours_since_last=24.0,
        manual_request=False,
        pulse_bpm=0.1,
        s_n=0.8,
    )
    consolidation = consolidation_plan(
        [
            {"id": "a", "text": "Dream records preserve provenance."},
            {"id": "b", "text": "Dream records preserve provenance."},
        ]
    )
    ok = bool(consolidation.get("ok")) and consolidation.get("writes_performed") is False
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=ok,
        plan={"trigger": trigger, "consolidation": consolidation},
    )


def plan_luna(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_luna import communication_plan

    plan = communication_plan(prompt="Why does the security system need evidence?", grounded=True)
    evidence = plan.get("evidence") or {}
    ok = bool(plan.get("ok")) and evidence.get("writes_performed") is False
    return _base_result(profile=profile, mode="plan_only", ok=ok, plan=plan)


def plan_consciousness(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_consciousness import cpu_plan

    plan = cpu_plan(
        prompt="truthful system documentation",
        experience={
            "nodes": {"truth": {"weight": 1.0}, "evidence": {"weight": 1.0}},
            "edges": [("evidence", "CAUSES", "truth")],
        },
        explicit_commit=False,
    )
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=bool(plan.get("ok")) and plan.get("writes_performed") is False,
        plan=plan,
        durable_commit_performed=False,
    )


def plan_main(profile: AutomationProfile) -> dict[str, Any]:
    from lib.main_core import discover_core_catalog, plan_route
    from lib.paths import FOUNDATION_ROOT as foundation

    # Prefer Viv foundation/lib sibling inventory via contract map path, not AIOS boot.
    catalog = discover_core_catalog(foundation / "lib")
    # discover_core_catalog expects *_core dirs; foundation/lib is flat modules.
    # Build a minimal verified catalog from the automation registry instead.
    cores = [{"core_id": p.core_id, "state": "DISCOVERED", "has_handler": False} for p in PROFILES]
    synthetic = {
        "ok": True,
        "state": "VERIFIED",
        "cores": cores,
        "counts": {"discovered": len(cores), "total": len(cores)},
        "imports_performed": False,
        "execution_performed": False,
        "writes_performed": False,
    }
    route = plan_route(["support_core", "status"], synthetic, fallback_core="support_core")
    ok = bool(route.get("ok")) and route.get("handler_invoked") is False and route.get("execution_performed") is False
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=ok,
        plan={"disk_catalog_note": catalog.get("state"), "catalog": synthetic, "route": route},
    )


def plan_rid(profile: AutomationProfile) -> dict[str, Any]:
    from lib.aios_adapter_rid import status

    observed = status()
    evidence = observed.get("evidence") or {}
    ok = bool(observed.get("ok")) and evidence.get("mutates_security_core") is not True
    return _base_result(
        profile=profile,
        mode="plan_only",
        ok=ok,
        plan=observed,
        stress_started=False,
        capture_started=False,
    )


_PLAN_RUNNERS: dict[str, Callable[[AutomationProfile], dict[str, Any]]] = {
    "backup_uml_lane": plan_backup,
    "backup_safe": plan_backup,
    "infra": plan_infra,
    "privacy": plan_privacy,
    "music": plan_music,
    "marketplace": plan_marketplace,
    "game": plan_game,
    "fractal": plan_fractal,
    "enterprise": plan_enterprise,
    "utils": plan_utils,
    "support": plan_support,
    "data": plan_data,
    "carma": plan_carma,
    "dream": plan_dream,
    "luna": plan_luna,
    "consciousness": plan_consciousness,
    "main": plan_main,
    "rid": plan_rid,
}


def run_plan(profile_id: str) -> dict[str, Any]:
    profile = get_profile(profile_id)
    if profile is None:
        return {
            "ok": False,
            "error": "unknown_profile",
            "profile": profile_id,
            "aios_runtime_started": False,
            "available": [p.profile_id for p in PROFILES],
        }
    runner = _PLAN_RUNNERS.get(profile.profile_id)
    if runner is None:
        return _base_result(profile=profile, mode="plan_only", ok=False, error="plan_runner_missing")
    return runner(profile)


def run_closed_smoke(profile: AutomationProfile) -> dict[str, Any]:
    """Execute adapter run_smoke for effect-closed profiles only."""
    if profile.execute_kind != "closed_smoke":
        return _base_result(
            profile=profile,
            mode="execute",
            ok=False,
            error="execute_kind_not_closed_smoke",
            execution_approved=False,
        )
    module_name = {
        "infra": "lib.aios_adapter_infra",
        "privacy": "lib.aios_adapter_privacy",
        "music": "lib.aios_adapter_music",
        "marketplace": "lib.aios_adapter_marketplace",
        "game": "lib.aios_adapter_game",
        "fractal": "lib.aios_adapter_fractal",
        "utils": "lib.aios_adapter_utils",
        "support": "lib.aios_adapter_support",
        "data": "lib.aios_adapter_data",
    }.get(profile.profile_id)
    if not module_name:
        return _base_result(profile=profile, mode="execute", ok=False, error="smoke_module_missing")
    module = importlib.import_module(module_name)
    smoke = module.run_smoke()
    plan = run_plan(profile.profile_id)
    ok = bool(smoke.get("ok")) and bool(plan.get("ok"))
    return _base_result(
        profile=profile,
        mode="execute",
        ok=ok,
        plan=plan.get("plan"),
        smoke=smoke,
        execution_approved=True,
        note="closed_smoke_receipt_only",
    )


def _python() -> str:
    return str(PYTHON if PYTHON.is_file() else Path(sys.executable))


def _run_preflight(*, profile: str = "quick") -> dict[str, Any]:
    from lib.aios_systems_preflight import SCHEMA_VERSION as PREFLIGHT_SCHEMA
    from lib.aios_systems_preflight import build_receipt, write_receipt as write_preflight

    receipt = build_receipt(profile=profile, plan_only=True, include_foundation_health=False)
    path = write_preflight(receipt)
    ready = [row for row in (receipt.get("catalog") or []) if row.get("plan_only_ready")]
    backup_entries = [
        {
            "id": row.get("id"),
            "automation_entry": row.get("automation_entry"),
            "risk_tag": row.get("risk_tag"),
        }
        for row in (receipt.get("catalog") or [])
        if row.get("automation_entry")
    ]
    return {
        "ok": bool(receipt.get("ok")),
        "cold_start_phase": 0,
        "cold_start_phase_name": COLD_START_PHASES[0],
        "schema_version": PREFLIGHT_SCHEMA,
        "receipt": str(path).replace("\\", "/"),
        "latest": receipt.get("latest_path"),
        "counts": receipt.get("counts"),
        "plan_only_ready": ready,
        "plan_only_ready_count": len(ready),
        "automation_entries": backup_entries,
        "aios_runtime_started": False,
        "gpu_train_started": False,
    }


def _run_training_catalog() -> dict[str, Any]:
    from lib.training_automation_v1 import RISK_GPU_LONG, SCHEMA_CATALOG, catalog_jobs

    jobs = catalog_jobs()
    return {
        "ok": True,
        "cold_start_phase": 3,
        "cold_start_phase_name": COLD_START_PHASES[3],
        "mode": "catalog",
        "schema_catalog": SCHEMA_CATALOG,
        "job_count": len(jobs),
        "jobs": [
            {
                "id": j["id"],
                "title": j["title"],
                "risk": j["risk"],
                "auto_execute": j.get("auto_execute"),
                "requires_gpu_long_gate": j.get("requires_gpu_long_gate"),
            }
            for j in jobs
        ],
        "risk_counts": {
            "GPU_LONG": sum(1 for j in jobs if j["risk"] == RISK_GPU_LONG),
            "CPU_SAFE": sum(1 for j in jobs if j["risk"] == "CPU_SAFE"),
            "MEASUREMENT_ONLY": sum(1 for j in jobs if j["risk"] == "MEASUREMENT_ONLY"),
        },
        "gpu_long_launched": False,
        "aios_runtime_started": False,
    }


def _run_training_uml_status() -> dict[str, Any]:
    from lib.training_automation_v1 import collect_uml_status, write_receipt as write_training
    from lib.training_automation_v1 import _utc_stamp as training_stamp

    status = collect_uml_status()
    stamp = training_stamp()
    receipt = {
        "ok": bool(status.get("ok")),
        "mode": "execute",
        "profile": "uml_status",
        "stamp": stamp,
        "status": status,
        "survivor_sha256": (status.get("survivor") or {}).get("sha256"),
        "thesis_ladder_tip": (status.get("thesis_ladder_tip") or {}).get("tip_line"),
        "smoke_ran": False,
        "gpu_train_launched": False,
    }
    path = write_training(stamp, receipt)
    return {
        "ok": bool(receipt.get("ok")),
        "cold_start_phase": 3,
        "cold_start_phase_name": COLD_START_PHASES[3],
        "profile": "uml_status",
        "receipt": str(path).replace("\\", "/"),
        "survivor_sha256": receipt.get("survivor_sha256"),
        "thesis_ladder_tip": receipt.get("thesis_ladder_tip"),
        "gpu_long_launched": False,
        "aios_runtime_started": False,
    }


def _delegate_backup(*, plan_only: bool, backup_profile: str = "uml_lane") -> dict[str, Any]:
    cmd = [_python(), str(BACKUP_RUNNER), "--profile", backup_profile]
    if plan_only:
        cmd.append("--plan-only")
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(FOUNDATION_ROOT), check=False)
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    parsed: dict[str, Any] = {}
    if stdout:
        try:
            import json

            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = {"raw_stdout": stdout}
    ok = proc.returncode == 0 and bool(parsed.get("ok", False))
    return {
        "ok": ok,
        "cold_start_phase": 2,
        "cold_start_phase_name": COLD_START_PHASES[2],
        "mode": "plan_only" if plan_only else "execute",
        "backup_profile": backup_profile,
        "automation_entry": "scripts/run_backup_core_automation_v1.py",
        "backup_receipt": parsed.get("receipt"),
        "delegate": {
            "command": cmd,
            "returncode": proc.returncode,
            "stdout_summary": {
                k: parsed.get(k)
                for k in ("ok", "mode", "profile", "copied_items", "logical_bytes", "snapshot_id", "receipt")
                if k in parsed
            },
            "stderr_tail": stderr[-1500:] if stderr else "",
        },
        "aios_runtime_started": False,
        "deny_weight_packs": True,
        "gpu_long_launched": False,
    }


def run_bundle_plan_only(*, preflight_profile: str = "quick") -> dict[str, Any]:
    """Default integrated surface: preflight + training catalog + backup plan."""
    preflight = _run_preflight(profile=preflight_profile)
    training = _run_training_catalog()
    backup = _delegate_backup(plan_only=True, backup_profile="uml_lane")
    ok = bool(preflight.get("ok")) and bool(training.get("ok")) and bool(backup.get("ok"))
    return {
        "ok": ok,
        "schema_version": SCHEMA_VERSION,
        "module": MODULE_ID,
        "version": VERSION,
        "mode": "plan_only",
        "bundle": "integrated_plan_only",
        "at": _utc(),
        "roadmap_refs": ROADMAP_REFS,
        "phase_map": phase_map()["bundle"]["plan_only"],
        "siblings": {
            "systems_preflight": preflight,
            "training_catalog": training,
            "backup_uml_lane": backup,
        },
        "aios_runtime_started": False,
        "gpu_long_launched": False,
        "deny_weight_packs": True,
        "federation_activation": False,
        "bridge_promotion": False,
        "soft_0_99": False,
    }


def run_bundle_execute_safe(*, preflight_profile: str = "quick") -> dict[str, Any]:
    """Safe execute: preflight + uml_status + backup uml_lane (no GPU_LONG, no AIOS)."""
    preflight = _run_preflight(profile=preflight_profile)
    training = _run_training_uml_status()
    backup = _delegate_backup(plan_only=False, backup_profile="uml_lane")
    ok = bool(preflight.get("ok")) and bool(training.get("ok")) and bool(backup.get("ok"))
    return {
        "ok": ok,
        "schema_version": SCHEMA_VERSION,
        "module": MODULE_ID,
        "version": VERSION,
        "mode": "execute_safe",
        "bundle": "integrated_execute_safe",
        "at": _utc(),
        "roadmap_refs": ROADMAP_REFS,
        "phase_map": phase_map()["bundle"]["execute_safe"],
        "siblings": {
            "systems_preflight": preflight,
            "training_uml_status": training,
            "backup_uml_lane": backup,
        },
        "aios_runtime_started": False,
        "gpu_long_launched": False,
        "deny_weight_packs": True,
        "federation_activation": False,
        "bridge_promotion": False,
        "soft_0_99": False,
    }


def write_receipt(payload: dict[str, Any], *, stamp: str | None = None) -> Path:
    stamp_value = stamp or _utc_stamp()
    folder = RECEIPTS_ROOT / stamp_value
    folder.mkdir(parents=True, exist_ok=True)
    import json

    path = folder / "RECEIPT.json"
    body = dict(payload)
    body.setdefault("stamp", stamp_value)
    body.setdefault("created_at", _utc())
    body.setdefault("receipt_root", str(RECEIPTS_ROOT).replace("\\", "/"))
    body.setdefault("roadmap_refs", ROADMAP_REFS)
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8", newline="\n")
    md = folder / "RECEIPT.md"
    md.write_text(
        "\n".join(
            [
                f"# AIOS core automation receipt `{stamp_value}`",
                "",
                f"- ok: `{body.get('ok')}`",
                f"- mode: `{body.get('mode')}`",
                f"- bundle: `{body.get('bundle')}`",
                f"- profile: `{body.get('profile')}`",
                f"- core_id: `{body.get('core_id')}`",
                f"- aios_runtime_started: `{body.get('aios_runtime_started')}`",
                f"- gpu_long_launched: `{body.get('gpu_long_launched')}`",
                f"- deny_weight_packs: `{body.get('deny_weight_packs')}`",
                f"- federation_activation: `{body.get('federation_activation')}`",
                f"- bridge_promotion: `{body.get('bridge_promotion')}`",
                "",
                "Roadmap: `COLD_START.md` Phases 0–8 (no parallel roadmap).",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    latest = RECEIPTS_ROOT / "LATEST.json"
    latest.write_text(json.dumps(body, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8", newline="\n")
    return path
