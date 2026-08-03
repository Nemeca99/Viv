"""Read-only admission audit for the final 368-row candidate."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
CAMPAIGN = ROOT / "campaigns/mouth_combined_candidate_v20"
PARENT = ROOT / "campaigns/mouth_combined_candidate_v18/train_332_candidate_hold.jsonl"
EXPANSION = ROOT / "campaigns/mouth_governance_semantics_expansion_v12/positive_36_hold.jsonl"
NEG_GOV = ROOT / "campaigns/mouth_governance_semantics_expansion_v12/negative_36_judge_only.jsonl"
NEG_ENTITY = ROOT / "campaigns/mouth_entity_we_expansion_v6/negative_24_judge_only.jsonl"
CAL = ROOT / "campaigns/mouth_semantics_calibration_v5/calibration_96.jsonl"
BLIND = ROOT / "campaigns/mouth_semantics_blind_v4/blind_48.jsonl"
CANDIDATE = CAMPAIGN / "train_368_candidate_hold.jsonl"
MANIFEST = CAMPAIGN / "MANIFEST.json"
REPORT = CAMPAIGN / "ADMISSION_AUDIT.json"

from lib.evaluator_v2_3_hybrid_v1_2_5 import judge


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if REPORT.exists():
        raise FileExistsError("refuse_overwrite:mouth_combined_candidate_v20_admission_audit")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    parent = load(PARENT)
    added = load(EXPANSION)
    candidate = load(CANDIDATE)
    negatives = load(NEG_GOV) + load(NEG_ENTITY)
    calibration = load(CAL)
    blind = load(BLIND)
    errors: list[str] = []

    if sha(PARENT) != manifest["parent_sha256"]:
        errors.append("parent_hash_mismatch")
    if sha(EXPANSION) != manifest["expansion_sha256"]:
        errors.append("expansion_hash_mismatch")
    if sha(CANDIDATE) != manifest["candidate_sha256"]:
        errors.append("candidate_hash_mismatch")
    if len(parent) != 332 or len(added) != 36 or len(candidate) != 368:
        errors.append("projection_row_count")
    if candidate[:332] != parent or candidate[332:] != added:
        errors.append("projection_bytes_mismatch")
    if len({row["ask_hash"] for row in candidate}) != 368 or len({row["target_hash"] for row in candidate}) != 368:
        errors.append("candidate_duplicate_hashes")

    target_statuses = [judge(row["target"], axis=row["axis"])["status"] for row in candidate]
    if any(status != "PASS" for status in target_statuses):
        errors.append("candidate_target_nonpass")
    negative_statuses = [judge(row["target"], axis=row["axis"])["status"] for row in negatives]
    if any(status != "FAIL" for status in negative_statuses):
        errors.append("judge_only_negative_nonfail")
    added_asks = {row["ask_hash"] for row in added}
    added_targets = {row["target_hash"] for row in added}
    for name, rows in (("calibration", calibration), ("blind", blind), ("judge_only_negatives", negatives)):
        if added_asks & {row.get("ask_hash") for row in rows}:
            errors.append(f"added_ask_overlap:{name}")
        if added_targets & {row.get("target_hash") for row in rows}:
            errors.append(f"added_target_overlap:{name}")
    if any(row.get("optimizer_eligible") is not False or row.get("training_authorized") is not False or row.get("run_authorized") is not False for row in added):
        errors.append("added_authorization_open")

    report = {
        "schema_version": "mouth_combined_candidate_admission_audit_v20",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ADMISSION_AUDIT_PASS" if not errors else "ADMISSION_AUDIT_FAIL",
        "candidate_rows": len(candidate),
        "candidate_target_pass": sum(status == "PASS" for status in target_statuses),
        "judge_only_negative_rows": len(negatives),
        "judge_only_negative_fail": sum(status == "FAIL" for status in negative_statuses),
        "axis_counts": dict(sorted(Counter(row["axis"] for row in candidate).items())),
        "errors": errors,
        "admission_allowed": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: report[key] for key in ("status", "candidate_rows", "candidate_target_pass", "judge_only_negative_rows", "judge_only_negative_fail", "errors", "admission_allowed", "training_authorized")}, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
