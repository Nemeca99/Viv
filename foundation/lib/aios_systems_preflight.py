"""Plan-only AIOS systems preflight catalog — discovery + readiness probes.

Never starts the AIOS runtime, never GPU-trains, never executes core automation.
Backup automation is listed as an entry point only (not duplicated).
"""
from __future__ import annotations

import importlib
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.aios_systems import adapter_file_map, registered_core_specs
from lib.paths import AUTO_ARTIFACTS, FOUNDATION_ROOT, VIV_ROOT

SCHEMA_VERSION = "aios_systems_preflight_receipt_v1"
PREFLIGHT_DIR = AUTO_ARTIFACTS / "aios_systems_preflight"
SCRIPTS_DIR = FOUNDATION_ROOT / "scripts"
LIB_DIR = FOUNDATION_ROOT / "lib"

# Adapters present on disk but not yet in aios_systems._ADAPTER_FILES.
_EXTRA_ADAPTER_FILES: dict[str, str] = {
    "audit_core": "aios_adapter_audit.py",
    "carma_core": "aios_adapter_carma.py",
    "consciousness_core": "aios_adapter_consciousness.py",
    "dream_core": "aios_adapter_dream.py",
    "knowledge_core": "aios_adapter_knowledge.py",
    "rag_core": "aios_adapter_knowledge.py",
    "luna_core": "aios_adapter_luna.py",
    "mirror_core": "aios_adapter_mirror.py",
    "privacy_core": "aios_adapter_privacy.py",
    "rid_core": "aios_adapter_rid.py",
    "steel_brain_core": "aios_adapter_steel.py",
}

# Existing automation runners — list only; do not reimplement.
_AUTOMATION_ENTRIES: dict[str, str] = {
    "backup_core": "scripts/run_backup_core_automation_v1.py",
}

_OPTIONAL_IDS = frozenset({"marketplace_core", "music_core"})
_GPU_ADJACENT_IDS = frozenset({"slm_core"})
_RUNTIME_IDS = frozenset({"main_core", "consciousness_core"})

# Quick profile: high-priority / adapter-backed skeleton (excludes deferred).
_QUICK_PRIORITY_MAX = 40


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _posix(path: Path | str) -> str:
    return str(path).replace("\\", "/")


# Canonical roadmap surfaces — map into receipts; do not invent a parallel roadmap.
ROADMAP_REFS: dict[str, str] = {
    "cold_start": _posix(VIV_ROOT / "COLD_START.md"),
    "triangulation": _posix(
        FOUNDATION_ROOT / "artifacts" / "audit" / "THREE_SOURCE_REBUILD_TRIANGULATION_20260803.md"
    ),
    "foundation_roadmap": _posix(FOUNDATION_ROOT / "FOUNDATION_ROADMAP.md"),
    "viv_build_status": _posix(FOUNDATION_ROOT / "VIV_BUILD_STATUS.md"),
}

# COLD_START.md §7 phase labels (authoritative names).
COLD_START_PHASES: dict[int, str] = {
    0: "documentation and inventory",
    1: "finish the foundation spine",
    2: "consolidate security and memory",
    3: "finish the voice contract and training",
    4: "migrate knowledge and open-source ingestion",
    5: "restore perception one sense at a time",
    6: "identity, sovereignty, and transparency",
    7: "dream, ethics, and adaptive behavior",
    8: "hardware agnosticism and distributed systems",
}

