"""CPU-only contracts for Viv's AIOS backup and staged restore gate."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.backup_core import (  # noqa: E402
    BOOTSTRAP_REPORT,
    BackupError,
    bootstrap_status,
    stage_restore,
    verify_snapshot,
)
from lib.security_bridge import (  # noqa: E402
    authorize_backup,
    constitution,
    verify_backup_ledger,
)


MIN_FREE = 12 * 1024 * 1024 * 1024


def _request(
    *,
    action: str = "SNAPSHOT",
    actor: str = "artifact_controller",
    sources: list[str] | None = None,
    targets: list[str] | None = None,
    approved: bool = False,
) -> dict[str, object]:
    return {
        "action": action,
        "operation_id": "backup-contract",
        "snapshot_id": "a" * 64,
        "actor_role": actor,
        "manifest_hash": "b" * 64,
        "source_paths": sources
        or ["L:/Continue/Viv/foundation/model_config.json"],
        "target_paths": targets
        or ["L:/Continue/Viv/foundation/artifacts/auto/backup_core/vault"],
        "process_id": os.getpid(),
        "max_bytes": 1024,
        "min_free_bytes": MIN_FREE,
        "architect_approved": approved,
    }


def _deny(request: dict[str, object], rule: str) -> None:
    verdict = authorize_backup(request)
    assert not verdict.get("allowed"), verdict
    assert verdict.get("rule") == rule, verdict


def main() -> int:
    const = constitution()
    version = str(const.get("version") or "")
    assert version.startswith("0.2."), const
    assert BOOTSTRAP_REPORT.is_file(), BOOTSTRAP_REPORT
    bootstrap = bootstrap_status()
    assert bootstrap.get("ok"), bootstrap
    ledger = verify_backup_ledger()
    assert ledger.get("ok"), ledger

    allowed = authorize_backup(_request())
    assert allowed.get("allowed"), allowed

    escaped = _request(sources=["L:/Continue/Viv/../private.txt"])
    _deny(escaped, "path_contract")

    external_prefix = _request(
        sources=["L:/Continue/.venv/Lib/site-packages/security_core.pyd.evil"]
    )
    _deny(external_prefix, "capability_matrix")

    restore = _request(
        action="RESTORE_COMMIT",
        actor="architect",
        sources=["L:/Continue/Viv/sandbox/restore_staging/backup-contract/file.bin"],
        targets=["L:/Continue/Viv/foundation/model_config.json"],
    )
    _deny(restore, "architect_approval")

    replicate = _request(action="REPLICATE")
    _deny(replicate, "replication_unconfigured")

    verified = verify_snapshot(
        str(bootstrap["report"]["snapshot_id"]),
        verify_catalog=False,
    )
    assert verified.get("ok"), verified

    staged = stage_restore(
        str(bootstrap["report"]["snapshot_id"]),
        targets=(REPO / "security_core" / "Cargo.toml",),
    )
    assert staged.get("ok") and not staged.get("live_changed"), staged
    plan = json.loads(Path(staged["plan_path"]).read_text(encoding="utf-8"))
    assert len(plan["items"]) == 1, plan
    target_hash_before = plan["items"][0]["expected_current_sha256"]
    assert target_hash_before, plan

    staging = Path(staged["plan_path"]).parent.resolve()
    allowed_root = (REPO / "sandbox" / "restore_staging").resolve()
    staging.relative_to(allowed_root)
    shutil.rmtree(staging)

    print(
        json.dumps(
            {
                "ok": True,
                "security_version": const.get("version"),
                "bootstrap_snapshot": bootstrap["report"]["snapshot_id"],
                "verified_items": verified["copied_items"],
                "negative_contracts": 4,
                "staged_restore_items": 1,
                "live_changed": False,
                "backup_ledger_events": verify_backup_ledger().get("events"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BackupError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise
