#!/usr/bin/env python3
"""Read-only admission checks for the v4 relationship repair micro."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_relationship_repair_micro_v4"
TRAIN = ROOT / "train_8.jsonl"
MANIFEST = ROOT / "MANIFEST.json"


def main() -> int:
    data = TRAIN.read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    if len(rows) != 8:
        raise AssertionError(f"row_count:{len(rows)}")
    axes = {axis: sum(row["axis"] == axis for row in rows) for axis in {row["axis"] for row in rows}}
    if axes != {"architecture_cpu_gpu_role": 4, "indirect_tool_agency": 4}:
        raise AssertionError(f"axis_counts:{axes}")
    if manifest["train_jsonl_sha256"] != hashlib.sha256(data).hexdigest():
        raise AssertionError("manifest_train_sha_mismatch")
    for row in rows:
        target = row["target"].lower()
        if any(token in target for token in ("aioskynet", "aiosketcher", "aiosc")):
            raise AssertionError(f"invented_identity:{row['candidate_id']}")
        if "cpu" not in target or "gpu" not in target:
            raise AssertionError(f"missing_role_boundary:{row['candidate_id']}")
        if row["optimizer_eligible"] is not True or row["hold_only"] is not False:
            raise AssertionError(f"eligibility_state:{row['candidate_id']}")
        if row["training_authorized"] is not False or row["run_authorized"] is not False:
            raise AssertionError(f"authorization_state:{row['candidate_id']}")
    print("PASS v4 corpus contract")
    print("ALL_PASS 8/8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