# Per-core mapping derived from COLD_START §7 + VIV_BUILD_STATUS section rows
# + triangulation migration disposition. Status values use the VIV_BUILD_STATUS legend.
_ROADMAP_BY_CORE: dict[str, dict[str, Any]] = {
    "backup_core": {
        "cold_start_phase": 0,
        "viv_build_status_row": "OpenAster / hardening — AIOS backup core",
        "viv_build_status": "BUILT",
        "foundation_layer": "foundation_ops",
        "triangulation_disposition": "Preserve reversible backup workflow; do not replace security controls",
    },
    "support_core": {
        "cold_start_phase": 0,
        "viv_build_status_row": "§5 Software Architecture",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "lib_spine",
        "triangulation_disposition": "Inventory/ops surface; defer enterprise monitoring until spine solid",
    },
    "utils_core": {
        "cold_start_phase": 0,
        "viv_build_status_row": "§5 Software Architecture",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "lib_spine",
        "triangulation_disposition": "Bridges/monitoring utils — inventory first",
    },
    "tools": {
        "cold_start_phase": 0,
        "viv_build_status_row": "§5 Software Architecture",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "lib_spine",
        "triangulation_disposition": "Dev tooling; keep package isolation",
    },
    "template_core": {
        "cold_start_phase": 0,
        "viv_build_status_row": "§18 Final Goal",
        "viv_build_status": "NONE",
        "foundation_layer": "deferred",
        "triangulation_disposition": "Deferred plugin template — not current Alpha surface",
    },
    "streamlit_core": {
        "cold_start_phase": 0,
        "viv_build_status_row": "§18 Final Goal",
        "viv_build_status": "NONE",
        "foundation_layer": "deferred",
        "triangulation_disposition": "UI deferred until foundation/knowledge/mouth path solid",
    },
    "rid_core": {
        "cold_start_phase": 1,
        "viv_build_status_row": "§2 RID Physics Engine",
        "viv_build_status": "BUILT",
        "foundation_layer": "three_mains",
        "triangulation_disposition": "Canonical plant/RID authority in Viv",
    },
    "main_core": {
        "cold_start_phase": 1,
        "viv_build_status_row": "§5 Software Architecture",
        "viv_build_status": "BUILT",
        "foundation_layer": "three_mains",
        "triangulation_disposition": "Three-main ownership; no broad implicit plugin kernel",
    },
    "security_core": {
        "cold_start_phase": 1,
        "viv_build_status_row": "§8 Constitutional Framework",
        "viv_build_status": "BUILT",
        "foundation_layer": "security_envelope",
        "triangulation_disposition": "Viv Rust membrane is authority; do not restore V1 file locks",
    },
    "tool_core": {
        "cold_start_phase": 1,
        "viv_build_status_row": "§5 Software Architecture",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "security_envelope",
        "triangulation_disposition": "Gated read/write/list/run via security_membrane",
    },
    "data_core": {
        "cold_start_phase": 1,
        "viv_build_status_row": "§5 Software Architecture",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "foundation_ops",
        "triangulation_disposition": "Artifact/session stores under Viv evidence roots",
    },
    "containment": {
        "cold_start_phase": 2,
        "viv_build_status_row": "§8 Constitutional Framework",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "security_envelope",
        "triangulation_disposition": "Filesystem boundary; align with Security IN/OUT",
    },
    "carma_core": {
        "cold_start_phase": 2,
        "viv_build_status_row": "§6 Memory System (CARMA)",
        "viv_build_status": "BUILT",
        "foundation_layer": "memory",
        "triangulation_disposition": "Port formats through provenance; do not import unverified vector hot path",
    },
    "privacy_core": {
        "cold_start_phase": 2,
        "viv_build_status_row": "§11 Security & Identity",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "security_envelope",
        "triangulation_disposition": "Consent/retention policy under Security envelope",
    },
    "nox_forge_core": {
        "cold_start_phase": 2,
        "viv_build_status_row": "§5 Software Architecture",
        "viv_build_status": "LEGACY",
        "foundation_layer": "security_envelope",
        "triangulation_disposition": "Legacy Rust governor reference; port into Viv security_core only",
    },
    "luna_core": {
        "cold_start_phase": 3,
        "viv_build_status_row": "§7 Stateless Voice (GPU)",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "gpu_voice",
        "triangulation_disposition": "Preserve identity goals; do not give GPU free-form authority",
    },
    "consciousness_core": {
        "cold_start_phase": 3,
        "viv_build_status_row": "§1 Core Philosophy",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "gpu_voice",
        "triangulation_disposition": "Identity language without unproven consciousness claims",
    },
    "slm_core": {
        "cold_start_phase": 3,
        "viv_build_status_row": "§7 Stateless Voice (GPU)",
        "viv_build_status": "NONE",
        "foundation_layer": "training",
        "triangulation_disposition": "Deferred SLM lane; no GPU train from this preflight",
    },
    "knowledge_core": {
        "cold_start_phase": 4,
        "viv_build_status_row": "§12 Knowledge & Open Source",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "knowledge",
        "triangulation_disposition": "Knowledge contract/provenance first; read-only seam before corpus admit",
    },
    "rag_core": {
        "cold_start_phase": 4,
        "viv_build_status_row": "§12 Knowledge & Open Source",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "knowledge",
        "triangulation_disposition": "Port retrieval discipline; add hashes/freshness/cannot-verify",
    },
    "dataset_core": {
        "cold_start_phase": 4,
        "viv_build_status_row": "§12 Knowledge & Open Source",
        "viv_build_status": "LEGACY",
        "foundation_layer": "knowledge",
        "triangulation_disposition": "Legacy global index; absorb via staging only",
    },
    "steel_brain_core": {
        "cold_start_phase": 4,
        "viv_build_status_row": "§12 Knowledge & Open Source",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "knowledge",
        "triangulation_disposition": "CPU steel_judge live; 3-LLM refinery remains LEGACY",
    },
    "vision_core": {
        "cold_start_phase": 5,
        "viv_build_status_row": "§9 Vision System",
        "viv_build_status": "LEGACY",
        "foundation_layer": "perception",
        "triangulation_disposition": "Port after text perception; no autonomous action from labels",
    },
    "input_core": {
        "cold_start_phase": 5,
        "viv_build_status_row": "§16 Perception (Sight / Sound / Text)",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "perception",
        "triangulation_disposition": "Multimodal normalizer; text-first through UML/security",
    },
    "audit_core": {
        "cold_start_phase": 6,
        "viv_build_status_row": "§13 Sovereignty & Transparency",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "sovereignty",
        "triangulation_disposition": "Audit concepts only where they fit backup/rollback gates",
    },
    "mirror_core": {
        "cold_start_phase": 6,
        "viv_build_status_row": "§13 Sovereignty & Transparency",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "sovereignty",
        "triangulation_disposition": "Introspection/dashboard; keep decision receipts factual",
    },
    "governance_core": {
        "cold_start_phase": 6,
        "viv_build_status_row": "§11 Security & Identity",
        "viv_build_status": "NONE",
        "foundation_layer": "sovereignty",
        "triangulation_disposition": "Deferred courtroom vote bus",
    },
    "inbox_outbox": {
        "cold_start_phase": 6,
        "viv_build_status_row": "§13 Sovereignty & Transparency",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "sovereignty",
        "triangulation_disposition": "Message I/O lanes under governed evidence",
    },
    "dream_core": {
        "cold_start_phase": 7,
        "viv_build_status_row": "§15 Dream Cycle",
        "viv_build_status": "BUILT",
        "foundation_layer": "dream_ethics",
        "triangulation_disposition": "Compare provenance preservation; keep dream writes reversible",
    },
    "infra_core": {
        "cold_start_phase": 8,
        "viv_build_status_row": "§17 Hardware Agnosticism",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "hardware_distributed",
        "triangulation_disposition": "CI/deploy/rollback planning; defer multi-node",
    },
    "fractal_core": {
        "cold_start_phase": 8,
        "viv_build_status_row": "§5 Software Architecture",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "hardware_distributed",
        "triangulation_disposition": "Multi-scale reasoner; later Rest-of-AIOS slice",
    },
    "game_core": {
        "cold_start_phase": 8,
        "viv_build_status_row": "§18 Final Goal",
        "viv_build_status": "PARTIAL",
        "foundation_layer": "rest_of_aios",
        "triangulation_disposition": "Optional coaching/analytics; not foundation gate",
    },
    "marketplace_core": {
        "cold_start_phase": 8,
        "viv_build_status_row": "§18 Final Goal",
        "viv_build_status": "NONE",
        "foundation_layer": "rest_of_aios",
        "triangulation_disposition": "Optional plugin discovery; installation closed",
    },
    "music_core": {
        "cold_start_phase": 8,
        "viv_build_status_row": "§18 Final Goal",
        "viv_build_status": "NONE",
        "foundation_layer": "rest_of_aios",
        "triangulation_disposition": "Optional music policy; playback closed",
    },
}


