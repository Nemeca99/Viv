"""Plan-only automation for privacy, support, and dream service cores.

Focused sibling to ``aios_core_automation``: inventories the three service
cores, runs effect-closed CPU planners, and writes receipts under
``foundation/artifacts/auto/service_cores_automation/``.

Default posture is plan-only. Never starts AIOS, never copies weight packs,
never deletes archives, never runs dream cycles, never stresses the plant.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from lib.paths import FOUNDATION_ROOT

RECEIPTS_ROOT = FOUNDATION_ROOT / "artifacts" / "auto" / "service_cores_automation"
SCHEMA_VERSION = "viv_service_cores_automation_receipt_v1"
MODULE_ID = "service_cores_automation"
VERSION = "v1"
PYTHON = Path(r"L:\Continue\.venv\Scripts\python.exe")
ORCHESTRATOR = FOUNDATION_ROOT / "scripts" / "run_service_cores_automation_v1.py"

SERVICE_CORE_IDS: tuple[str, ...] = ("privacy", "support", "dream")


@dataclass(frozen=True)
class ServiceCoreSpec:
    core_key: str
    core_id: str
    description: str
    adapter: str
    cpu_module: str
    planner: str
    tests: tuple[str, ...]
    docs: str
    default_mode: str
    execute_allowed: bool
    execute_kind: str  # none | closed_smoke
    constraints: tuple[str, ...]
    cold_start_phase: int


SPECS: tuple[ServiceCoreSpec, ...] = (
    ServiceCoreSpec(
        "privacy",
        "privacy_core",
        "Retention/mode/consent planning only.",
        "lib/aios_adapter_privacy.py",
        "lib/privacy_core.py",
        "lib.aios_adapter_privacy.cpu_plan",
        (
            "scripts/test_privacy_core_v1.py",
            "scripts/test_privacy_adapter_cpu_plan_v1.py",
            "scripts/test_cpu_privacy_policy_v1.py",
        ),
        "docs/PRIVACY_CORE_V1.md",
        "plan_only",
        True,
        "closed_smoke",
        ("no_delete", "no_writes", "no_aios_runtime"),
        6,
    ),
    ServiceCoreSpec(
        "support",
        "support_core",
        "Diagnostic/cache planning + health observation (no stress).",
        "lib/aios_adapter_support.py",
        "lib/support_core.py",
        "lib.aios_adapter_support.cpu_plan",
        (
            "scripts/test_support_core_v1.py",
            "scripts/test_support_adapter_cpu_plan_v1.py",
        ),
        "docs/SUPPORT_CORE_V1.md",
        "plan_only",
        True,
        "closed_smoke",
        ("no_stress", "no_aios_runtime"),
        1,
    ),
    ServiceCoreSpec(
        "dream",
        "dream_core",
        "Idle trigger + consolidation planning (no dream cycle execute).",
        "lib/aios_adapter_dream.py",
        "lib/dream_core.py",
        "lib.aios_adapter_dream.cycle_plan",
        (
            "scripts/test_dream_core_v1.py",
            "scripts/test_cpu_dream_planner_v1.py",
        ),
        "docs/DREAM_CORE_V1.md",
        "plan_only",
        False,
        "none",
        ("no_dream_cycle_execute", "no_archive_delete", "no_aios_runtime"),
        7,
    ),
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _posix(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def get_spec(core_key: str) -> ServiceCoreSpec | None:
    key = str(core_key or "").strip().casefold()
    if key.endswith("_core"):
        key = key[: -len("_core")]
    for spec in SPECS:
        if spec.core_key == key or spec.core_id.casefold() == key:
            return spec
    return None


def list_specs() -> list[dict[str, Any]]:
    return [asdict(spec) for spec in SPECS]


def inventory_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in SPECS:
        adapter_path = FOUNDATION_ROOT / spec.adapter
        cpu_path = FOUNDATION_ROOT / spec.cpu_module
        docs_path = FOUNDATION_ROOT / spec.docs
        test_paths = [FOUNDATION_ROOT / rel for rel in spec.tests]
        rows.append(
            {
                "core_key": spec.core_key,
                "core_id": spec.core_id,
                "automatable": True,
                "mode": "plan_only",
                "default_mode": spec.default_mode,
                "execute_allowed": spec.execute_allowed,
                "execute_kind": spec.execute_kind,
                "planner": spec.planner,
                "adapter": _posix(spec.adapter),
                "adapter_present": adapter_path.is_file(),
                "cpu_module": _posix(spec.cpu_module),
                "cpu_module_present": cpu_path.is_file(),
                "docs": _posix(spec.docs),
                "docs_present": docs_path.is_file(),
                "tests": [_posix(rel) for rel in spec.tests],
                "tests_present": {
                    _posix(rel): (FOUNDATION_ROOT / rel).is_file() for rel in spec.tests
                },
                "constraints": list(spec.constraints),
                "cold_start_phase": spec.cold_start_phase,
                "description": spec.description,
                "command": (
                    f"{_posix(PYTHON)} {_posix(ORCHESTRATOR)} "
                    f"--core {spec.core_key} --plan-only"
                ),
                "all_artifacts_present": adapter_path.is_file()
                and cpu_path.is_file()
                and docs_path.is_file()
                and all(p.is_file() for p in test_paths),
            }
        )
    return rows


def inventory() -> dict[str, Any]:
    rows = inventory_rows()
    return {
        "ok": all(row.get("all_artifacts_present") for row in rows),
        "module": MODULE_ID,
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "receipts_root": _posix(RECEIPTS_ROOT),
        "cores": list(SERVICE_CORE_IDS),
        "rows": rows,
        "aios_runtime_started": False,
        "deny_weight_packs": True,
        "federation_activation": False,
        "bridge_promotion": False,
        "at": _utc(),
    }


def _base_result(*, spec: ServiceCoreSpec, mode: str, ok: bool, **fields: Any) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "schema_version": SCHEMA_VERSION,
        "module": MODULE_ID,
        "version": VERSION,
        "core_key": spec.core_key,
        "core_id": spec.core_id,
        "mode": mode,
        "at": _utc(),
        "aios_runtime_started": False,
        "deny_weight_packs": True,
        "federation_activation": False,
        "bridge_promotion": False,
        "soft_0_99": False,
        "constraints": list(spec.constraints),
        **fields,
    }


def plan_privacy(spec: ServiceCoreSpec | None = None) -> dict[str, Any]:
    from lib.aios_adapter_privacy import cpu_plan

    profile = spec or get_spec("privacy")
    assert profile is not None
    plan = cpu_plan(
        {"mode": "standard"},
        requested_mode="strict",
        explicit_consent=False,
        retention_category="conversations",
        records=[{"category": "conversation", "source_kind": "conversation"}],
        data_action={"action": "export", "target": "conversations", "confirmation": ""},
    )
    ok = bool(plan.get("ok")) and plan.get("writes_performed") is False
    return _base_result(spec=profile, mode="plan_only", ok=ok, plan=plan)


def plan_support(spec: ServiceCoreSpec | None = None) -> dict[str, Any]:
    from lib.aios_adapter_support import cpu_plan
    from lib.support_core import make_cache_entry

    profile = spec or get_spec("support")
    assert profile is not None
    plan = cpu_plan(
        [{"name": "membrane", "ok": True, "detail": "service_cores_fixture"}],
        [
            make_cache_entry(
                "support automation fixture",
                cache_id="service-cache-one",
                source="service_cores_automation",
                hit=True,
            ),
            make_cache_entry(
                "another fragment",
                cache_id="service-cache-two",
                source="service_cores_automation",
                hit=False,
            ),
        ],
        sample_text="support automation fixture user@example.com",
    )
    ok = bool(plan.get("ok")) and plan.get("writes_performed") is False and plan.get("live_probe_performed") is False
    return _base_result(spec=profile, mode="plan_only", ok=ok, plan=plan)


def plan_dream(spec: ServiceCoreSpec | None = None) -> dict[str, Any]:
    from lib.aios_adapter_dream import consolidation_plan, cycle_plan

    profile = spec or get_spec("dream")
    assert profile is not None
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
        spec=profile,
        mode="plan_only",
        ok=ok,
        plan={"trigger": trigger, "consolidation": consolidation},
        dream_cycle_executed=False,
        archive_deleted=False,
    )


_PLAN_RUNNERS: dict[str, Callable[[ServiceCoreSpec], dict[str, Any]]] = {
    "privacy": plan_privacy,
    "support": plan_support,
    "dream": plan_dream,
}


def run_plan(core_key: str) -> dict[str, Any]:
    spec = get_spec(core_key)
    if spec is None:
        return {
            "ok": False,
            "error": "unknown_core",
            "core_key": core_key,
            "available": list(SERVICE_CORE_IDS),
            "aios_runtime_started": False,
            "deny_weight_packs": True,
        }
    runner = _PLAN_RUNNERS[spec.core_key]
    return runner(spec)


def run_closed_smoke(core_key: str) -> dict[str, Any]:
    """Bounded adapter smoke for privacy/support only; dream remains plan-only."""
    spec = get_spec(core_key)
    if spec is None:
        return {
            "ok": False,
            "error": "unknown_core",
            "core_key": core_key,
            "available": list(SERVICE_CORE_IDS),
            "aios_runtime_started": False,
        }
    if not spec.execute_allowed or spec.execute_kind != "closed_smoke":
        return _base_result(
            spec=spec,
            mode="execute",
            ok=False,
            error="execute_not_allowed",
            execution_approved=False,
            hint="dream and operator-gated cores stay plan-only",
        )
    import importlib

    module_name = {
        "privacy": "lib.aios_adapter_privacy",
        "support": "lib.aios_adapter_support",
    }[spec.core_key]
    smoke = importlib.import_module(module_name).run_smoke()
    plan = run_plan(spec.core_key)
    ok = bool(smoke.get("ok")) and bool(plan.get("ok"))
    return _base_result(
        spec=spec,
        mode="execute",
        ok=ok,
        plan=plan.get("plan"),
        smoke=smoke,
        execution_approved=True,
        note="closed_smoke_receipt_only",
    )


def run_all_plans() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for core_key in SERVICE_CORE_IDS:
        results[core_key] = run_plan(core_key)
    ok = all(bool(row.get("ok")) for row in results.values())
    return {
        "ok": ok,
        "schema_version": SCHEMA_VERSION,
        "module": MODULE_ID,
        "version": VERSION,
        "mode": "plan_only",
        "cores": list(SERVICE_CORE_IDS),
        "results": results,
        "at": _utc(),
        "aios_runtime_started": False,
        "deny_weight_packs": True,
        "federation_activation": False,
        "bridge_promotion": False,
        "soft_0_99": False,
    }


def write_receipt(payload: dict[str, Any], *, stamp: str | None = None) -> Path:
    stamp_value = stamp or _utc_stamp()
    folder = RECEIPTS_ROOT / stamp_value
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "RECEIPT.json"
    body = dict(payload)
    body.setdefault("stamp", stamp_value)
    body.setdefault("created_at", _utc())
    body.setdefault("receipt_root", _posix(RECEIPTS_ROOT))
    path.write_text(
        json.dumps(body, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    core_label = body.get("core_key") or body.get("core_id") or "all"
    md_lines = [
        f"# Service cores automation receipt `{stamp_value}`",
        "",
        f"- ok: `{body.get('ok')}`",
        f"- core: `{core_label}`",
        f"- mode: `{body.get('mode')}`",
        f"- aios_runtime_started: `{body.get('aios_runtime_started')}`",
        f"- deny_weight_packs: `{body.get('deny_weight_packs')}`",
        f"- federation_activation: `{body.get('federation_activation')}`",
        f"- bridge_promotion: `{body.get('bridge_promotion')}`",
        "",
    ]
    if isinstance(body.get("results"), dict):
        md_lines.append("## Per-core results")
        md_lines.append("")
        for key, row in body["results"].items():
            md_lines.append(f"- `{key}`: ok=`{row.get('ok')}` mode=`{row.get('mode')}`")
        md_lines.append("")
    (folder / "RECEIPT.md").write_text("\n".join(md_lines), encoding="utf-8", newline="\n")
    return path
