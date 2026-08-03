"""Security-governed AIOS content-addressed backup and restore core.

The vault stores one SHA-256 object per unique byte sequence. Snapshot manifests
are immutable and parent-linked. Restore is always staged first; live commit is
an explicit Architect operation and creates its own safety snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Iterable
import uuid

from lib.security_bridge import authorize_backup, verify_backup_ledger


VIV_ROOT = Path(r"L:\Continue\Viv")
FOUNDATION = VIV_ROOT / "foundation"
VAULT_ROOT = FOUNDATION / "artifacts" / "auto" / "backup_core" / "vault"
OBJECTS_ROOT = VAULT_ROOT / "objects"
MANIFESTS_ROOT = VAULT_ROOT / "manifests"
HEAD_PATH = VAULT_ROOT / "refs" / "HEAD"
EVIDENCE_ROOT = FOUNDATION / "artifacts" / "auto" / "backup_core"
RESTORE_STAGING_ROOT = VIV_ROOT / "sandbox" / "restore_staging"
BOOTSTRAP_REPORT = EVIDENCE_ROOT / "bootstrap_restore_verification.json"
MIN_FREE_BYTES = 12 * 1024 * 1024 * 1024
MAX_OPERATION_BYTES = 8 * 1024 * 1024 * 1024
EXTERNAL_EXACT = {
    Path(r"L:\Continue\.venv\Lib\site-packages\security_core.pyd"),
    Path(r"L:\Continue\.venv\Lib\site-packages\security_core.pyd.sha256"),
}
IGNORED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".git",
    "node_modules",
    "backup_core",
}
IGNORED_SUFFIXES = {".pyc", ".pyo", ".security-tmp", ".staged"}
IGNORED_NAMES = {"security_backup_events.jsonl"}


class BackupError(RuntimeError):
    """Fail-closed backup contract error."""


@dataclass(frozen=True)
class SnapshotResult:
    snapshot_id: str
    manifest_path: Path
    copied_items: int
    catalog_items: int
    logical_bytes: int
    new_object_bytes: int
    decision_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "snapshot_id": self.snapshot_id,
            "manifest_path": _posix(self.manifest_path),
            "copied_items": self.copied_items,
            "catalog_items": self.catalog_items,
            "logical_bytes": self.logical_bytes,
            "new_object_bytes": self.new_object_bytes,
            "decision_id": self.decision_id,
        }


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _posix(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".security-tmp", dir=path.parent)
    temp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _has_reparse_component(path: Path) -> bool:
    cursor = path
    while True:
        if cursor.exists() or cursor.is_symlink():
            info = cursor.lstat()
            if stat.S_ISLNK(info.st_mode):
                return True
            attributes = int(getattr(info, "st_file_attributes", 0))
            if attributes & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
                return True
        if cursor.parent == cursor:
            return False
        cursor = cursor.parent


def _validate_source(path: Path) -> Path:
    if ".." in path.parts:
        raise BackupError(f"path traversal denied: {path}")
    resolved = path.resolve(strict=True)
    if _has_reparse_component(path):
        raise BackupError(f"reparse or symlink source denied: {path}")
    if _under(resolved, VAULT_ROOT):
        raise BackupError(f"vault recursion denied: {path}")
    if not _under(resolved, VIV_ROOT) and resolved not in {
        item.resolve(strict=False) for item in EXTERNAL_EXACT
    }:
        raise BackupError(f"source outside backup allowlist: {path}")
    if not resolved.is_file():
        raise BackupError(f"source is not a file: {path}")
    return resolved


def _validate_live_target(path: Path) -> Path:
    if ".." in path.parts or _has_reparse_component(path):
        raise BackupError(f"unsafe restore target: {path}")
    resolved = path.resolve(strict=False)
    if _under(resolved, VAULT_ROOT):
        raise BackupError(f"restore may not target vault: {path}")
    if not _under(resolved, VIV_ROOT) and resolved not in {
        item.resolve(strict=False) for item in EXTERNAL_EXACT
    }:
        raise BackupError(f"restore target outside allowlist: {path}")
    return resolved


def _operation_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def _artifact_class(path: Path) -> str:
    text = _posix(path).lower()
    if "/models/" in text and any(part in text for part in ("adapter", "checkpoint", "viv_voice_lora")):
        return "adapter"
    if "/artifacts/auto/" in text:
        return "frozen_or_training_evidence"
    if "security_core" in text:
        return "security"
    if "/artifacts/audit/" in text:
        return "audit"
    return "code_config_doc"


def _expand_files(roots: Iterable[Path | str]) -> tuple[list[Path], list[dict[str, str]]]:
    files: set[Path] = set()
    skipped: list[dict[str, str]] = []
    for raw in roots:
        path = Path(raw)
        if not path.exists():
            skipped.append({"path": _posix(path), "reason": "missing"})
            continue
        if _has_reparse_component(path):
            raise BackupError(f"reparse root denied: {path}")
        candidates = [path] if path.is_file() else path.rglob("*")
        for candidate in candidates:
            if not candidate.is_file():
                continue
            if any(part in IGNORED_PARTS for part in candidate.parts):
                continue
            if candidate.name in IGNORED_NAMES:
                continue
            if candidate.suffix.lower() in IGNORED_SUFFIXES:
                continue
            files.add(_validate_source(candidate))
    return sorted(files, key=lambda value: _posix(value).lower()), skipped


def default_snapshot_roots() -> list[Path]:
    """Lean sovereign set; large immutable bases are intentionally excluded."""
    roots = [
        VIV_ROOT / "security_core" / "src",
        VIV_ROOT / "security_core" / "scripts",
        VIV_ROOT / "security_core" / "runtime",
        VIV_ROOT / "security_core" / "Cargo.toml",
        VIV_ROOT / "security_core" / "Cargo.lock",
        VIV_ROOT / "security_core" / "README.md",
        VIV_ROOT / "src",
        VIV_ROOT / "scripts",
        FOUNDATION / "lib",
        FOUNDATION / "scripts",
        FOUNDATION / "model_config.json",
        FOUNDATION / "cpu_config.json",
        FOUNDATION / "BACKUP_CORE.md",
        FOUNDATION / "VIV_BUILD_STATUS.md",
        FOUNDATION / "AIFL_STATUS.md",
        FOUNDATION / "VOICE.md",
        FOUNDATION / "VIV_INDEX.md",
        FOUNDATION / "artifacts" / "audit",
        FOUNDATION / "artifacts" / "models",
        FOUNDATION / "artifacts" / "auto" / "shadow_judge",
        FOUNDATION / "artifacts" / "auto" / "openaster_parity",
        FOUNDATION / "artifacts" / "auto" / "openaster_training_tree",
    ]
    roots.extend(path for path in EXTERNAL_EXACT if path.exists())
    return roots


def immutable_model_catalog_paths() -> list[Path]:
    config = json.loads((FOUNDATION / "model_config.json").read_text(encoding="utf-8"))
    # CPU specialist weights are part of Viv's cognitive substrate and must
    # receive the same immutable backup treatment as the replaceable voice
    # weights.  Catalog only model files; loaders remain separate concerns.
    paths = list((FOUNDATION / "models" / "cpu").glob("*.gguf"))
    paths.extend((FOUNDATION / "models" / "gpu").glob("*.gguf"))
    hf_base = Path(str(config.get("voice", {}).get("hf_base") or ""))
    if hf_base.is_dir():
        paths.extend(path for path in hf_base.rglob("*") if path.is_file())
    return sorted(set(paths), key=lambda value: _posix(value).lower())


def _request(
    *,
    action: str,
    operation_id: str,
    snapshot_id: str | None,
    actor_role: str,
    manifest_hash: str,
    source_paths: Iterable[Path | str],
    target_paths: Iterable[Path | str],
    max_bytes: int,
    architect_approved: bool = False,
) -> dict[str, Any]:
    return {
        "action": action,
        "operation_id": operation_id,
        "snapshot_id": snapshot_id,
        "actor_role": actor_role,
        "manifest_hash": manifest_hash,
        "source_paths": [_posix(path) for path in source_paths],
        "target_paths": [_posix(path) for path in target_paths],
        "process_id": os.getpid(),
        "max_bytes": max(1, min(int(max_bytes), MAX_OPERATION_BYTES)),
        "min_free_bytes": MIN_FREE_BYTES,
        "architect_approved": bool(architect_approved),
    }


def _require_authorized(request: dict[str, Any]) -> dict[str, Any]:
    ledger = verify_backup_ledger()
    if not ledger.get("ok"):
        raise BackupError(f"backup ledger failed: {ledger}")
    verdict = authorize_backup(request)
    if not verdict.get("allowed"):
        raise BackupError(f"backup security denied: {verdict}")
    return verdict


def _head() -> str | None:
    if not HEAD_PATH.is_file():
        return None
    value = HEAD_PATH.read_text(encoding="utf-8").strip().lower()
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise BackupError("vault HEAD is malformed")
    return value


def _manifest_path(snapshot_id: str) -> Path:
    if len(snapshot_id) != 64 or any(char not in "0123456789abcdef" for char in snapshot_id):
        raise BackupError("snapshot id is malformed")
    return MANIFESTS_ROOT / f"{snapshot_id}.json"


def _object_path(sha256: str) -> Path:
    return OBJECTS_ROOT / sha256[:2] / sha256[2:]


def _copy_object(source: Path, expected_hash: str) -> tuple[Path, bool]:
    destination = _object_path(expected_hash)
    if destination.is_file():
        if _file_sha256(destination) != expected_hash:
            raise BackupError(f"existing object is corrupt: {destination}")
        return destination, False
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".object-tmp", dir=destination.parent
    )
    temp = Path(raw)
    try:
        with source.open("rb") as src, os.fdopen(fd, "wb") as dst:
            shutil.copyfileobj(src, dst, length=4 * 1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        if _file_sha256(temp) != expected_hash:
            raise BackupError(f"source changed while copying: {source}")
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    return destination, True


def create_snapshot(
    *,
    trigger: str,
    paths: Iterable[Path | str] | None = None,
    catalog_paths: Iterable[Path | str] = (),
) -> SnapshotResult:
    """Create one immutable, parent-linked snapshot after Rust authorization."""
    roots = list(paths) if paths is not None else default_snapshot_roots()
    files, skipped = _expand_files(roots)
    if not files:
        raise BackupError("snapshot contains no files")

    copied: list[dict[str, Any]] = []
    logical_bytes = 0
    for path in files:
        before = path.stat()
        digest = _file_sha256(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise BackupError(f"source changed while hashing: {path}")
        logical_bytes += before.st_size
        copied.append(
            {
                "path": _posix(path),
                "bytes": before.st_size,
                "sha256": digest,
                "object": f"objects/{digest[:2]}/{digest[2:]}",
                "artifact_class": _artifact_class(path),
            }
        )

    catalog: list[dict[str, Any]] = []
    for raw in catalog_paths:
        path = _validate_source(Path(raw))
        info = path.stat()
        catalog.append(
            {
                "path": _posix(path),
                "bytes": info.st_size,
                "sha256": _file_sha256(path),
                "storage": "catalog_only_immutable_base",
            }
        )

    record = {
        "schema_version": "viv_backup_manifest_v1",
        "created_at": _utc(),
        "trigger": trigger,
        "parent_snapshot": _head(),
        "source_root": _posix(VIV_ROOT),
        "vault": _posix(VAULT_ROOT),
        "policy": {
            "copy_sovereign_assets": True,
            "immutable_bases": "hash_catalog_only",
            "minimum_free_bytes": MIN_FREE_BYTES,
            "restore": "staged_then_approved",
            "transaction_failure_rollback": True,
        },
        "copied_items": copied,
        "catalog_only_items": catalog,
        "skipped_items": skipped,
    }
    snapshot_id = _sha256_bytes(_stable_json(record).encode("utf-8"))
    missing_bytes = sum(
        row["bytes"] for row in copied if not _object_path(str(row["sha256"])).is_file()
    )
    if shutil.disk_usage(VAULT_ROOT.parent).free - missing_bytes < MIN_FREE_BYTES:
        raise BackupError("snapshot would violate the 12 GB free-space reserve")
    operation_id = _operation_id("snapshot")
    intent_hash = snapshot_id
    verdict = _require_authorized(
        _request(
            action="SNAPSHOT",
            operation_id=operation_id,
            snapshot_id=snapshot_id,
            actor_role="artifact_controller",
            manifest_hash=intent_hash,
            source_paths=roots,
            target_paths=(VAULT_ROOT, _manifest_path(snapshot_id)),
            max_bytes=max(logical_bytes, 1),
        )
    )

    new_object_bytes = 0
    for row in copied:
        source = Path(str(row["path"]))
        obj, created = _copy_object(source, str(row["sha256"]))
        if created:
            new_object_bytes += obj.stat().st_size
    manifest = {
        "snapshot_id": snapshot_id,
        "manifest_sha256": snapshot_id,
        "record": record,
        "security": {
            "policy_version": verdict.get("policy_version"),
            "decision_id": verdict.get("decision_id"),
        },
    }
    _atomic_text(_manifest_path(snapshot_id), json.dumps(manifest, indent=2, ensure_ascii=False))
    _atomic_text(HEAD_PATH, snapshot_id)
    return SnapshotResult(
        snapshot_id=snapshot_id,
        manifest_path=_manifest_path(snapshot_id),
        copied_items=len(copied),
        catalog_items=len(catalog),
        logical_bytes=logical_bytes,
        new_object_bytes=new_object_bytes,
        decision_id=str(verdict.get("decision_id") or ""),
    )


def verify_snapshot(
    snapshot_id: str | None = None,
    *,
    enforce_security: bool = True,
    verify_catalog: bool = True,
) -> dict[str, Any]:
    selected = snapshot_id or _head()
    if not selected:
        raise BackupError("vault has no snapshot")
    path = _manifest_path(selected)
    if not path.is_file():
        raise BackupError(f"manifest missing: {selected}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    record = manifest.get("record")
    if not isinstance(record, dict):
        raise BackupError("manifest record is malformed")
    computed = _sha256_bytes(_stable_json(record).encode("utf-8"))
    if (
        computed != selected
        and record.get("trigger") == "pre_change_bootstrap"
        and BOOTSTRAP_REPORT.is_file()
    ):
        # The one-time pre-0.2.7 PowerShell bootstrap used insertion-order JSON.
        # It is accepted only when bound to the independently verified report.
        ordered = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
        bootstrap = json.loads(BOOTSTRAP_REPORT.read_text(encoding="utf-8"))
        if bootstrap.get("snapshot_id") == selected:
            computed = _sha256_bytes(ordered.encode("utf-8"))
    if computed != selected or manifest.get("snapshot_id") != selected:
        raise BackupError("manifest hash does not match snapshot id")
    if enforce_security:
        _require_authorized(
            _request(
                action="VERIFY",
                operation_id=_operation_id("verify"),
                snapshot_id=selected,
                actor_role="deterministic_authority",
                manifest_hash=computed,
                source_paths=(VAULT_ROOT,),
                target_paths=(EVIDENCE_ROOT,),
                max_bytes=max(path.stat().st_size, 1),
            )
        )
    object_failures: list[str] = []
    logical_bytes = 0
    for row in record.get("copied_items") or []:
        logical_bytes += int(row.get("bytes") or 0)
        obj = VAULT_ROOT / str(row.get("object") or "")
        expected = str(row.get("sha256") or "")
        if not obj.is_file() or _file_sha256(obj) != expected:
            object_failures.append(str(row.get("path") or obj))
    catalog_drift: list[str] = []
    if verify_catalog:
        for row in record.get("catalog_only_items") or []:
            source = Path(str(row.get("path") or ""))
            expected = str(row.get("sha256") or "")
            if not source.is_file() or _file_sha256(source) != expected:
                catalog_drift.append(_posix(source))
    ok = not object_failures and not catalog_drift
    return {
        "ok": ok,
        "snapshot_id": selected,
        "manifest_path": _posix(path),
        "copied_items": len(record.get("copied_items") or []),
        "catalog_items": len(record.get("catalog_only_items") or []),
        "logical_bytes": logical_bytes,
        "object_failures": object_failures,
        "catalog_drift": catalog_drift,
    }


def stage_restore(
    snapshot_id: str,
    *,
    targets: Iterable[Path | str] | None = None,
) -> dict[str, Any]:
    verification = verify_snapshot(snapshot_id, verify_catalog=False)
    if not verification["ok"]:
        raise BackupError(f"snapshot cannot be staged: {verification}")
    manifest = json.loads(_manifest_path(snapshot_id).read_text(encoding="utf-8"))
    rows = manifest["record"]["copied_items"]
    selected = {_posix(_validate_live_target(Path(path))).lower() for path in targets or ()}
    if selected:
        rows = [row for row in rows if str(row["path"]).lower() in selected]
        missing = selected - {str(row["path"]).lower() for row in rows}
        if missing:
            raise BackupError(f"restore targets absent from snapshot: {sorted(missing)}")
    if not rows:
        raise BackupError("restore plan contains no files")
    operation_id = _operation_id("restore-stage")
    staging = RESTORE_STAGING_ROOT / operation_id
    plan_seed = {
        "snapshot_id": snapshot_id,
        "operation_id": operation_id,
        "targets": [row["path"] for row in rows],
    }
    plan_seed_hash = _sha256_bytes(_stable_json(plan_seed).encode("utf-8"))
    _require_authorized(
        _request(
            action="RESTORE_STAGE",
            operation_id=operation_id,
            snapshot_id=snapshot_id,
            actor_role="deterministic_authority",
            manifest_hash=plan_seed_hash,
            source_paths=(VAULT_ROOT,),
            target_paths=(staging,),
            max_bytes=max(sum(int(row["bytes"]) for row in rows), 1),
        )
    )
    staging.mkdir(parents=True, exist_ok=False)
    plan_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        source = VAULT_ROOT / row["object"]
        staged = staging / "files" / f"{index:06d}.bin"
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, staged)
        if _file_sha256(staged) != row["sha256"]:
            raise BackupError(f"staged restore hash mismatch: {row['path']}")
        target = _validate_live_target(Path(row["path"]))
        current_hash = _file_sha256(target) if target.is_file() else None
        plan_rows.append(
            {
                "target": _posix(target),
                "staged": _posix(staged),
                "expected_current_sha256": current_hash,
                "restore_sha256": row["sha256"],
                "bytes": row["bytes"],
            }
        )
    core = {
        "schema_version": "viv_restore_plan_v1",
        "created_at": _utc(),
        "snapshot_id": snapshot_id,
        "operation_id": operation_id,
        "items": plan_rows,
    }
    plan_hash = _sha256_bytes(_stable_json(core).encode("utf-8"))
    plan = {**core, "plan_hash": plan_hash, "approval_phrase": f"ARCHITECT_APPROVED:{plan_hash}"}
    plan_path = staging / "restore_plan.json"
    _atomic_text(plan_path, json.dumps(plan, indent=2))
    return {
        "ok": True,
        "snapshot_id": snapshot_id,
        "operation_id": operation_id,
        "plan_hash": plan_hash,
        "plan_path": _posix(plan_path),
        "items": len(plan_rows),
        "live_changed": False,
    }


def commit_restore(plan_path: Path | str, *, architect_approval: str) -> dict[str, Any]:
    """Commit an already staged restore; never called by automated training."""
    path = Path(plan_path).resolve(strict=True)
    if not _under(path, RESTORE_STAGING_ROOT):
        raise BackupError("restore plan is outside staging")
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan_hash = str(plan.get("plan_hash") or "")
    core = {key: value for key, value in plan.items() if key not in {"plan_hash", "approval_phrase"}}
    if _sha256_bytes(_stable_json(core).encode("utf-8")) != plan_hash:
        raise BackupError("restore plan hash mismatch")
    if architect_approval != f"ARCHITECT_APPROVED:{plan_hash}":
        raise BackupError("explicit Architect approval phrase is missing")
    items = plan.get("items") or []
    targets = [_validate_live_target(Path(item["target"])) for item in items]
    for item, target in zip(items, targets, strict=True):
        current = _file_sha256(target) if target.is_file() else None
        if current != item.get("expected_current_sha256"):
            raise BackupError(f"restore target changed after staging: {target}")
        staged = Path(item["staged"]).resolve(strict=True)
        if not _under(staged, path.parent) or _file_sha256(staged) != item["restore_sha256"]:
            raise BackupError(f"invalid staged restore object: {staged}")

    safety = create_snapshot(trigger=f"pre_restore:{plan_hash[:12]}", paths=targets)
    verdict = _require_authorized(
        _request(
            action="RESTORE_COMMIT",
            operation_id=str(plan["operation_id"]),
            snapshot_id=str(plan["snapshot_id"]),
            actor_role="architect",
            manifest_hash=plan_hash,
            source_paths=(path.parent,),
            target_paths=targets,
            max_bytes=max(sum(int(item["bytes"]) for item in items), 1),
            architect_approved=True,
        )
    )
    safety_manifest = json.loads(safety.manifest_path.read_text(encoding="utf-8"))
    safety_by_path = {
        str(item["path"]).lower(): item for item in safety_manifest["record"]["copied_items"]
    }
    changed: list[Path] = []
    try:
        for item, target in zip(items, targets, strict=True):
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, raw = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".restore-tmp", dir=target.parent)
            os.close(fd)
            temp = Path(raw)
            try:
                shutil.copyfile(Path(item["staged"]), temp)
                if _file_sha256(temp) != item["restore_sha256"]:
                    raise BackupError(f"restore copy verification failed: {target}")
                os.replace(temp, target)
                changed.append(target)
            finally:
                temp.unlink(missing_ok=True)
        for item, target in zip(items, targets, strict=True):
            if _file_sha256(target) != item["restore_sha256"]:
                raise BackupError(f"post-restore verification failed: {target}")
    except Exception:
        for target in reversed(changed):
            previous = safety_by_path.get(_posix(target).lower())
            if previous is None:
                target.unlink(missing_ok=True)
                continue
            source = VAULT_ROOT / previous["object"]
            shutil.copyfile(source, target)
            if _file_sha256(target) != previous["sha256"]:
                raise BackupError(f"transaction rollback failed: {target}")
        raise
    return {
        "ok": True,
        "operation_id": plan["operation_id"],
        "restored_items": len(changed),
        "safety_snapshot": safety.snapshot_id,
        "decision_id": verdict.get("decision_id"),
    }


def bootstrap_status() -> dict[str, Any]:
    if not BOOTSTRAP_REPORT.is_file():
        return {"ok": False, "reason": "bootstrap_restore_verification_missing"}
    report = json.loads(BOOTSTRAP_REPORT.read_text(encoding="utf-8"))
    try:
        verification = verify_snapshot(
            str(report.get("snapshot_id") or ""),
            enforce_security=False,
            verify_catalog=False,
        )
    except (BackupError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "reason": str(exc)}
    return {
        "ok": bool(report.get("ok")) and verification.get("ok"),
        "report": report,
        "verification": verification,
    }


def ensure_pre_mutation_snapshot(
    *,
    trigger: str,
    paths: Iterable[Path | str],
) -> dict[str, Any]:
    """Create and verify the exact safety snapshot required by a mutation."""
    result = create_snapshot(trigger=trigger, paths=paths)
    verification = verify_snapshot(result.snapshot_id, verify_catalog=False)
    if not verification.get("ok"):
        raise BackupError(f"pre-mutation snapshot failed verification: {verification}")
    return {"snapshot": result.as_dict(), "verification": verification}


def secure_write_evidence_text(path: Path | str, payload: str) -> dict[str, Any]:
    """Write backup evidence through the Rust VERIFY capability."""
    destination = Path(path).resolve(strict=False)
    if not _under(destination, EVIDENCE_ROOT):
        raise BackupError(f"backup evidence path is outside evidence root: {destination}")
    digest = _sha256_bytes(payload.encode("utf-8"))
    verdict = _require_authorized(
        _request(
            action="VERIFY",
            operation_id=_operation_id("evidence"),
            snapshot_id=_head(),
            actor_role="deterministic_authority",
            manifest_hash=digest,
            source_paths=(VAULT_ROOT,),
            target_paths=(destination,),
            max_bytes=max(len(payload.encode("utf-8")), 1),
        )
    )
    _atomic_text(destination, payload)
    return verdict


def secure_write_evidence_json(path: Path | str, payload: dict[str, Any]) -> dict[str, Any]:
    return secure_write_evidence_text(path, json.dumps(payload, indent=2, ensure_ascii=False))
