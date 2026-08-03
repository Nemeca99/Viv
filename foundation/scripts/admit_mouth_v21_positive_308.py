#!/usr/bin/env python3
"""Admit the verified 308-positive selection into a new train projection.

This preserves the hold-only selection and creates a separate, hash-locked
projection. It does not authorize or execute training.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
SOURCE_ROOT = TREE / "campaigns/mouth_combined_candidate_v21_positive_308_selection"
ROOT = TREE / "campaigns/mouth_combined_candidate_v21_positive_308_admitted"
SOURCE = SOURCE_ROOT / "positive_308_selection_hold.jsonl"
SOURCE_MANIFEST = SOURCE_ROOT / "manifest.json"
QUALITY = TREE / "campaigns/mouth_combined_candidate_v20" / "POSITIVE_HOLD_QUALITY_AUDIT.json"
OUTPUT = ROOT / "positive_308_train_projection.jsonl"
MANIFEST = ROOT / "manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_overwrite:{ROOT}")
    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    if source_manifest.get("selection_jsonl_sha256") != sha256(SOURCE):
        raise ValueError("selection_hash_mismatch")
    if source_manifest.get("selected_positive_rows") != 308:
        raise ValueError("selection_count_mismatch")
    if source_manifest.get("admission_allowed") is not False:
        raise ValueError("source_must_remain_hold_only")
    quality = json.loads(QUALITY.read_text(encoding="utf-8"))
    if quality.get("status") != "QUALITY_PASS":
        raise ValueError("positive_quality_not_pass")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 308 or len({row.get("pair_id") for row in rows}) != 308:
        raise ValueError("admission_rows_or_ids_invalid")
    if any(row.get("axis") == "candidate_hold" for row in rows):
        raise ValueError("negative_row_in_admission")
    projected = []
    for row in rows:
        item = dict(row)
        item.update({
            "split": "train",
            "optimizer_eligible": True,
            "full_campaign_eligible": True,
            "hold_only": False,
            "admission_status": "ADMITTED_TRAINING_CLOSED",
            "training_authorized": False,
            "run_authorized": False,
        })
        projected.append(item)
    ROOT.mkdir(parents=True, exist_ok=False)
    OUTPUT.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in projected), encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": "mouth_v21_positive_308_admission_manifest_v1",
        "status": "ADMITTED_TRAINING_CLOSED",
        "source_selection": str(SOURCE).replace("\\", "/"),
        "source_selection_sha256": sha256(SOURCE),
        "source_selection_manifest_sha256": sha256(SOURCE_MANIFEST),
        "quality_audit": str(QUALITY).replace("\\", "/"),
        "quality_audit_sha256": sha256(QUALITY),
        "optimizer_jsonl": str(OUTPUT).replace("\\", "/"),
        "optimizer_jsonl_sha256": sha256(OUTPUT),
        "optimizer_rows": 308,
        "axis_counts": dict(sorted(Counter(row["axis"] for row in projected).items())),
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
        "deployment_authorized": False,
        "negative_rows_admitted": 0,
        "source_bytes_preserved": True,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
