#!/usr/bin/env python3
"""Read-only compatibility audit for the 368-row mouth candidate.

This does not load a model or install/authorize a run.  It proves that the
production trainer's row validator accepts the candidate when given its real
row count, and records that the legacy 256-row wrappers are not valid runners
for this campaign.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
CAMPAIGN = TREE / "campaigns/mouth_combined_candidate_v20"
TRAIN = CAMPAIGN / "train_368_candidate_hold.jsonl"
MANIFEST = CAMPAIGN / "manifest.json"
AUDIT = CAMPAIGN / "ADMISSION_AUDIT.json"
LEGACY_RUNNERS = (
    FOUNDATION / "scripts/prepare_mouth_recovery_v2_runner.py",
    FOUNDATION / "scripts/prepare_mouth_full_run_entity_we_v1.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows() -> list[dict]:
    return [json.loads(line) for line in TRAIN.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    if not TRAIN.is_file() or not MANIFEST.is_file() or not AUDIT.is_file():
        raise FileNotFoundError("v20_candidate_artifacts_missing")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    admission = json.loads(AUDIT.read_text(encoding="utf-8"))
    rows = load_rows()

    if len(rows) != 368:
        raise ValueError(f"candidate_rows:{len(rows)}")
    if manifest.get("status") != "COMBINED_CANDIDATE_HOLD_TRAINING_CLOSED":
        raise ValueError("candidate_not_hold_only")
    if manifest.get("training_authorized") is not False or manifest.get("run_authorized") is not False:
        raise ValueError("candidate_authority_open")
    if admission.get("status") != "ADMISSION_AUDIT_PASS" or admission.get("admission_allowed") is not False:
        raise ValueError("admission_contract_not_closed")
    if admission.get("candidate_rows") != 368 or admission.get("candidate_target_pass") != 368:
        raise ValueError("admission_counts_drift")

    # Exercise the exact production row validator on rows already admitted by
    # the source contract.  The entity-we expansion is intentionally still
    # hold-only and must not be silently promoted by this audit.
    import sys

    sys.path.insert(0, str(FOUNDATION))
    from models.Training.code import train_mouth_v3_targeted_patch as trainer

    admitted_rows = [row for row in rows if row.get("split") == "train" and row.get("optimizer_eligible") is True]
    positive_hold_rows = [row for row in rows if row.get("split") == "train_candidate_hold"]
    negative_hold_rows = [row for row in rows if row.get("split") == "candidate_hold"]
    if len(admitted_rows) != 256 or len(positive_hold_rows) != 52 or len(negative_hold_rows) != 60:
        raise ValueError(f"source_projection_counts:{len(admitted_rows)}:{len(positive_hold_rows)}:{len(negative_hold_rows)}")
    trainer.assert_optimizer_rows_only(admitted_rows, expected_rows=256)

    legacy_256 = []
    for runner in LEGACY_RUNNERS:
        text = runner.read_text(encoding="utf-8")
        if "expected_rows=256" in text or "len(rows) != 256" in text:
            legacy_256.append(str(runner).replace("\\", "/"))
    if len(legacy_256) != len(LEGACY_RUNNERS):
        raise ValueError("legacy_runner_detection_incomplete")

    report = {
        "schema_version": "mouth_combined_candidate_v20_runner_compatibility_v1",
        "status": "TRAINER_ACCEPTS_256_BASE_52_POSITIVE_HOLD_ROWS_REQUIRE_ADMISSION_RUNNER_ADAPTER_REQUIRED",
        "candidate_rows": len(rows),
        "admitted_compatible_rows": len(admitted_rows),
        "positive_hold_rows": len(positive_hold_rows),
        "negative_hold_rows": len(negative_hold_rows),
        "candidate_sha256": sha256(TRAIN),
        "manifest_sha256": sha256(MANIFEST),
        "admission_audit_sha256": sha256(AUDIT),
        "production_row_validator": "accepted_expected_rows_256_existing_admission",
        "model_loaded": False,
        "cuda_touched": False,
        "lease_called": False,
        "optimizer_steps_executed": 0,
        "legacy_256_wrappers": legacy_256,
        "execution_authorized": False,
        "training_authorized": False,
        "promotion_allowed": False,
        "next_action": "admit_52_positive_hold_rows_only_after_separate_admission_then_construct_named_runner_for_308_optimizer_rows",
    }
    output = CAMPAIGN / "RUNNER_COMPATIBILITY_AUDIT_V2.json"
    if output.exists():
        raise FileExistsError(f"refuse_overwrite:{output}")
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
