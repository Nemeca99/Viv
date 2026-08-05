#!/usr/bin/env python3
"""Regression tests for the V24 canonical speech-surface corpus."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for path in (FOUNDATION, VIV_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from build_viv_slm_identity_personality_v17 import _build_v17_rows, _source_bundle  # noqa: E402
from build_viv_slm_identity_personality_v24 import TARGET_ROWS, build  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="viv_slm_v24_regression_") as temp_dir:
        output = Path(temp_dir) / "dataset"
        manifest = build(output_dir=output)
        assert manifest["schema_version"] == "viv_slm_identity_personality_dataset_v24"
        assert manifest["row_counts"] == {"train": 430, "validation": 64, "frozen": 32, "adversarial": 32}
        assert manifest["canonical_surface_counts"] == {"capability": 8, "greeting": 12, "identity": 8, "plain_language": 12, "presence": 8, "speech_style": 16}
        assert manifest["vocab_size"] == 96
        assert manifest["world_knowledge_included"] is False
        assert manifest["telemetry_in_training_responses"] is False
        assert manifest["training_authorized"] is False
        assert manifest["run_authorized"] is False
        assert manifest["deployment_changed"] is False

        source_hash_records, source_hash = _source_bundle()
        assert manifest["source_bundle_sha256"] == source_hash
        assert len(source_hash_records) == 4

        parent_rows = _build_v17_rows(source_hash)
        parent_prompts = {str(row["prompt"]) for row in parent_rows}
        v24_train = [json.loads(line) for line in (output / "train.jsonl").read_text(encoding="utf-8").splitlines()]
        target_rows = [row for row in v24_train if str(row["example_id"]).startswith("v24-")]
        assert len(target_rows) == len(TARGET_ROWS)
        assert not parent_prompts.intersection(str(row["prompt"]) for row in target_rows)
        assert all(row["split"] == "train" and row["canonical_anchor"] is True for row in target_rows)
        assert all(row["world_knowledge_included"] is False for row in target_rows)
        assert all(row["telemetry_allowed"] is False for row in target_rows)
        assert all("Master S_n" not in row["response"] and "RID=" not in row["response"] for row in target_rows)

        v24_validation = (output / "validation.jsonl").read_text(encoding="utf-8")
        v17_validation = (VIV_ROOT / "foundation" / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v17" / "validation.jsonl").read_text(encoding="utf-8")
        assert v24_validation == v17_validation

    print(
        "VIV_SLM_V24_CANONICAL_SURFACE_DATASET_PASS "
        "train_rows=430 validation_rows=64 target_rows=64 vocab_size=96 "
        "parent_holdouts_unchanged=true telemetry=false world_knowledge=false "
        "training_authorized=false deployment_changed=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
