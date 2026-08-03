"""Read-only admission audit for the 272-row entity-we candidate."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
CANDIDATE = ROOT / "campaigns/mouth_entity_we_candidate_v5/train_272_candidate_hold.jsonl"
MANIFEST = ROOT / "campaigns/mouth_entity_we_candidate_v5/MANIFEST.json"
PARENT = ROOT / "campaigns/mouth_full_run_entity_we_v2/train_256.jsonl"
NEGATIVE = ROOT / "campaigns/mouth_entity_we_expansion_v5/negative_16_judge_only.jsonl"
CALIBRATION = ROOT / "campaigns/mouth_semantics_calibration_v5/calibration_96.jsonl"
BLIND = ROOT / "campaigns/mouth_semantics_blind_v4/blind_48.jsonl"
OUT = ROOT / "campaigns/mouth_entity_we_candidate_v5/ADMISSION_AUDIT.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_overwrite:{OUT}")
    candidate = load(CANDIDATE)
    parent = load(PARENT)
    negative = load(NEGATIVE)
    calibration = load(CALIBRATION)
    blind = load(BLIND)
    errors: list[dict[str, str]] = []
    if len(candidate) != 272 or len(parent) != 256:
        errors.append({"kind": "row_count", "detail": f"candidate={len(candidate)} parent={len(parent)}"})
    if candidate[:256] != parent:
        errors.append({"kind": "parent_rows_changed", "detail": "candidate first 256 parsed rows differ from parent"})
    added = candidate[256:]
    if len(added) != 16 or any(row.get("axis") != "entity_we_boundary" for row in added):
        errors.append({"kind": "added_axis", "detail": "added rows are not exactly 16 entity_we_boundary rows"})
    for row in added:
        if row.get("optimizer_eligible") is not False or row.get("training_authorized") is not False or row.get("run_authorized") is not False:
            errors.append({"kind": "authorization", "detail": str(row.get("case_id"))})
        if judge(row.get("target", ""), axis="entity_we_boundary")["status"] != "PASS":
            errors.append({"kind": "semantic_target", "detail": str(row.get("case_id"))})
    candidate_asks = {row.get("ask_hash") for row in candidate}
    candidate_targets = {row.get("target_hash") for row in candidate}
    for name, rows in (("negative", negative), ("calibration", calibration), ("blind", blind)):
        if candidate_asks & {row.get("ask_hash") for row in rows}:
            errors.append({"kind": f"{name}_ask_overlap", "detail": "overlap detected"})
        if candidate_targets & {row.get("target_hash") for row in rows}:
            errors.append({"kind": f"{name}_target_overlap", "detail": "overlap detected"})
    report = {
        "schema_version": "mouth_entity_we_candidate_admission_audit_v5",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ADMISSION_AUDIT_PASS_TRAINING_CLOSED" if not errors else "ADMISSION_AUDIT_FAIL",
        "candidate_path": str(CANDIDATE).replace("\\", "/"),
        "candidate_sha256": sha(CANDIDATE),
        "manifest_sha256": sha(MANIFEST),
        "parent_sha256": sha(PARENT),
        "candidate_rows": len(candidate),
        "parent_rows": len(parent),
        "added_rows": len(added),
        "negative_rows_checked": len(negative),
        "calibration_rows_checked": len(calibration),
        "blind_rows_checked": len(blind),
        "errors": errors,
        "admission_allowed": False,
        "optimizer_eligible": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
        "next_action": "Require separate explicit corpus-admission authorization; training remains closed.",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("status", "candidate_rows", "parent_rows", "added_rows", "errors", "admission_allowed", "training_authorized", "run_authorized")}, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
