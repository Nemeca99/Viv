"""AIOS Engineering Governor.

The Governor does not grant Viv permission to rewrite protected source.  It
governs externally authorized engineering work as a transaction: discover,
backup, preflight evidence, reconcile, and journal.  Runtime self-modification
remains blocked by the Rust laws.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Iterable
import uuid

from lib.backup_core import ensure_pre_mutation_snapshot
from lib.paths import AUTO_ARTIFACTS, FOUNDATION_ROOT, VIV_ROOT
from lib.triad_kernel import (
    TRIAD_CONTRACT_VERSION,
    TriadContext,
    TriadDenied,
    TriadEnvelope,
    authorize_operation,
    dispatch,
    emit,
    open_context,
    verify_triad_ledger,
)


GOVERNOR_VERSION = "viv_engineering_governor_v1"
GOVERNOR_ROOT = AUTO_ARTIFACTS / "engineering_governor"
TRANSACTIONS_ROOT = GOVERNOR_ROOT / "transactions"
LATEST_PATH = GOVERNOR_ROOT / "latest.json"
SESSION_JOURNAL = FOUNDATION_ROOT / "artifacts" / "audit" / "session_journal.md"
DENIED_ACTORS = {"model", "self", "self_authorizing_model", "gpu_mouth", "teacher"}
IGNORED_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "target",
    "backup_core",
}


class GovernorError(RuntimeError):
    """Fail-closed engineering transaction error."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _as_posix(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _scope_digest(paths: Iterable[Path | str]) -> dict[str, Any]:
    """Represent protected scope at general ingress without exposing raw paths."""
    normalized = sorted(_as_posix(path) for path in paths)
    return {
        "count": len(normalized),
        "sha256": _sha256_bytes(_stable_json(normalized).encode("utf-8")),
    }


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _validate_path(path: Path) -> Path:
    if ".." in path.parts:
        raise GovernorError(f"path traversal denied: {path}")
    resolved = path.resolve(strict=False)
    if not _under(resolved, VIV_ROOT):
        raise GovernorError(f"engineering scope outside Viv denied: {path}")
    return resolved


