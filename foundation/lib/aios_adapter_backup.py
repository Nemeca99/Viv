"""Callable AIOS backup adapter backed by Viv's governed snapshot vault."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from lib.backup_core import (
    BackupError,
    automation_snapshot_roots,
    bootstrap_status,
    create_snapshot,
    immutable_model_catalog_paths,
    stage_restore,
    uml_evidence_snapshot_roots,
    verify_snapshot,
    _expand_files,
    _posix,
)
from lib.security_bridge import verify_backup_ledger
from lib.cpu_backup_planner import (  # noqa: E402
    make_snapshot_manifest,
    module_status as cpu_module_status,
    plan_restore as plan_restore_intent,
    plan_retention,
    plan_snapshot,
    verify_manifest,
)


ADAPTER_ID = "backup_core"
REGISTRY_ID = "backup_core"


def status() -> dict[str, Any]:
    """Return current vault, bootstrap, snapshot, and ledger status."""
    bootstrap = bootstrap_status()
    ledger = verify_backup_ledger()
    try:
        latest = verify_snapshot(enforce_security=False)
    except (BackupError, OSError, ValueError) as exc:
        latest = {"ok": False, "reason": str(exc)}
    return {
        "ok": bool(bootstrap.get("ok")) and bool(latest.get("ok")),
        "evidence": {
            "adapter": ADAPTER_ID,
            "registry_id": REGISTRY_ID,
            "mode": "content_addressed_security_governed",
            "bootstrap": bootstrap,
            "latest": latest,
            "ledger": ledger,
            "external_replication": "unconfigured",
        },
    }


def cpu_plan(
    *,
    trigger: str | None = None,
    source_paths: list[str] | None = None,
    catalog_paths: list[str] | None = None,
    manifest_items: list[dict[str, Any]] | None = None,
    manifest_created_at: str | None = None,
    snapshot_id: str | None = None,
    restore_items: list[dict[str, Any]] | None = None,
    manifests: list[dict[str, Any]] | None = None,
    keep: int = 7,
) -> dict[str, Any]:
    """Plan backup operations from supplied evidence without invoking the executor."""
    sections: dict[str, Any] = {"module": cpu_module_status()}
    if trigger is not None or source_paths is not None:
        sections["snapshot"] = plan_snapshot(
            trigger=trigger or "unspecified",
            source_paths=source_paths or [],
            catalog_paths=catalog_paths or [],
        )
    if manifest_items is not None:
        if manifest_created_at is None:
            sections["manifest"] = {"ok": False, "state": "ABSTAIN", "errors": ["manifest_created_at_required"]}
        else:
            built = make_snapshot_manifest(
                manifest_items,
                trigger=trigger or "unspecified",
                created_at=manifest_created_at,
            )
            sections["manifest"] = built
            sections["manifest_verification"] = verify_manifest(built.get("manifest"))
    if snapshot_id is not None or restore_items is not None:
        sections["restore"] = plan_restore_intent(snapshot_id or "", restore_items or [])
    if manifests is not None:
        sections["retention"] = plan_retention(manifests, keep=keep)
    failed = [name for name, result in sections.items() if name != "module" and result.get("ok") is False]
    return {
        "ok": not failed,
        "sections": sections,
        "failed_sections": failed,
        "filesystem_scan_performed": False,
        "filesystem_read_performed": False,
        "filesystem_write_performed": False,
        "security_authorization_requested": False,
        "live_restore_performed": False,
        "deletion_performed": False,
        "llm_authority": False,
    }


def plan_automation(
    *,
    trigger: str = "backup_core_automation_v1",
    profile: str = "safe",
    catalog_models: bool = False,
) -> dict[str, Any]:
    """Plan an automation snapshot: CPU intent + filesystem expand with weight denies."""
    roots = automation_snapshot_roots(profile=profile)
    files, skipped = _expand_files(roots, deny_weight_packs=True)
    catalog = immutable_model_catalog_paths() if catalog_models else []
    intent = plan_snapshot(
        trigger=trigger,
        source_paths=[_posix(path) for path in roots],
        catalog_paths=[_posix(path) for path in catalog],
    )
    exclusion_counts: dict[str, int] = {}
    for row in skipped:
        reason = str(row.get("reason") or "unknown")
        exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1
    return {
        "ok": bool(intent.get("ok")) and bool(files),
        "trigger": trigger,
        "profile": profile,
        "catalog_models": bool(catalog_models),
        "root_count": len(roots),
        "roots": [_posix(path) for path in roots],
        "file_count": len(files),
        "logical_bytes": sum(path.stat().st_size for path in files),
        "skipped_count": len(skipped),
        "exclusion_counts": exclusion_counts,
        "skipped_sample": skipped[:50],
        "uml_roots": [_posix(path) for path in uml_evidence_snapshot_roots()],
        "cpu_intent": intent,
        "deny_weight_packs": True,
        "execution_approved": False,
        "aios_runtime_started": False,
    }


def list_artifacts(limit: int = 20) -> dict[str, Any]:
    """List immutable snapshot manifests newest first."""
    from lib.backup_core import MANIFESTS_ROOT

    top = max(1, min(int(limit), 100))
    rows = []
    if MANIFESTS_ROOT.is_dir():
        for path in sorted(
            MANIFESTS_ROOT.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[:top]:
            rows.append(
                {
                    "snapshot_id": path.stem,
                    "path": str(path).replace("\\", "/"),
                    "bytes": path.stat().st_size,
                }
            )
    return {
        "ok": bool(rows),
        "evidence": {"adapter": ADAPTER_ID, "op": "list_artifacts", "artifacts": rows},
    }


def create(
    *,
    trigger: str,
    paths: Iterable[Path | str] | None = None,
    catalog_models: bool = False,
    deny_weight_packs: bool = False,
) -> dict[str, Any]:
    """Create one Rust-authorized snapshot."""
    catalog = immutable_model_catalog_paths() if catalog_models else ()
    try:
        result = create_snapshot(
            trigger=trigger,
            paths=paths,
            catalog_paths=catalog,
            deny_weight_packs=deny_weight_packs,
        )
        return {"ok": True, "evidence": result.as_dict()}
    except (BackupError, OSError, ValueError) as exc:
        return {"ok": False, "evidence": {"op": "create", "error": str(exc)}}


def create_automation(
    *,
    trigger: str = "backup_core_automation_v1",
    profile: str = "safe",
    catalog_models: bool = False,
) -> dict[str, Any]:
    """Execute the local-first automation profile through the governed vault."""
    plan = plan_automation(trigger=trigger, profile=profile, catalog_models=catalog_models)
    if not plan.get("ok"):
        return {"ok": False, "evidence": {"op": "create_automation", "plan": plan}}
    created = create(
        trigger=trigger,
        paths=automation_snapshot_roots(profile=profile),
        catalog_models=catalog_models,
        deny_weight_packs=True,
    )
    return {
        "ok": bool(created.get("ok")),
        "evidence": {
            "op": "create_automation",
            "plan": plan,
            "snapshot": created.get("evidence"),
            "aios_runtime_started": False,
        },
    }


def verify(snapshot_id: str | None = None) -> dict[str, Any]:
    try:
        result = verify_snapshot(snapshot_id)
        return {"ok": bool(result.get("ok")), "evidence": result}
    except (BackupError, OSError, ValueError) as exc:
        return {"ok": False, "evidence": {"op": "verify", "error": str(exc)}}


def plan_restore(snapshot_id: str, paths: Iterable[Path | str] | None = None) -> dict[str, Any]:
    """Stage a restore only; this API never commits live replacements."""
    try:
        result = stage_restore(snapshot_id, targets=paths)
        return {"ok": True, "evidence": result}
    except (BackupError, OSError, ValueError) as exc:
        return {"ok": False, "evidence": {"op": "plan_restore", "error": str(exc)}}


def legacy_tracking() -> dict[str, Any]:
    """Compatibility response: legacy V1/V2 sources are no longer executed."""
    return {
        "ok": True,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "legacy_tracking",
            "legacy_sources": "read_only_reference",
            "viv_executes_legacy": False,
        },
    }


def run_smoke() -> dict[str, Any]:
    state = status()
    listed = list_artifacts(3)
    ok = bool(state.get("ok")) and bool(listed.get("ok"))
    return {
        "ok": ok,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "smoke",
            "status": state,
            "list": listed,
            "live_restore_attempted": False,
        },
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_smoke(), indent=2, default=str))
