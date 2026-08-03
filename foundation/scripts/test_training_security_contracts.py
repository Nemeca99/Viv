"""Fail-closed CPU contracts for the Rust-governed training membrane."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.security_bridge import (  # noqa: E402
    authorize_training,
    constitution,
    integrity_status,
    rust_available,
    rust_error,
    verify_training_ledger,
)
from lib.training_security import make_request  # noqa: E402


def _base() -> dict[str, object]:
    return make_request(
        action="EVALUATE",
        stage_id="tree_control",
        run_id="security-contract",
        model_role="artifact_controller",
        manifest_sha256="a" * 64,
        source_hashes=("b" * 64,),
        paths=(
            "L:/Continue/Viv/foundation/artifacts/audit/"
            "training_security_contract_probe.json",
        ),
        artifact_class="training_evidence",
        master_s_n=0.60,
    )


def _deny(request: dict[str, object], rule: str) -> None:
    verdict = authorize_training(request)
    assert not verdict.get("allowed"), verdict
    assert verdict.get("rule") == rule, verdict


def _static_write_scan() -> dict[str, int]:
    """Privileged Stage 1 surfaces may only write in the facade or a Rust lease."""
    targets = [
        FOUNDATION / "scripts" / "training_tree.py",
        FOUNDATION / "scripts" / "finalize_training_tree_milestone.py",
        FOUNDATION / "scripts" / "security_redteam.py",
        FOUNDATION / "lib" / "cpu_semantic_judge.py",
        FOUNDATION / "models" / "Training" / "code" / "train_pairwise_lora.py",
        FOUNDATION / "models" / "Training" / "code" / "train_stage1_pairwise.py",
        FOUNDATION / "models" / "Training" / "code" / "train_stage1_generation.py",
        FOUNDATION / "models" / "Training" / "code"
        / "train_stage1_generation_bootstrap.py",
        FOUNDATION / "scripts" / "stage1_generation_bootstrap_postmortem.py",
        FOUNDATION / "scripts" / "stage1_mouth_identity_curriculum.py",
        FOUNDATION / "scripts" / "stage1_mouth_identity_judge.py",
    ]
    direct_markers = (".write_text(", ".write_bytes(", '.open("w"', '.open("a"', ".open('w'", ".open('a'")
    approved = 0
    checked = 0
    for path in targets:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not any(marker in line for marker in direct_markers):
                continue
            checked += 1
            if "SECURITY_LEASE_WRITE" in line:
                approved += 1
                continue
            raise AssertionError(f"unsecured training write:{path}:{number}:{line.strip()}")
    return {"direct_writes_checked": checked, "lease_writes": approved}


def main() -> int:
    assert rust_available(), f"Rust security unavailable: {rust_error()}"
    assert integrity_status().get("ok"), integrity_status()
    const = constitution()
    version = str(const.get("version") or "")
    assert version.startswith("0.2."), const
    ledger = verify_training_ledger()
    assert ledger.get("ok"), ledger

    allowed = authorize_training(_base())
    assert allowed.get("allowed"), allowed

    parity_eval = _base()
    parity_eval["model_role"] = "parity_mouth_eval"
    parity_eval["artifact_class"] = "evaluation_report"
    parity_allowed = authorize_training(parity_eval)
    assert parity_allowed.get("allowed"), parity_allowed

    parity_draft = parity_eval.copy()
    parity_draft["action"] = "DRAFT"
    parity_draft["artifact_class"] = "draft_set"
    _deny(parity_draft, "capability_matrix")

    worker = """
import os,sys,time
from pathlib import Path
root=Path(r'L:/Continue/Viv/foundation')
repo=root.parent
sys.path[:0]=[str(root),str(repo)]
from lib.security_bridge import authorize_training
from lib.training_security import make_request
time.sleep(max(0.0,float(sys.argv[1])-time.time()))
for index in range(8):
    request=make_request(
        action='EVALUATE',stage_id='tree_control',
        run_id=f'ledger-concurrency-{os.getpid()}',
        model_role='artifact_controller',manifest_sha256='c'*64,
        source_hashes=('d'*64,),
        paths=(f'L:/Continue/Viv/foundation/artifacts/audit/ledger_probe_{os.getpid()}_{index}.json',),
        artifact_class='training_evidence',master_s_n=0.60,
    )
    verdict=authorize_training(request)
    assert verdict.get('allowed'),verdict
"""
    start_at = time.time() + 0.5
    workers = [
        subprocess.Popen(
            [sys.executable, "-c", worker, str(start_at)],
            cwd=str(REPO),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    for process in workers:
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, (stdout, stderr)
    concurrent_ledger = verify_training_ledger()
    assert concurrent_ledger.get("ok"), concurrent_ledger

    request = _base()
    request["action"] = "DEPLOY"
    request["artifact_class"] = "candidate_pointer"
    _deny(request, "training_deploy_disabled")

    request = _base()
    request["master_s_n"] = 0.10
    _deny(request, "law5_stability")

    request = _base()
    request["master_s_n"] = float("nan")
    _deny(request, "request_schema")

    request = _base()
    request["process_id"] = os.getpid() + 1
    _deny(request, "process_binding")

    request = _base()
    request["paths"] = [
        "L:/Continue/Viv/foundation/artifacts_evil/security_contract.json"
    ]
    _deny(request, "path_contract")

    request = _base()
    request["paths"] = [
        "L:/Continue/Viv/foundation/artifacts/auto/../../security_core/Cargo.toml"
    ]
    _deny(request, "path_contract")

    request = _base()
    request["lora_rank"] = 32
    _deny(request, "resource_ceiling")

    request = _base()
    request["model_role"] = "self_authorizing_model"
    _deny(request, "model_role")

    request = _base()
    request["bypass"] = True
    _deny(request, "request_schema")

    replay_shape = make_request(
        action="COMMIT_RUN",
        stage_id="evidence_truth",
        run_id="security-contract-replay",
        model_role="openaster_target",
        manifest_sha256="a" * 64,
        source_hashes=("b" * 64,),
        paths=(
            "L:/Continue/Viv/sandbox/training_staging/security-contract-replay",
            "L:/Continue/Viv/foundation/models/Training/runs/security-contract-replay",
        ),
        artifact_class="lora_adapter",
        master_s_n=0.60,
    )
    _deny(replay_shape, "lease")

    scan = _static_write_scan()
    print(json.dumps({
        "ok": True,
        "security_version": const.get("version"),
        "ledger_events": concurrent_ledger.get("events"),
        "concurrent_writers": 2,
        "concurrent_events": 16,
        "negative_contracts": 11,
        "parity_eval_only": True,
        **scan,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
