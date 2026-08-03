"""Python facade for Rust-governed training transactions.

All privileged training code calls this module.  It computes a fresh Master RID
sample, obtains a typed Rust verdict, and exposes atomic artifact writes or a
process-bound staging lease.  A missing/old Rust API always denies.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable

from lib.master_rid import compute_master_rid
from lib.rid_telemetry import sample_once
from lib.security_bridge import (
    authorize_training,
    begin_training_lease,
    commit_training_lease,
    freeze_training_registry,
    quarantine_training_payload,
    read_training_quarantine,
    verify_training_ledger,
)
from lib.security_membrane import require_membrane
from lib.triad_kernel import (
    TriadDenied,
    TriadEnvelope,
    emit,
    open_context,
)

POLICY_VERSION = "viv_training_security_v1"
DEFAULT_STAGE = "tree_control"
_BACKUP_BASELINE_PATHS = (
    Path(r"L:\Continue\Viv\foundation\model_config.json"),
    Path(r"L:\Continue\Viv\foundation\artifacts\auto\shadow_judge\holdout_registry.json"),
    Path(r"L:\Continue\Viv\foundation\artifacts\auto\shadow_judge\deploy_test_registry.json"),
    Path(
        r"L:\Continue\Viv\foundation\artifacts\auto\openaster_parity"
        r"\development_registry_v1.json"
    ),
    Path(
        r"L:\Continue\Viv\foundation\artifacts\auto\openaster_training_tree"
        r"\seed_registry_v2.json"
    ),
)


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def manifest_hash(value: Any) -> str:
    return sha256_text(stable_json(value))


def fresh_master_s_n() -> tuple[float, dict[str, Any]]:
    """Read current hardware instead of trusting the possibly stale published file."""
    master = compute_master_rid(sample_once())
    evidence = {
        "timestamp": master.timestamp,
        "master_s_n": master.master_s_n,
        "status": master.status,
        "n_subsystems": master.n_subsystems,
    }
    return float(master.master_s_n), evidence


def make_request(
    *,
    action: str,
    stage_id: str,
    run_id: str,
    model_role: str,
    manifest_sha256: str,
    source_hashes: Iterable[str] = (),
    paths: Iterable[Path | str] = (),
    artifact_class: str,
    master_s_n: float,
    max_duration_s: int = 3600,
    max_vram_mib: int = 8192,
    max_ram_mib: int = 28672,
    max_disk_mib: int = 2048,
    sequence_cap: int = 384,
    lora_rank: int = 16,
) -> dict[str, Any]:
    return {
        "action": action,
        "stage_id": stage_id,
        "run_id": run_id,
        "model_role": model_role,
        "manifest_hash": manifest_sha256,
        "source_hashes": list(source_hashes),
        "paths": [str(path).replace("\\", "/") for path in paths],
        "artifact_class": artifact_class,
        "master_s_n": float(master_s_n),
        "process_id": os.getpid(),
        "max_duration_s": int(max_duration_s),
        "max_vram_mib": int(max_vram_mib),
        "max_ram_mib": int(max_ram_mib),
        "max_disk_mib": int(max_disk_mib),
        "sequence_cap": int(sequence_cap),
        "lora_rank": int(lora_rank),
    }


def require_training_security() -> dict[str, Any]:
    membrane = require_membrane()
    if membrane is not None:
        raise PermissionError(f"security_membrane:{membrane.get('reason')}")
    ledger = verify_training_ledger()
    if not ledger.get("ok"):
        raise PermissionError(f"security_training_ledger:{ledger.get('error')}")
    return ledger


def require_pre_mutation_backup(
    *,
    trigger: str,
    paths: Iterable[Path | str] = (),
) -> dict[str, Any]:
    """Create a verified safety snapshot before a privileged mutation."""
    from lib.backup_core import ensure_pre_mutation_snapshot

    selected: list[Path] = []
    for raw in (*_BACKUP_BASELINE_PATHS, *tuple(paths)):
        candidate = Path(raw)
        if candidate.exists() and candidate not in selected:
            selected.append(candidate)
    if not selected:
        raise PermissionError("backup_precondition:no_existing_safety_sources")
    try:
        return ensure_pre_mutation_snapshot(trigger=trigger, paths=selected)
    except Exception as exc:  # noqa: BLE001 - fail closed at the privilege boundary
        raise PermissionError(f"backup_precondition:{exc}") from exc


def gate_record(
    *,
    text: str,
    direction: str,
    action: str,
    stage_id: str,
    run_id: str,
    model_role: str,
    manifest_sha256: str,
    artifact_class: str,
    paths: Iterable[Path | str] = (),
    source_hashes: Iterable[str] = (),
) -> dict[str, Any]:
    require_training_security()
    s_n, rid = fresh_master_s_n()
    try:
        context = open_context(
            TriadEnvelope.build(
                actor=model_role,
                source=f"training:{stage_id}",
                target="training_security",
                action=f"{action}_{direction.upper()}",
                payload={"text": text, "run_id": run_id},
                s_n=s_n,
            )
        )
        if direction.upper() == "IN":
            membrane = context.security_ingress
            triad_receipt = None
        else:
            _, triad_receipt = emit(context, text)
            membrane = triad_receipt.security
    except TriadDenied as exc:
        return {
            "allowed": False, "disposition": "DENY",
            "reason": exc.reason, "rule": "triad",
            "master_rid": rid,
            "membrane": exc.evidence,
        }
    request = make_request(
        action=action, stage_id=stage_id, run_id=run_id,
        model_role=model_role, manifest_sha256=manifest_sha256,
        source_hashes=source_hashes, paths=paths, artifact_class=artifact_class,
        master_s_n=s_n,
    )
    verdict = authorize_training(request)
    return {
        **verdict,
        "master_rid": rid,
        "membrane": membrane,
        "triad": {
            "context_id": context.context_id,
            "receipt": triad_receipt.to_dict() if triad_receipt is not None else None,
        },
    }


def authorize_artifact(
    *,
    path: Path,
    payload: Any,
    stage_id: str = DEFAULT_STAGE,
    run_id: str = "tree-control",
    artifact_class: str = "training_evidence",
    action: str = "EVALUATE",
    model_role: str = "artifact_controller",
) -> dict[str, Any]:
    encoded = stable_json(payload) if not isinstance(payload, str) else payload
    require_training_security()
    s_n, rid = fresh_master_s_n()
    request = make_request(
        action=action, stage_id=stage_id, run_id=run_id,
        model_role=model_role, manifest_sha256=sha256_text(encoded),
        source_hashes=(sha256_text(encoded),), paths=(path,),
        artifact_class=artifact_class, master_s_n=s_n,
    )
    return {**authorize_training(request), "master_rid": rid}


def secure_write_json(
    path: Path,
    payload: dict[str, Any],
    *,
    stage_id: str = DEFAULT_STAGE,
    run_id: str = "tree-control",
    artifact_class: str = "training_evidence",
    action: str = "EVALUATE",
    model_role: str = "artifact_controller",
) -> dict[str, Any]:
    encoded = json.dumps(payload, indent=2, ensure_ascii=False)
    verdict = authorize_artifact(
        path=path, payload=encoded, stage_id=stage_id,
        run_id=run_id, artifact_class=artifact_class,
        action=action, model_role=model_role,
    )
    if not verdict.get("allowed"):
        raise PermissionError(f"security_denied_write:{verdict}")
    # The bytes written must be exactly the bytes authorized. Security evidence
    # belongs in the Rust hash-chained ledger, not in a self-altering payload.
    _atomic_text(path, encoded)
    return verdict


def secure_write_jsonl(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    stage_id: str = DEFAULT_STAGE,
    run_id: str = "tree-control",
    artifact_class: str = "training_evidence",
    action: str = "EVALUATE",
    model_role: str = "artifact_controller",
) -> dict[str, Any]:
    payload = "".join(stable_json(row) + "\n" for row in rows)
    verdict = authorize_artifact(
        path=path, payload=payload, stage_id=stage_id,
        run_id=run_id, artifact_class=artifact_class,
        action=action, model_role=model_role,
    )
    if not verdict.get("allowed"):
        raise PermissionError(f"security_denied_write:{verdict}")
    _atomic_text(path, payload)
    return verdict


def secure_write_text(
    path: Path,
    payload: str,
    *,
    stage_id: str = DEFAULT_STAGE,
    run_id: str = "tree-control",
    artifact_class: str = "training_evidence",
    action: str = "EVALUATE",
    model_role: str = "artifact_controller",
) -> dict[str, Any]:
    verdict = authorize_artifact(
        path=path, payload=payload, stage_id=stage_id,
        run_id=run_id, artifact_class=artifact_class,
        action=action, model_role=model_role,
    )
    if not verdict.get("allowed"):
        raise PermissionError(f"security_denied_write:{verdict}")
    _atomic_text(path, payload)
    return verdict


def secure_write_candidate_pointer(
    path: Path,
    payload: dict[str, Any],
    *,
    stage_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Write a validation-only pointer through the typed PROMOTE capability."""
    require_pre_mutation_backup(
        trigger=f"pre_candidate_pointer:{stage_id}:{run_id}",
        paths=(path,),
    )
    encoded = json.dumps(payload, indent=2, ensure_ascii=False)
    require_training_security()
    s_n, rid = fresh_master_s_n()
    digest = sha256_text(encoded)
    request = make_request(
        action="PROMOTE",
        stage_id=stage_id,
        run_id=run_id,
        model_role="deterministic_authority",
        manifest_sha256=digest,
        source_hashes=(digest,),
        paths=(path,),
        artifact_class="candidate_pointer",
        master_s_n=s_n,
    )
    verdict = authorize_training(request)
    if not verdict.get("allowed"):
        raise PermissionError(f"security_denied_candidate_pointer:{verdict}")
    _atomic_text(path, encoded)
    return {**verdict, "master_rid": rid}


