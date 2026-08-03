"""Callable AIOS backup adapter backed by Viv's governed snapshot vault."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from lib.backup_core import (
    BackupError,
    bootstrap_status,
    create_snapshot,
    immutable_model_catalog_paths,
    stage_restore,
    verify_snapshot,
)
from lib.security_bridge import verify_backup_ledger


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
) -> dict[str, Any]:
    """Create one Rust-authorized snapshot."""
    catalog = immutable_model_catalog_paths() if catalog_models else ()
    try:
        result = create_snapshot(trigger=trigger, paths=paths, catalog_paths=catalog)
        return {"ok": True, "evidence": result.as_dict()}
    except (BackupError, OSError, ValueError) as exc:
        return {"ok": False, "evidence": {"op": "create", "error": str(exc)}}


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
