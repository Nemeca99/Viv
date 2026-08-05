"""Verify the V13 speech-style and missing-evidence refinement corpus."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v13"
INPUTS = FOUNDATION.parent / "models" / "viv_slm_identity_personality_v13" / "inputs"


def test_v13_dataset() -> None:
    manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "viv_slm_identity_personality_dataset_v13"
    assert manifest["row_counts"] == {"train": 312, "validation": 64, "frozen": 32, "adversarial": 32}
    assert manifest["row_total"] == 440
    assert manifest["refinement_target"] == "speech_style_and_missing_evidence_direct_answer"
    assert manifest["targeted_concepts"] == ["missing_evidence", "personality_tone"]
    assert manifest["additional_train_rows"] == 24
    assert manifest["vocab_size"] == 96
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    rows = []
    for split in ("train", "validation", "frozen", "adversarial"):
        rows.extend(json.loads(line) for line in (DATASET / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
    assert len(rows) == 440
    assert len({row["prompt"] for row in rows}) == 440
    targeted = [
        row
        for row in rows
        if row["example_id"].startswith(("v13-speech_style-train-", "v13-missing_evidence-train-"))
    ]
    assert len(targeted) == 24
    assert {row["split"] for row in targeted} == {"train"}
    assert {row["concept_id"] for row in targeted} == {"personality_tone", "missing_evidence"}
    assert all("master s_n" not in row["response"].casefold() and "rid=" not in row["response"].casefold() for row in rows)


def test_v13_inputs() -> None:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_TRAINING_CLOSED"
    assert manifest["dataset_manifest"].endswith("viv_slm_identity_personality_v13/MANIFEST.json")
    assert manifest["vocab_size"] == 96
    assert manifest["context_length"] == 128
    assert manifest["stride"] == 1
    assert manifest["train_examples"] > 38662
    assert manifest["validation_examples"] == 8673
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert manifest["world_knowledge_included"] is False


def main() -> int:
    test_v13_dataset()
    test_v13_inputs()
    print({"ok": True, "dataset": "v13", "rows": 440, "targeted_train_rows": 24, "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