def secure_freeze_training_registry(
    path: Path,
    payload: dict[str, Any],
    *,
    stage_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Create a typed frozen training registry atomically inside Rust."""
    require_pre_mutation_backup(
        trigger=f"pre_training_registry_freeze:{stage_id}:{run_id}",
        paths=(path,),
    )
    encoded = json.dumps(payload, indent=2, ensure_ascii=False)
    require_training_security()
    s_n, rid = fresh_master_s_n()
    digest = sha256_text(encoded)
    request = make_request(
        action="FREEZE",
        stage_id=stage_id,
        run_id=run_id,
        model_role="deterministic_authority",
        manifest_sha256=digest,
        source_hashes=(digest,),
        paths=(path,),
        artifact_class="training_evidence",
        master_s_n=s_n,
    )
    verdict = freeze_training_registry(request, encoded)
    if not verdict.get("allowed"):
        raise PermissionError(f"security_denied_registry_freeze:{verdict}")
    if not path.is_file():
        raise PermissionError("security_registry_freeze_missing_after_allow")
    actual = path.read_text(encoding="utf-8")
    if actual != encoded:
        raise PermissionError(
            "security_registry_freeze_bytes_mismatch_after_allow"
        )
    return {**verdict, "master_rid": rid}


def secure_freeze_stage1_registry(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Back-compatible evidence-truth Stage 1 registry freeze."""
    return secure_freeze_training_registry(
        path,
        payload,
        stage_id="evidence_truth",
        run_id="stage1-freeze",
    )


def _atomic_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".security-tmp", dir=str(path.parent)
    )
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


