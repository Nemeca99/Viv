#!/usr/bin/env python3
"""Audit v22 semantic packs as a hold-only admission boundary."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import FAIL, PASS, judge

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
POS_ROOT = TREE / "campaigns/mouth_semantic_refinement_v22_42"
NEG_ROOT = TREE / "campaigns/mouth_semantic_refinement_v22_adversarial"
POS = POS_ROOT / "semantic_refinement_96_hold.jsonl"
NEG = NEG_ROOT / "semantic_adversarial_48_judge_only.jsonl"
OUT = POS_ROOT / "ADMISSION_AUDIT_V1.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_overwrite:{OUT}")
    pos_manifest = json.loads((POS_ROOT / "manifest.json").read_text(encoding="utf-8"))
    neg_manifest = json.loads((NEG_ROOT / "manifest.json").read_text(encoding="utf-8"))
    positives = load(POS)
    negatives = load(NEG)
    findings: list[str] = []
    if sha(POS) != pos_manifest.get("jsonl_sha256"): findings.append("positive_hash_mismatch")
    if sha(NEG) != neg_manifest.get("jsonl_sha256"): findings.append("negative_hash_mismatch")
    pos_ids = {row.get("pair_id") for row in positives}; neg_ids = {row.get("pair_id") for row in negatives}
    pos_text = {row.get("target") for row in positives}; neg_text = {row.get("target") for row in negatives}
    if len(positives) != 96 or len(pos_ids) != 96 or len(pos_text) != 96: findings.append("positive_shape_or_duplicate")
    if len(negatives) != 48 or len(neg_ids) != 48 or len(neg_text) != 48: findings.append("negative_shape_or_duplicate")
    if pos_ids & neg_ids: findings.append("pair_id_overlap")
    if pos_text & neg_text: findings.append("target_text_overlap")
    if any(row.get("optimizer_eligible") is not False or row.get("hold_only") is not True for row in positives): findings.append("positive_authorization_projection")
    if any(row.get("optimizer_eligible") is not False or row.get("hold_only") is not True for row in negatives): findings.append("negative_authorization_projection")
    positive_replay = []
    for row in positives:
        result = judge(row["target"], axis=row["axis"], use_cpu_sensor=False)
        positive_replay.append(result.get("status") == PASS)
    negative_replay = []
    for row in negatives:
        result = judge(row["target"], axis=row["axis"], use_cpu_sensor=False)
        negative_replay.append(result.get("status") == FAIL)
    if not all(positive_replay): findings.append("positive_current_replay_failure")
    if not all(negative_replay): findings.append("negative_current_replay_failure")
    report = {
        "schema_version": "mouth_semantic_refinement_v22_admission_audit_v1",
        "status": "ADMISSION_AUDIT_PASS" if not findings else "ADMISSION_AUDIT_FAIL",
        "positive_pack": {"path": str(POS).replace("\\", "/"), "sha256": sha(POS), "rows": len(positives), "current_pass": sum(positive_replay), "current_total": len(positive_replay)},
        "negative_pack": {"path": str(NEG).replace("\\", "/"), "sha256": sha(NEG), "rows": len(negatives), "current_fail": sum(negative_replay), "current_total": len(negative_replay)},
        "pair_id_overlap": len(pos_ids & neg_ids),
        "target_text_overlap": len(pos_text & neg_text),
        "training_authorized": False,
        "run_authorized": False,
        "optimizer_eligible": False,
        "promotion_allowed": False,
        "findings": findings,
        "next_action": "separate_explicit_admission_authorization_required" if not findings else "repair_findings_before_admission",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
