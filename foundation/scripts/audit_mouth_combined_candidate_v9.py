"""Read-only admission audit for the combined 308-row mouth candidate."""
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
CAMPAIGN = ROOT / "campaigns/mouth_combined_candidate_v9"
CANDIDATE = CAMPAIGN / "train_308_candidate_hold.jsonl"
ENTITY = ROOT / "campaigns/mouth_entity_we_candidate_v7/train_272_candidate_hold.jsonl"
GOVERNANCE = ROOT / "campaigns/mouth_governance_candidate_v8/positive_36_candidate_hold.jsonl"
REPORT = CAMPAIGN / "ADMISSION_AUDIT_V3.json"

from lib.evaluator_v2_3_hybrid_v1_2_5 import judge


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if REPORT.exists():
        raise FileExistsError("refuse_overwrite:mouth_combined_candidate_v9_admission_audit")
    manifest = json.loads((CAMPAIGN / "MANIFEST.json").read_text(encoding="utf-8"))
    candidate = load(CANDIDATE)
    entity = load(ENTITY)
    governance = load(GOVERNANCE)
    errors: list[str] = []

    if digest(ENTITY) != manifest["entity_source_sha256"]:
        errors.append("entity_source_hash_mismatch")
    if digest(GOVERNANCE) != manifest["governance_source_sha256"]:
        errors.append("governance_source_hash_mismatch")
    if len(candidate) != 308 or candidate[:272] != entity or candidate[272:] != governance:
        errors.append("candidate_source_projection_mismatch")
    if digest(CANDIDATE) != manifest["candidate_sha256"]:
        errors.append("candidate_hash_mismatch")

    calibration = load(ROOT / "campaigns/mouth_semantics_calibration_v5/calibration_96.jsonl")
    blind = load(ROOT / "campaigns/mouth_semantics_blind_v4/blind_48.jsonl")
    new_asks = {row["ask_hash"] for row in governance}
    new_targets = {row["target_hash"] for row in governance}
    for name, rows in (("entity_candidate", entity), ("calibration", calibration), ("blind", blind)):
        if new_asks & {row.get("ask_hash") for row in rows}:
            errors.append(f"governance_ask_overlap:{name}")
        if new_targets & {row.get("target_hash") for row in rows}:
            errors.append(f"governance_target_overlap:{name}")

    statuses = [judge(row["target"], axis=row["axis"])["status"] for row in candidate]
    if any(status != "PASS" for status in statuses):
        errors.append("target_semantic_pass_failure")
    if any(row.get("optimizer_eligible") is not False for row in governance):
        errors.append("new_row_optimizer_open")
    if any(row.get("training_authorized") is not False or row.get("run_authorized") is not False for row in governance):
        errors.append("new_row_authorization_open")

    report = {
        "schema_version": "mouth_combined_candidate_admission_audit_v3",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ADMISSION_AUDIT_PASS" if not errors else "ADMISSION_AUDIT_FAIL",
        "candidate_rows": len(candidate),
        "parent_rows": len(entity),
        "new_governance_rows": len(governance),
        "axis_counts": dict(sorted(Counter(row["axis"] for row in candidate).items())),
        "target_pass_rows": sum(status == "PASS" for status in statuses),
        "target_nonpass_rows": sum(status != "PASS" for status in statuses),
        "errors": errors,
        "new_rows_hold_only": True,
        "admission_allowed": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: report[key] for key in ("status", "candidate_rows", "target_pass_rows", "target_nonpass_rows", "errors", "admission_allowed", "training_authorized")}, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
