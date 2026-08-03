#!/usr/bin/env python3
"""Construct a byte-preserving 308-positive selection; never authorizes training."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
SOURCE_ROOT = TREE / "campaigns/mouth_combined_candidate_v20"
ROOT = TREE / "campaigns/mouth_combined_candidate_v21_positive_308_selection"
SOURCE = SOURCE_ROOT / "train_368_candidate_hold.jsonl"
OUTPUT = ROOT / "positive_308_selection_hold.jsonl"
MANIFEST = ROOT / "manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_overwrite:{ROOT}")
    source_lines = SOURCE.read_text(encoding="utf-8").splitlines(keepends=True)
    selected: list[str] = []
    rows: list[dict] = []
    for line in source_lines:
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("split") in {"train", "train_candidate_hold"}:
            selected.append(line if line.endswith("\n") else line + "\n")
            rows.append(row)
    if len(rows) != 308:
        raise ValueError(f"positive_selection_rows:{len(rows)}")
    if sum(row.get("split") == "train" for row in rows) != 256:
        raise ValueError("base_train_selection_drift")
    if sum(row.get("split") == "train_candidate_hold" for row in rows) != 52:
        raise ValueError("held_positive_selection_drift")
    if len({row["pair_id"] for row in rows}) != 308:
        raise ValueError("selection_pair_ids_not_unique")
    if any(row.get("axis") == "candidate_hold" for row in rows):
        raise ValueError("negative_row_selected")

    ROOT.mkdir(parents=True, exist_ok=False)
    OUTPUT.write_text("".join(selected), encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": "mouth_v20_positive_308_selection_manifest_v1",
        "status": "POSITIVE_SELECTION_HOLD_ADMISSION_CLOSED",
        "source_campaign": str(SOURCE_ROOT).replace("\\", "/"),
        "source_jsonl_sha256": sha256(SOURCE),
        "selection_jsonl_sha256": sha256(OUTPUT),
        "source_rows": 368,
        "selected_positive_rows": 308,
        "existing_train_rows": 256,
        "held_positive_rows": 52,
        "judge_only_negative_rows_excluded": 60,
        "axis_counts": dict(sorted(Counter(row["axis"] for row in rows).items())),
        "byte_preserving_selection": True,
        "admission_allowed": False,
        "optimizer_eligible": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
        "next_action": "separate_admission_projection_then_named_308_runner",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
