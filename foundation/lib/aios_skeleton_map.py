"""AIOS skeleton map — walk ALL catalog systems + bus wire status.

Plan-only. Honest SKELETON / PARTIAL / BOUND labels. Never starts AIOS,
never GPU-trains, never 120s plant stress.
"""
from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.aios_skeleton_bus import BUS_SLOTS, default_bus
from lib.aios_skeleton_stub import skeleton_cpu_plan
from lib.aios_skeleton_subagent_profiles import list_profiles as list_subagent_profiles
from lib.aios_systems_preflight import (
    COLD_START_PHASES,
    discover_systems,
    probe_system,
    roadmap_mapping_for,
)
from lib.paths import AUTO_ARTIFACTS, FOUNDATION_ROOT

SCHEMA_VERSION = "aios_skeleton_map_receipt_v1"
SKELETON_DIR = AUTO_ARTIFACTS / "aios_skeleton"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _posix(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _classify_system(row: dict[str, Any], plan: dict[str, Any] | None) -> str:
    """Honest build_state for one catalog system."""
    if row.get("deferred"):
        return "SKELETON"
    if plan and str(plan.get("build_state") or "").upper() in {"SKELETON", "STUB", "PARTIAL", "BOUND"}:
        return str(plan.get("build_state")).upper()
    if row.get("plan_only_ready") and row.get("has_cpu_plan"):
        return "PARTIAL"
    if row.get("has_cpu_plan") and row.get("importable"):
        return "PARTIAL"
    if row.get("importable"):
        return "SKELETON"
    if row.get("adapter_filename"):
        return "SKELETON"
    viv = str(row.get("viv_build_status") or "")
    if viv == "BUILT":
        return "PARTIAL"  # present elsewhere but not adapter-wired here
    if viv in {"NONE", "LEGACY"}:
        return "SKELETON"
    return "SKELETON"


def _invoke_cpu_plan(row: dict[str, Any]) -> dict[str, Any] | None:
    module_name = row.get("adapter_module")
    if not module_name or not row.get("importable"):
        return None
    try:
        mod = importlib.import_module(str(module_name))
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": "skeleton",
            "build_state": "SKELETON",
            "import_error": f"{type(exc).__name__}: {exc}",
            "aios_runtime_started": False,
        }
    fn = getattr(mod, "cpu_plan", None)
    if not callable(fn):
        # Prefer known alternate planners without executing side effects.
        for alt_name in ("cycle_plan", "communication_plan"):
            alt = getattr(mod, alt_name, None)
            if callable(alt):
                try:
                    if alt_name == "cycle_plan":
                        plan = alt(idle_minutes=0.0, active_conversation=False)
                    elif alt_name == "communication_plan":
                        plan = alt(prompt="skeleton_map_probe", grounded=True)
                    else:
                        plan = alt()
                    if isinstance(plan, dict):
                        plan = dict(plan)
                        plan.setdefault("build_state", "PARTIAL")
                        plan.setdefault("delegates_to", f"{module_name}.{alt_name}")
                        plan.setdefault("aios_runtime_started", False)
                        return plan
                except Exception as exc:  # noqa: BLE001
                    return {
                        "ok": False,
                        "status": "skeleton",
                        "build_state": "SKELETON",
                        "planner_error": f"{alt_name}: {type(exc).__name__}: {exc}",
                        "aios_runtime_started": False,
                    }
        return None
    try:
        # Most cpu_plan callables accept kwargs; call with no args when possible.
        plan = fn()
        if isinstance(plan, dict):
            plan = dict(plan)
            plan.setdefault(
                "build_state",
                "PARTIAL" if plan.get("ok") is not False else "SKELETON",
            )
            plan.setdefault("aios_runtime_started", False)
            return plan
        return {
            "ok": True,
            "status": "partial",
            "build_state": "PARTIAL",
            "raw_type": type(plan).__name__,
            "aios_runtime_started": False,
        }
    except TypeError:
        # Signature requires kwargs — emit skeleton without inventing args.
        return skeleton_cpu_plan(
            core_id=str(row["id"]),
            role=str(row.get("role") or ""),
            build_state="SKELETON",
            notes="cpu_plan present but requires args — mapped as SKELETON without invoke",
            delegates_to=f"{module_name}.cpu_plan",
            cold_start_phase=row.get("cold_start_phase"),
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": "skeleton",
            "build_state": "SKELETON",
            "planner_error": f"{type(exc).__name__}: {exc}",
            "aios_runtime_started": False,
        }