def _inventory(paths: Iterable[Path | str]) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for raw in paths:
        selected = _validate_path(Path(raw))
        candidates = [selected] if selected.is_file() else (
            selected.rglob("*") if selected.is_dir() else []
        )
        for candidate in candidates:
            if not candidate.is_file() or any(part in IGNORED_PARTS for part in candidate.parts):
                continue
            stat = candidate.stat()
            inventory[_as_posix(candidate)] = {
                "sha256": _file_sha256(candidate),
                "bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
    return dict(sorted(inventory.items()))


@dataclass(frozen=True)
class EngineeringSpec:
    objective: str
    actor: str
    mutation_paths: tuple[str, ...]
    scope_roots: tuple[str, ...]
    expected_changes: tuple[str, ...] = ()
    known_baseline_failures: tuple[str, ...] = ()
    s_n: float = 0.60
    transaction_id: str = field(default_factory=lambda: f"eng-{uuid.uuid4().hex[:16]}")
    contract_version: str = TRIAD_CONTRACT_VERSION
    governor_version: str = GOVERNOR_VERSION

    def validate(self) -> None:
        if not self.objective.strip():
            raise GovernorError("missing objective")
        if self.actor.strip().lower() in DENIED_ACTORS:
            raise GovernorError("self-authorizing actor denied")
        if not self.mutation_paths or not self.scope_roots:
            raise GovernorError("mutation paths and scope roots are required")
        if self.contract_version != TRIAD_CONTRACT_VERSION:
            raise GovernorError("Triad contract version mismatch")
        for value in (*self.mutation_paths, *self.scope_roots):
            _validate_path(Path(value))


def _open_governor_context(spec: EngineeringSpec, action: str, payload: Any) -> TriadContext:
    return open_context(
        TriadEnvelope.build(
            actor=spec.actor,
            source="engineering_governor",
            target="aios_source",
            action=action,
            payload=payload,
            s_n=spec.s_n,
            trace_id=spec.transaction_id,
        ),
        ttl_s=900.0,
    )


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _secure_write(context: TriadContext, path: Path, payload: str) -> dict[str, Any]:
    encoded = payload.encode("utf-8")
    params = {
        "path": _as_posix(path),
        "content_sha256": _sha256_bytes(encoded),
        "bytes": len(encoded),
    }

    def _write() -> str:
        _atomic_write(path, payload)
        return _as_posix(path)

    _, receipt = dispatch(
        context,
        operation="engineering.evidence.write",
        params=params,
        handler=_write,
        tool_name="write_file",
    )
    return receipt.to_dict()


def _transaction_path(transaction_id: str) -> Path:
    return TRANSACTIONS_ROOT / f"{transaction_id}.json"


def begin_transaction(spec: EngineeringSpec, *, dry_run: bool = False) -> dict[str, Any]:
    """Discover and snapshot an external engineering mutation before it starts."""
    spec.validate()
    baseline = _inventory(spec.scope_roots)
    payload = {
        "transaction_id": spec.transaction_id,
        "actor": spec.actor,
        "objective_sha256": _sha256_bytes(spec.objective.encode("utf-8")),
        "mutation_scope": _scope_digest(spec.mutation_paths),
        "inventory_scope": _scope_digest(spec.scope_roots),
        "baseline_files": len(baseline),
        "dry_run": dry_run,
    }
    context = _open_governor_context(spec, "ENGINEERING_BEGIN", payload)
    authorization = authorize_operation(
        context,
        operation="engineering.external_change.prepare",
        params={
            "transaction_id": spec.transaction_id,
            "mutation_paths": list(spec.mutation_paths),
            "dry_run": dry_run,
        },
    )
    backup = None
    if not dry_run:
        existing = [Path(path) for path in spec.mutation_paths if Path(path).exists()]
        if not existing:
            raise GovernorError("no existing mutation paths available for safety snapshot")
        backup = ensure_pre_mutation_snapshot(
            trigger=f"engineering_governor:{spec.transaction_id}",
            paths=existing,
        )
    record = {
        "schema_version": GOVERNOR_VERSION,
        "contract_version": TRIAD_CONTRACT_VERSION,
        "transaction_id": spec.transaction_id,
        "state": "DRY_RUN" if dry_run else "PREPARED",
        "prepared_at": _utc(),
        "spec": asdict(spec),
        "baseline": baseline,
        "backup": backup,
        "authorization": authorization.to_dict(),
        "triad_context": {
            "context_id": context.context_id,
            "pillar_versions": context.pillar_versions,
        },
        "classification": None,
        "verification": None,
    }
    path = _transaction_path(spec.transaction_id)
    record["evidence_receipt"] = _secure_write(
        context, path, json.dumps(record, indent=2, ensure_ascii=False)
    )
    _secure_write(context, LATEST_PATH, json.dumps(record, indent=2, ensure_ascii=False))
    return {**record, "path": _as_posix(path)}


def reconcile_transaction(
    transaction_path: Path | str,
    *,
    verification: dict[str, Any],
    classification: str,
    journal_summary: str,
) -> dict[str, Any]:
    """Compare actual changes with declared scope and close the transaction."""
    path = Path(transaction_path)
    record = json.loads(path.read_text(encoding="utf-8"))
    spec = EngineeringSpec(**record["spec"])
    spec.validate()
    if classification not in {
        "PASS",
        "PRE_EXISTING",
        "REGRESSION",
        "ENVIRONMENT",
        "RESOURCE",
        "TEST_HARNESS",
        "BLOCKED",
    }:
        raise GovernorError("invalid failure classification")
    current = _inventory(spec.scope_roots)
    baseline = dict(record.get("baseline") or {})
    changed = sorted(
        key for key in set(baseline) & set(current) if baseline[key] != current[key]
    )
    created = sorted(set(current) - set(baseline))
    deleted = sorted(set(baseline) - set(current))
    allowed_roots = [_validate_path(Path(value)) for value in spec.mutation_paths]

    def declared(raw: str) -> bool:
        candidate = Path(raw)
        return any(candidate == root or _under(candidate, root) for root in allowed_roots)

    unexpected = sorted(
        raw for raw in (*changed, *created, *deleted) if not declared(raw)
    )
    ok = bool(verification.get("ok")) and not unexpected and classification == "PASS"
    context = _open_governor_context(
        spec,
        "ENGINEERING_RECONCILE",
        {
            "verification": verification,
            "changed": _scope_digest(changed),
            "created": _scope_digest(created),
            "deleted": _scope_digest(deleted),
            "unexpected": _scope_digest(unexpected),
        },
    )
    authorize_operation(
        context,
        operation="engineering.external_change.reconcile",
        params={"transaction_id": spec.transaction_id, "ok": ok},
    )
    closed = {
        **record,
        "state": "VERIFIED" if ok else "FAILED",
        "closed_at": _utc(),
        "classification": classification,
        "verification": verification,
        "changes": {
            "changed": changed,
            "created": created,
            "deleted": deleted,
            "unexpected": unexpected,
        },
        "triad_ledger": verify_triad_ledger(),
    }
    emitted, receipt = emit(context, {"ok": ok, "transaction_id": spec.transaction_id})
    closed["egress"] = {"payload": emitted, "receipt": receipt.to_dict()}
    closed["evidence_receipt"] = _secure_write(
        context, path, json.dumps(closed, indent=2, ensure_ascii=False)
    )
    _secure_write(context, LATEST_PATH, json.dumps(closed, indent=2, ensure_ascii=False))

    prior = SESSION_JOURNAL.read_text(encoding="utf-8") if SESSION_JOURNAL.is_file() else ""
    entry = (
        f"\n\n## AIOS Engineering Governor — {spec.transaction_id}\n\n"
        f"- Result: **{'PASS' if ok else 'FAIL'}**\n"
        f"- Classification: `{classification}`\n"
        f"- Objective: {spec.objective}\n"
        f"- Backup: `{((record.get('backup') or {}).get('snapshot') or {}).get('snapshot_id')}`\n"
        f"- Changed/created/deleted: {len(changed)}/{len(created)}/{len(deleted)}\n"
        f"- Unexpected changes: {len(unexpected)}\n"
        f"- Evidence: `{_as_posix(path)}`\n"
        f"- Summary: {journal_summary}\n"
    )
    _secure_write(context, SESSION_JOURNAL, prior.rstrip() + entry)
    return {**closed, "path": _as_posix(path), "ok": ok}


def governor_status() -> dict[str, Any]:
    latest = {}
    if LATEST_PATH.is_file():
        try:
            latest = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            latest = {"state": "MALFORMED"}
    return {
        "version": GOVERNOR_VERSION,
        "triad_contract_version": TRIAD_CONTRACT_VERSION,
        "latest": latest,
        "triad_ledger": verify_triad_ledger(),
    }
