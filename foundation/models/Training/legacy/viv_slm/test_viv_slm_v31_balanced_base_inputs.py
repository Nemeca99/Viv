#!/usr/bin/env python3
"""Regression checks for the V31 balanced source-grounded input lane."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys
import tempfile

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for path in (FOUNDATION, FOUNDATION / "scripts", VIV_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from build_viv_slm_v31_balanced_base_inputs import (  # noqa: E402
    DATASET_ROOT,
    EXPECTED_CANONICAL_COUNTS,
    EXPECTED_PARENT_ROWS,
    build,
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="viv_slm_v31_balanced_base_") as temp_dir:
        output = Path(temp_dir) / "inputs"
        manifest = build(output_dir=output)
        assert manifest["schema_version"] == "viv_slm_v31_balanced_base_inputs_v1"
        assert manifest["train_examples"] == 53314
        assert manifest["validation_examples"] == 8672
        assert manifest["response_only_loss"] is True
        assert manifest["world_knowledge_included"] is False
        assert manifest["training_authorized"] is False
        assert manifest["run_authorized"] is False
        assert manifest["promotion_authorized"] is False
        assert manifest["deployment_changed"] is False
        assert manifest["live_model_changed"] is False
        balanced = manifest["balanced_corpus"]
        assert balanced["parent_rows"] == EXPECTED_PARENT_ROWS
        assert balanced["canonical_rows"] == sum(EXPECTED_CANONICAL_COUNTS.values())
        assert balanced["canonical_counts"] == EXPECTED_CANONICAL_COUNTS
        assert balanced["canonical_repeats"] == 1
        assert balanced["focus_repeats"] == 0
        assert balanced["validation_unchanged_from_v17"] is True

        input_manifest = json.loads((output / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
        tensor_manifest = json.loads((output / "tensor_dataset" / "MANIFEST.json").read_text(encoding="utf-8"))
        assert input_manifest["tensor_manifest_sha256"] == hashlib.sha256((output / "tensor_dataset" / "MANIFEST.json").read_bytes()).hexdigest()
        assert tensor_manifest["schema_version"] == "viv_slm_v31_balanced_base_tensor_dataset_v1"
        assert tensor_manifest["splits"]["train"]["rows"] == 430
        assert tensor_manifest["splits"]["validation"]["rows"] == 64
        assert tensor_manifest["splits"]["train"]["examples"] == 53314
        assert tensor_manifest["splits"]["validation"]["examples"] == 8672

        train_rows = [json.loads(line) for line in (DATASET_ROOT / "train.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(train_rows) == 430
        assert sum(not str(row["example_id"]).startswith("v24-") for row in train_rows) == 366
        assert sum(str(row["example_id"]).startswith("v24-") for row in train_rows) == 64

    print(
        "VIV_SLM_V31_BALANCED_BASE_INPUTS_PASS "
        "parent_rows=366 canonical_rows=64 canonical_repeats=1 focus_repeats=0 "
        "train_examples=53314 validation_examples=8672 response_only=true "
        "validation_unchanged=true telemetry=false world_knowledge=false "
        "training_authorized=false deployment_changed=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