@dataclass
class TrainingLease:
    token: str
    staging_root: Path
    final_root: Path
    request_manifest: str
    stage_id: str
    run_id: str
    rid: dict[str, Any]
    model_role: str
    artifact_class: str
    source_hashes: tuple[str, ...]
    max_duration_s: int
    max_vram_mib: int
    max_ram_mib: int
    max_disk_mib: int
    sequence_cap: int
    lora_rank: int

    def commit(self) -> dict[str, Any]:
        s_n, rid = fresh_master_s_n()
        request = make_request(
            action="COMMIT_RUN", stage_id=self.stage_id, run_id=self.run_id,
            model_role=self.model_role, manifest_sha256=self.request_manifest,
            source_hashes=self.source_hashes,
            paths=(self.staging_root, self.final_root),
            artifact_class=self.artifact_class, master_s_n=s_n,
            max_duration_s=self.max_duration_s,
            max_vram_mib=self.max_vram_mib,
            max_ram_mib=self.max_ram_mib,
            max_disk_mib=self.max_disk_mib,
            sequence_cap=self.sequence_cap,
            lora_rank=self.lora_rank,
        )
        verdict = commit_training_lease(self.token, request)
        verdict["master_rid"] = rid
        return verdict

    def quarantine(self, record_id: str, text: str) -> dict[str, Any]:
        return quarantine_training_payload(self.token, record_id, text)

    def read_quarantine(self, record_id: str) -> str:
        result = read_training_quarantine(self.token, record_id)
        if not result.get("allowed"):
            raise PermissionError(f"security_denied_quarantine_read:{result}")
        return str(result.get("payload") or "")