def walk_systems(*, profile: str = "full") -> list[dict[str, Any]]:
    seeds = discover_systems(profile=profile)
    catalog = [probe_system(row) for row in seeds]
    out: list[dict[str, Any]] = []
    for row in catalog:
        plan = _invoke_cpu_plan(row)
        if plan is None:
            plan = skeleton_cpu_plan(
                core_id=str(row["id"]),
                role=str(row.get("role") or ""),
                build_state="SKELETON",
                notes=(
                    "No cpu_plan — structural catalog row only. "
                    "Flesh later; compute core wires via aios_skeleton_bus."
                ),
                cold_start_phase=row.get("cold_start_phase"),
            )
        build_state = _classify_system(row, plan)
        mapped = roadmap_mapping_for(str(row["id"]))
        out.append(
            {
                "id": row["id"],
                "role": row.get("role"),
                "build_state": build_state,
                "cold_start_phase": row.get("cold_start_phase"),
                "cold_start_phase_label": COLD_START_PHASES.get(
                    int(row["cold_start_phase"]) if row.get("cold_start_phase") is not None else -1,
                    mapped.get("cold_start_phase_label"),
                ),
                "viv_build_status": row.get("viv_build_status"),
                "viv_build_status_row": row.get("viv_build_status_row"),
                "importable": row.get("importable"),
                "has_cpu_plan": row.get("has_cpu_plan"),
                "plan_only_ready": row.get("plan_only_ready"),
                "adapter_module": row.get("adapter_module"),
                "adapter_filename": row.get("adapter_filename"),
                "deferred": row.get("deferred"),
                "risk_tag": row.get("risk_tag"),
                "plan": {
                    "ok": plan.get("ok"),
                    "status": plan.get("status"),
                    "build_state": plan.get("build_state"),
                    "delegates_to": plan.get("delegates_to"),
                    "notes": plan.get("notes") or plan.get("note"),
                    "aios_runtime_started": plan.get("aios_runtime_started", False),
                },
            }
        )
    return out


def summarize_systems(systems: list[dict[str, Any]]) -> dict[str, Any]:
    by_state: dict[str, int] = {}
    by_phase: dict[str, int] = {}
    for row in systems:
        st = str(row.get("build_state") or "UNKNOWN")
        by_state[st] = by_state.get(st, 0) + 1
        ph = str(row.get("cold_start_phase"))
        by_phase[ph] = by_phase.get(ph, 0) + 1
    total = len(systems)
    partial_or_better = sum(
        1 for r in systems if r.get("build_state") in {"PARTIAL", "BOUND"}
    )
    skeleton = by_state.get("SKELETON", 0) + by_state.get("STUB", 0)
    return {
        "systems_total": total,
        "by_build_state": dict(sorted(by_state.items())),
        "by_cold_start_phase": dict(
            sorted(by_phase.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 99)
        ),
        "pct_partial_or_bound": round(100.0 * partial_or_better / total, 1) if total else 0.0,
        "pct_skeleton": round(100.0 * skeleton / total, 1) if total else 0.0,
        "structural_coverage_pct": 100.0 if total else 0.0,
    }


def build_map_receipt(*, profile: str = "full", stamp: str | None = None) -> dict[str, Any]:
    stamp = stamp or _utc_stamp()
    systems = walk_systems(profile=profile)
    sys_summary = summarize_systems(systems)
    bus = default_bus()
    wire = bus.wire_status()
    subagents = list_subagent_profiles()

    # Register security adapter in extra map sense: ensure probe sees it next run
    # via _EXTRA / disk glob — already on disk as aios_adapter_security.py.

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _utc(),
        "stamp": stamp,
        "mode": "plan_only",
        "profile": profile,
        "ok": True,
        "aios_runtime_started": False,
        "gpu_train_started": False,
        "soft_0_99": False,
        "purpose": (
            "Complete honest AIOS skeleton map — structural coverage for later "
            "compute-core (UML Nested-PEMDAS + RID/PID plant + mouth/security) wire-in"
        ),
        "systems_summary": sys_summary,
        "bus_wire_status": wire,
        "subagent_profiles": {
            "count": len(subagents),
            "all_skip": all(p.get("status") == "SKIP" for p in subagents),
            "profiles": subagents,
        },
        "vacant_for_compute_core": wire.get("vacant_for_compute_core") or [],
        "vacant_slot_notes": {
            "uml_invoke": "Nested-PEMDAS / uml_engine invoke — deliberately vacant for compute-core",
        },
        "systems": systems,
        "cold_start_phases": dict(COLD_START_PHASES),
        "bus_slots": list(BUS_SLOTS),
        "coverage": {
            "systems_counted": sys_summary["systems_total"],
            "systems_structural_coverage_pct": sys_summary["structural_coverage_pct"],
            "systems_partial_or_bound_pct": sys_summary["pct_partial_or_bound"],
            "systems_skeleton_pct": sys_summary["pct_skeleton"],
            "bus_slots_total": wire["slots_total"],
            "bus_slots_filled_pct": wire["pct_filled"],
            "bus_slots_vacant_pct": wire["pct_vacant"],
            "bus_vacant": wire.get("vacant_for_compute_core") or [],
        },
    }
    return receipt


