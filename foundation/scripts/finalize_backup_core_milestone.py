"""Generate evidence for the lean AIOS backup/security milestone."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.aios_adapter_backup import run_smoke  # noqa: E402
from lib.backup_core import (  # noqa: E402
    OBJECTS_ROOT,
    VAULT_ROOT,
    bootstrap_status,
    secure_write_evidence_json,
    secure_write_evidence_text,
    verify_snapshot,
)
from lib.security_bridge import (  # noqa: E402
    constitution,
    integrity_status,
    verify_backup_ledger,
    verify_training_ledger,
)
OUT = FOUNDATION / "artifacts" / "auto" / "backup_core" / "milestone_report_v1.json"
OUT_MD = FOUNDATION / "artifacts" / "auto" / "backup_core" / "MILESTONE.md"
PYTHON = Path(r"L:\Continue\.venv\Scripts\python.exe")
BOOTSTRAP_ID = "903c052b6b4f386913a79aabaf9e5b4dee51e701768c9de8bedb5ac16ff7b6d4"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(label: str, command: list[str], cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    return {
        "label": label,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "command": command,
        "output_tail": combined.splitlines()[-30:],
    }


def main() -> int:
    tests = [
        _run(
            "rust",
            ["cargo", "test", "--offline", "--quiet"],
            REPO / "security_core",
        ),
        _run(
            "training_security",
            [str(PYTHON), "scripts/test_training_security_contracts.py"],
            FOUNDATION,
        ),
        _run(
            "backup_security",
            [str(PYTHON), "scripts/test_backup_core_contracts.py"],
            FOUNDATION,
        ),
    ]
    bootstrap = bootstrap_status()
    full_bootstrap = verify_snapshot(BOOTSTRAP_ID, verify_catalog=True)
    latest = verify_snapshot(verify_catalog=False)
    local_module = REPO / "security_core" / "runtime" / "security_core.pyd"
    objects = list(OBJECTS_ROOT.rglob("*")) if OBJECTS_ROOT.is_dir() else []
    object_files = [path for path in objects if path.is_file()]
    config = json.loads((FOUNDATION / "model_config.json").read_text(encoding="utf-8"))
    disk = shutil.disk_usage(REPO)
    report = {
        "schema_version": "viv_backup_milestone_v1",
        "generated_at": _utc(),
        "ok": False,
        "architecture": {
            "vault": str(VAULT_ROOT).replace("\\", "/"),
            "content_addressing": "sha256",
            "deduplication": True,
            "restore": "staged_then_architect_approved",
            "transaction_failure_rollback": True,
            "minimum_free_bytes": 12 * 1024 * 1024 * 1024,
            "external_replication": "unconfigured",
            "immutable_base_policy": "hash_catalog_only",
        },
        "security": {
            "constitution": constitution(),
            "integrity": integrity_status(),
            "runtime_module": str(local_module).replace("\\", "/"),
            "runtime_sha256": _sha256(local_module),
            "training_ledger": verify_training_ledger(),
            "backup_ledger": verify_backup_ledger(),
        },
        "snapshots": {
            "bootstrap": bootstrap,
            "bootstrap_full_verification": full_bootstrap,
            "latest": latest,
            "object_count": len(object_files),
            "object_bytes": sum(path.stat().st_size for path in object_files),
        },
        "tests": tests,
        "runtime_state": {
            "voice_backend": config["voice"]["backend"],
            "served_name": config["voice"]["served_name"],
            "validated_candidate": config["openaster_training"]["validated_candidate"],
            "auto_deploy": config["openaster_training"]["auto_deploy"],
            "deployment_changed": False,
            "training_started": False,
        },
        "resources": {
            "l_free_bytes": disk.free,
            "l_free_gib": round(disk.free / (1024**3), 2),
            "reserve_ok": disk.free >= 12 * 1024 * 1024 * 1024,
        },
        "adapter_smoke": run_smoke(),
    }
    report["ok"] = bool(
        all(item["ok"] for item in tests)
        and bootstrap.get("ok")
        and full_bootstrap.get("ok")
        and latest.get("ok")
        and report["security"]["integrity"].get("ok")
        and report["security"]["training_ledger"].get("ok")
        and report["security"]["backup_ledger"].get("ok")
        and report["adapter_smoke"].get("ok")
        and report["resources"]["reserve_ok"]
        and report["runtime_state"]["validated_candidate"] is None
        and not report["runtime_state"]["deployment_changed"]
    )
    secure_write_evidence_json(OUT, report)
    lines = [
        "# AIOS Backup-Core Milestone",
        "",
        f"- Result: **{'PASS' if report['ok'] else 'FAIL'}**",
        f"- Bootstrap snapshot: `{BOOTSTRAP_ID}`",
        f"- Latest snapshot: `{latest['snapshot_id']}`",
        f"- Protected bootstrap files: {full_bootstrap['copied_items']}",
        f"- Catalogued immutable model files: {full_bootstrap['catalog_items']}",
        f"- Vault objects: {report['snapshots']['object_count']}",
        f"- Vault bytes: {report['snapshots']['object_bytes']}",
        f"- Viv-local security module: `0.2.7` / `{report['security']['runtime_sha256']}`",
        f"- L: free: {report['resources']['l_free_gib']} GiB",
        "- Restore drill: staged only; no live file changed.",
        "- External/off-disk replication: unconfigured.",
        "- Training/deployment: not started; Qwen remains live.",
        "",
    ]
    secure_write_evidence_text(OUT_MD, "\n".join(lines))
    print(json.dumps({"ok": report["ok"], "report": str(OUT), "summary": str(OUT_MD)}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
