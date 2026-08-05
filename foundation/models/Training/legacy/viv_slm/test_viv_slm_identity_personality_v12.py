"""Verify the V12 operator-mirroring refinement corpus."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v12"
INPUTS = FOUNDATION.parent / "models" / "viv_slm_identity_personality_v12" / "inputs"


def test_v12_dataset() -> None:
    manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "viv_slm_identity_personality_dataset_v12"
    assert manifest["row_counts"] == {"train": 288, "validation": 64, "frozen": 32, "adversarial": 32}
    assert manifest["row_total"] == 416
    assert manifest["refinement_target"] == "operator_mirror_direct_answer_and_identity_boundary"
    assert manifest["additional_train_rows"] == 24
    assert manifest["vocab_size"] == 96
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    rows = []
    for split in ("train", "validation", "frozen", "adversarial"):
        rows.extend(json.loads(line) for line in (DATASET / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
    assert len(rows) == 416
    assert len({row["prompt"] for row in rows}) == 416
    targeted = [row for row in rows if row["example_id"].startswith("v12-operator_mirror-train-")]
    assert len(targeted) == 24
    assert {row["split"] for row in targeted} == {"train"}
    assert all("identity" in row["response"].casefold() or "authority" in row["response"].casefold() or "tone" in row["response"].casefold() or "style" in row["response"].casefold() for row in targeted)
    assert all("master s_n" not in row["response"].casefold() and "rid=" not in row["response"].casefold() for row in rows)


def test_v12_inputs() -> None:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_TRAINING_CLOSED"
    assert manifest["dataset_manifest"].endswith("viv_slm_identity_personality_v12/MANIFEST.json")
    assert manifest["vocab_size"] == 96
    assert manifest["context_length"] == 128
    assert manifest["stride"] == 1
    assert manifest["train_examples"] == 38662
    assert manifest["validation_examples"] == 8673
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert manifest["world_knowledge_included"] is False


def main() -> int:
    test_v12_dataset()
    test_v12_inputs()
    print({"ok": True, "dataset": "v12", "rows": 416, "targeted_train_rows": 24, "train_examples": 38662, "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