def begin_run_lease(
    *,
    stage_id: str,
    run_id: str,
    manifest_sha256: str,
    source_hashes: Iterable[str],
    max_duration_s: int,
    max_disk_mib: int,
    lora_rank: int = 16,
    model_role: str = "openaster_target",
    artifact_class: str = "lora_adapter",
    max_vram_mib: int = 8192,
    max_ram_mib: int = 28672,
    sequence_cap: int = 384,
) -> TrainingLease:
    require_pre_mutation_backup(
        trigger=f"pre_training_run:{stage_id}:{run_id}",
    )
    require_training_security()
    bound_source_hashes = tuple(source_hashes)
    s_n, rid = fresh_master_s_n()
    staging = Path("L:/Continue/Viv/sandbox/training_staging") / run_id
    final = Path("L:/Continue/Viv/foundation/models/Training/runs") / run_id
    request = make_request(
        action="BEGIN_RUN", stage_id=stage_id, run_id=run_id,
        model_role=model_role, manifest_sha256=manifest_sha256,
        source_hashes=bound_source_hashes, paths=(staging, final),
        artifact_class=artifact_class, master_s_n=s_n,
        max_duration_s=max_duration_s, max_disk_mib=max_disk_mib,
        lora_rank=lora_rank, max_vram_mib=max_vram_mib,
        max_ram_mib=max_ram_mib, sequence_cap=sequence_cap,
    )
    verdict = begin_training_lease(request)
    if not verdict.get("allowed") or not verdict.get("lease_token"):
        raise PermissionError(f"security_denied_lease:{verdict}")
    return TrainingLease(
        token=str(verdict["lease_token"]),
        staging_root=Path(str(verdict["staging_root"])),
        final_root=Path(str(verdict["final_root"])),
        request_manifest=manifest_sha256,
        stage_id=stage_id,
        run_id=run_id,
        rid=rid,
        model_role=model_role,
        artifact_class=artifact_class,
        source_hashes=bound_source_hashes,
        max_duration_s=max_duration_s,
        max_vram_mib=max_vram_mib,
        max_ram_mib=max_ram_mib,
        max_disk_mib=max_disk_mib,
        sequence_cap=sequence_cap,
        lora_rank=lora_rank,
    )