def roadmap_mapping_for(core_id: str) -> dict[str, Any]:
    """Attach COLD_START phase + VIV_BUILD_STATUS row for a subsystem id."""
    base = _ROADMAP_BY_CORE.get(str(core_id))
    if base is None:
        # Unknown/orphan adapters: inventory (Phase 0) until explicitly placed.
        phase = 0
        mapping = {
            "cold_start_phase": phase,
            "viv_build_status_row": "§5 Software Architecture",
            "viv_build_status": "PARTIAL",
            "foundation_layer": "unmapped_adapter",
            "triangulation_disposition": "Discovered adapter — place via COLD_START inventory before execute",
        }
    else:
        mapping = dict(base)
        phase = int(mapping["cold_start_phase"])
    mapping["cold_start_phase_label"] = COLD_START_PHASES.get(phase, "unknown")
    mapping["roadmap_sources"] = [
        "COLD_START.md§7",
        "VIV_BUILD_STATUS.md",
        "FOUNDATION_ROADMAP.md",
        "THREE_SOURCE_REBUILD_TRIANGULATION_20260803.md",
    ]
    return mapping


def attach_roadmap_fields(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out.update(roadmap_mapping_for(str(row.get("id") or "")))
    return out


def summarize_phase_mapping(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    by_phase: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_section: dict[str, int] = {}
    by_layer: dict[str, int] = {}
    for row in catalog:
        phase = str(row.get("cold_start_phase"))
        by_phase[phase] = by_phase.get(phase, 0) + 1
        status = str(row.get("viv_build_status") or "UNKNOWN")
        by_status[status] = by_status.get(status, 0) + 1
        section = str(row.get("viv_build_status_row") or "UNKNOWN")
        by_section[section] = by_section.get(section, 0) + 1
        layer = str(row.get("foundation_layer") or "unknown")
        by_layer[layer] = by_layer.get(layer, 0) + 1
    return {
        "by_cold_start_phase": dict(sorted(by_phase.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 99)),
        "by_viv_build_status": dict(sorted(by_status.items())),
        "by_viv_build_status_row": dict(sorted(by_section.items())),
        "by_foundation_layer": dict(sorted(by_layer.items())),
        "cold_start_phase_labels": {
            str(k): v for k, v in sorted(COLD_START_PHASES.items())
        },
    }


def resolve_adapter_map() -> dict[str, str]:
    """Merge registry map + extras + on-disk adapter basename inference."""
    merged = dict(adapter_file_map())
    for core_id, filename in _EXTRA_ADAPTER_FILES.items():
        merged.setdefault(core_id, filename)
    for path in sorted(LIB_DIR.glob("aios_adapter_*.py")):
        stem = path.stem  # aios_adapter_foo
        suffix = stem.removeprefix("aios_adapter_")
        if not suffix:
            continue
        # Prefer explicit maps; only invent core_id when unused.
        guessed = f"{suffix}_core" if not suffix.endswith("_core") else suffix
        if guessed == "tool_core" or suffix == "tool":
            merged.setdefault("tool_core", path.name)
            merged.setdefault("tools", path.name)
            continue
        if suffix == "steel":
            merged.setdefault("steel_brain_core", path.name)
            continue
        if suffix == "carma":
            merged.setdefault("carma_core", path.name)
            continue
        if suffix == "knowledge":
            merged.setdefault("knowledge_core", path.name)
            merged.setdefault("rag_core", path.name)
            continue
        owners = [cid for cid, fn in merged.items() if fn == path.name]
        if not owners:
            merged.setdefault(guessed, path.name)
    return merged


def discover_systems(*, profile: str = "quick") -> list[dict[str, Any]]:
    """Return catalog seed rows for the requested profile (no imports yet)."""
    if profile not in {"quick", "full"}:
        raise ValueError(f"unsupported profile: {profile}")

    adapter_map = resolve_adapter_map()
    specs = registered_core_specs()
    by_id = {str(row["id"]): dict(row) for row in specs}

    # Orphan adapters: files mapped to cores not in the registry.
    for core_id, filename in adapter_map.items():
        if core_id in by_id:
            continue
        by_id[core_id] = {
            "id": core_id,
            "role": f"adapter-discovered ({filename})",
            "priority": 70,
            "deferred": False,
            "viv": f"foundation/lib/{filename}",
            "generations": ["adapter"],
        }

    rows: list[dict[str, Any]] = []
    for core_id, spec in sorted(by_id.items(), key=lambda item: (int(item[1].get("priority") or 99), item[0])):
        filename = adapter_map.get(core_id)
        adapter_path = (LIB_DIR / filename) if filename else None
        has_adapter_file = bool(adapter_path and adapter_path.is_file())
        deferred = bool(spec.get("deferred"))
        priority = int(spec.get("priority") or 99)

        if profile == "quick":
            include = (not deferred) and (priority <= _QUICK_PRIORITY_MAX or has_adapter_file)
            # Always keep backup_core — spine automation inventory.
            if core_id == "backup_core":
                include = True
            if not include:
                continue

        rows.append(
            attach_roadmap_fields(
                {
                    "id": core_id,
                    "role": spec.get("role"),
                    "priority": priority,
                    "deferred": deferred,
                    "viv": spec.get("viv"),
                    "generations": list(spec.get("generations") or []),
                    "adapter_filename": filename,
                    "adapter_path": _posix(adapter_path.relative_to(FOUNDATION_ROOT))
                    if has_adapter_file and adapter_path
                    else None,
                    "adapter_module": f"lib.{Path(filename).stem}" if filename and has_adapter_file else None,
                    "automation_entry": _AUTOMATION_ENTRIES.get(core_id),
                }
            )
        )
    return rows


def _find_tests(core_id: str, adapter_filename: str | None) -> list[str]:
    """Locate known selftests / cpu_plan tests without executing them."""
    found: list[Path] = []
    stems: list[str] = []
    if adapter_filename:
        stem = Path(adapter_filename).stem.removeprefix("aios_adapter_")
        stems.append(stem)
        stems.append(f"{stem}_adapter")
    short = core_id.removesuffix("_core")
    stems.extend([core_id, short, f"{short}_adapter", f"{core_id}_adapter"])
    # de-dupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for s in stems:
        if s and s not in seen:
            seen.add(s)
            ordered.append(s)

    patterns: list[str] = []
    for s in ordered:
        patterns.extend(
            [
                f"test_{s}_cpu_plan_v1.py",
                f"test_{s}_adapter_cpu_plan_v1.py",
                f"test_{s}_*.py",
            ]
        )
    # Explicit common names
    if core_id == "backup_core":
        patterns = [
            "test_backup_adapter_cpu_plan_v1.py",
            "test_backup_core_automation_v1.py",
            *patterns,
        ]
    if core_id == "carma_core":
        patterns = ["test_carma_adapter_cpu_plan_v1.py", *patterns]

    matched: set[str] = set()
    for pattern in patterns:
        for path in SCRIPTS_DIR.glob(pattern):
            key = _posix(path)
            if key in matched:
                continue
            matched.add(key)
            found.append(path)
    return [_posix(p.relative_to(FOUNDATION_ROOT)) for p in found]


def _risk_tag(row: dict[str, Any], *, importable: bool, has_cpu_plan: bool) -> str:
    core_id = str(row["id"])
    if row.get("deferred"):
        return "deferred"
    if core_id in _GPU_ADJACENT_IDS:
        return "gpu_adjacent"
    if core_id in _OPTIONAL_IDS:
        return "optional"
    if core_id in _RUNTIME_IDS:
        return "runtime_kernel"
    if core_id == "backup_core" and row.get("automation_entry"):
        return "automation_listed"
    if importable and has_cpu_plan:
        return "safe_cpu_plan"
    if importable and not has_cpu_plan:
        return "adapter_no_cpu_plan"
    if row.get("adapter_filename") and not importable:
        return "adapter_import_failed"
    return "legacy_unwired"


def probe_system(row: dict[str, Any]) -> dict[str, Any]:
    """Import-check one system. Never calls cpu_plan / status / automation."""
    out = dict(row)
    out["importable"] = False
    out["has_cpu_plan"] = False
    out["has_tests"] = False
    out["test_paths"] = []
    out["import_error"] = None
    out["cpu_plan_signature"] = None

    module_name = row.get("adapter_module")
    if module_name:
        try:
            mod = importlib.import_module(str(module_name))
            out["importable"] = True
            fn = getattr(mod, "cpu_plan", None)
            if callable(fn):
                out["has_cpu_plan"] = True
                try:
                    out["cpu_plan_signature"] = str(inspect.signature(fn))
                except (TypeError, ValueError):
                    out["cpu_plan_signature"] = "<uninspectable>"
        except Exception as exc:  # noqa: BLE001 — catalog must record failures
            out["import_error"] = f"{type(exc).__name__}: {exc}"

    tests = _find_tests(str(row["id"]), row.get("adapter_filename"))
    out["test_paths"] = tests
    out["has_tests"] = bool(tests)
    out["risk_tag"] = _risk_tag(out, importable=bool(out["importable"]), has_cpu_plan=bool(out["has_cpu_plan"]))
    out["plan_only_ready"] = bool(
        out["importable"]
        and out["has_cpu_plan"]
        and not out.get("deferred")
        and out["risk_tag"] not in {"gpu_adjacent", "adapter_import_failed"}
    )
    return out


def summarize_catalog(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    by_risk: dict[str, int] = {}
    for row in catalog:
        tag = str(row.get("risk_tag") or "unknown")
        by_risk[tag] = by_risk.get(tag, 0) + 1
    return {
        "systems_total": len(catalog),
        "importable": sum(1 for r in catalog if r.get("importable")),
        "has_cpu_plan": sum(1 for r in catalog if r.get("has_cpu_plan")),
        "has_tests": sum(1 for r in catalog if r.get("has_tests")),
        "plan_only_ready": sum(1 for r in catalog if r.get("plan_only_ready")),
        "with_automation_entry": sum(1 for r in catalog if r.get("automation_entry")),
        "by_risk": dict(sorted(by_risk.items())),
        "phase_mapping": summarize_phase_mapping(catalog),
    }


def optional_foundation_health(*, include_stress: bool = False) -> dict[str, Any]:
    """Cheap foundation gate. Stress is off unless explicitly requested."""
    from lib.foundation_health import evaluate_foundation_gate

    report = evaluate_foundation_gate(include_stress=include_stress)
    return {
        "ran": True,
        "include_stress": include_stress,
        "ok": bool(report.get("allow")),
        "failed": report.get("failed") or [],
        "checks": report.get("checks") or [],
    }


def build_receipt(
    *,
    profile: str = "quick",
    plan_only: bool = True,
    include_foundation_health: bool = False,
    stamp: str | None = None,
) -> dict[str, Any]:
    """Build a machine-readable preflight receipt (plan-only by default)."""
    if not plan_only:
        # Execute mode is intentionally unsupported — this is a catalog gate.
        raise ValueError("aios_systems_preflight only supports plan_only=True")

    stamp = stamp or _utc_stamp()
    seeds = discover_systems(profile=profile)
    catalog = [probe_system(row) for row in seeds]
    counts = summarize_catalog(catalog)

    foundation_health: dict[str, Any] | None = None
    if include_foundation_health:
        foundation_health = optional_foundation_health(include_stress=False)

    phase_mapping = counts.get("phase_mapping") or summarize_phase_mapping(catalog)
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _utc(),
        "stamp": stamp,
        "mode": "plan_only",
        "profile": profile,
        "ok": True,
        "aios_runtime_started": False,
        "gpu_train_started": False,
        "foundation_health_included": bool(include_foundation_health),
        "foundation_health": foundation_health,
        "roadmap_refs": dict(ROADMAP_REFS),
        "phase_mapping_summary": phase_mapping,
        "counts": counts,
        "catalog": catalog,
        "ingest_hint": {
            "for": "run_aios_core_automation_v1.py",
            "schema_version": SCHEMA_VERSION,
            "use_fields": [
                "catalog",
                "counts",
                "mode",
                "profile",
                "aios_runtime_started",
                "phase_mapping_summary",
                "roadmap_refs",
            ],
            "plan_only_ready_filter": "entry.plan_only_ready == true",
            "roadmap_fields": [
                "cold_start_phase",
                "cold_start_phase_label",
                "viv_build_status_row",
                "viv_build_status",
                "foundation_layer",
                "triangulation_disposition",
            ],
            "backup_note": "backup_core.automation_entry points at existing run_backup_core_automation_v1.py; do not duplicate",
            "roadmap_note": "Phases/rows map to existing COLD_START.md and VIV_BUILD_STATUS.md — no new roadmap document",
        },
    }
    # ok stays true for successful catalog generation; foundation_health failure is recorded separately.
    if foundation_health is not None and foundation_health.get("ok") is False:
        receipt["foundation_health_ok"] = False
    elif foundation_health is not None:
        receipt["foundation_health_ok"] = True
    return receipt


def write_receipt(receipt: dict[str, Any], *, stamp: str | None = None) -> Path:
    PREFLIGHT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = stamp or str(receipt.get("stamp") or _utc_stamp())
    folder = PREFLIGHT_DIR / stamp
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "RECEIPT.json"
    path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    latest = PREFLIGHT_DIR / "LATEST.json"
    latest.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    receipt["receipt_path"] = _posix(path)
    receipt["latest_path"] = _posix(latest)
    # Rewrite with path fields present.
    path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    latest.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path
