"""Focused tests for the effect-closed backup CPU planner."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_backup_planner import (  # noqa: E402
    make_snapshot_manifest,
    module_status,
    plan_restore,
    plan_retention,
    plan_snapshot,
    verify_manifest,
)


def main() -> int:
    digest_a = "a" * 64
    digest_b = "b" * 64
    snapshot = plan_snapshot(
        trigger="pre-edit",
        source_paths=["L:/Continue/Viv/foundation/lib/example.py"],
        catalog_paths=["L:/Continue/Viv/foundation/models/example.safetensors"],
    )
    denied = plan_snapshot(trigger="bad", source_paths=["L:/Continue/Viv/../outside.py"])
    assert snapshot["ok"] and snapshot["state"] == "READY_FOR_GOVERNED_EXECUTOR", snapshot
    assert snapshot["filesystem_scan_performed"] is False, snapshot
    assert denied["ok"] is False and "path_traversal_segment" in denied["errors"], denied

    built = make_snapshot_manifest(
        [
            {"path": "L:/Continue/Viv/foundation/lib/example.py", "bytes": 10, "sha256": digest_a, "artifact_class": "code"},
            {"path": "L:/Continue/Viv/foundation/lib/other.py", "bytes": 20, "sha256": digest_b, "artifact_class": "code"},
        ],
        trigger="pre-edit",
        created_at="2026-08-04T12:00:00Z",
    )
    assert built["ok"] and verify_manifest(built["manifest"])["ok"], built
    tampered = {**built["manifest"], "trigger": "tampered"}
    assert verify_manifest(tampered)["ok"] is False, tampered

    restore = plan_restore(
        built["snapshot_id"],
        [{"target_path": "L:/Continue/Viv/foundation/lib/example.py", "sha256": digest_a}],
    )
    vault = plan_restore(
        built["snapshot_id"],
        [{"target_path": "L:/Continue/Viv/foundation/artifacts/auto/backup_core/file", "sha256": digest_a}],
    )
    assert restore["ok"] and restore["stage_only"] and restore["live_commit_approved"] is False, restore
    assert vault["ok"] is False and "restore_target_is_backup_vault" in vault["errors"], vault

    manifests = [{"snapshot_id": digest_a, "created_at": "2026-08-04T12:00:00Z"}, {"snapshot_id": digest_b, "created_at": "2026-08-03T12:00:00Z"}]
    retention = plan_retention(manifests, keep=1)
    assert retention["ok"] and len(retention["deletion_candidates"]) == 1, retention
    assert retention["deletion_performed"] is False, retention
    assert module_status()["security_authorization_requested"] is False

    source = (FOUNDATION / "lib" / "cpu_backup_planner.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    )
    assert not imported.intersection({"subprocess", "socket", "requests", "torch", "os", "shutil", "pathlib"}), imported
    forbidden_calls = {"open", "sleep", "system", "run", "Popen", "write_text", "mkdir", "unlink", "rmtree"}
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not calls.intersection(forbidden_calls), calls

    print(
        json.dumps(
            {
                "ok": True,
                "snapshot_state": snapshot["state"],
                "manifest_verified": True,
                "restore_stage_only": restore["stage_only"],
                "retention_candidates": len(retention["deletion_candidates"]),
                "filesystem_write_performed": False,
                "live_restore_performed": False,
                "deletion_performed": False,
                "llm_authority": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