def write_receipt(receipt: dict[str, Any], *, stamp: str | None = None) -> Path:
    SKELETON_DIR.mkdir(parents=True, exist_ok=True)
    stamp = stamp or str(receipt.get("stamp") or _utc_stamp())
    folder = SKELETON_DIR / stamp
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "SKELETON_MAP.json"
    latest = SKELETON_DIR / "LATEST.json"
    operator_latest = SKELETON_DIR / "skeleton_map_latest.json"
    receipt["receipt_path"] = _posix(path)
    receipt["latest_path"] = _posix(latest)
    receipt["skeleton_map_latest_path"] = _posix(operator_latest)
    receipt["foundation_root"] = _posix(FOUNDATION_ROOT)
    text = json.dumps(receipt, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    latest.write_text(text, encoding="utf-8", newline="\n")
    # Human one-pager
    cov = receipt.get("coverage") or {}
    wire = receipt.get("bus_wire_status") or {}
    lines = [
        f"# AIOS Skeleton Map `{stamp}`",
        "",
        f"- mode: `{receipt.get('mode')}`",
        f"- systems: `{cov.get('systems_counted')}` (structural coverage `{cov.get('systems_structural_coverage_pct')}%`)",
        f"- systems PARTIAL/BOUND: `{cov.get('systems_partial_or_bound_pct')}%`",
        f"- systems SKELETON: `{cov.get('systems_skeleton_pct')}%`",
        f"- bus filled: `{cov.get('bus_slots_filled_pct')}%` ({wire.get('slots_bound_or_partial')}/{wire.get('slots_total')})",
        f"- bus vacant (compute-core wire-in): `{', '.join(cov.get('bus_vacant') or []) or '(none)'}`",
        f"- aios_runtime_started: `{receipt.get('aios_runtime_started')}`",
        "",
        "## Bus slots",
        "",
    ]
    for row in wire.get("rows") or []:
        lines.append(
            f"- `{row.get('slot')}` — **{row.get('fill')}**"
            f"{' (wire-in)' if row.get('for_compute_core_wire_in') else ''}"
            f" — {row.get('note') or ''}"
        )
    md = folder / "SKELETON_MAP.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    receipt["receipt_md"] = _posix(md)
    text = json.dumps(receipt, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    latest.write_text(text, encoding="utf-8", newline="\n")
    # Operator-facing index (includes overnight gap stubs + vacant hooks).
    gap_ids = ("perception_core", "ethics_core", "federation_core")
    systems = receipt.get("systems") or []
    gap_rows = [s for s in systems if s.get("id") in gap_ids]
    index = {
        "ok": bool(receipt.get("ok")),
        "schema_version": "aios_skeleton_map_index_v1",
        "at": receipt.get("created_at"),
        "stamp": stamp,
        "full_map_receipt": _posix(path),
        "full_map_latest": _posix(latest),
        "systems_counted": cov.get("systems_counted"),
        "systems_summary": receipt.get("systems_summary"),
        "coverage": cov,
        "bus_slots": receipt.get("bus_slots"),
        "wire_status": wire,
        "vacant_for_compute_core": cov.get("bus_vacant") or ["uml_invoke", "subagent_spawn"],
        "overnight_gap_stubs": {
            row["id"]: {
                "build_state": row.get("build_state"),
                "cold_start_phase": row.get("cold_start_phase"),
                "adapter_module": row.get("adapter_module"),
            }
            for row in gap_rows
        },
        "aios_runtime_started": False,
        "federation_activation": False,
        "gpu_train_started": False,
        "soft_0_99": False,
    }
    operator_latest.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path
