"""Verify the V14 generic speech-prefix refinement corpus."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v14"
INPUTS = FOUNDATION.parent / "models" / "viv_slm_identity_personality_v14" / "inputs"


def test_v14_dataset() -> None:
    manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "viv_slm_identity_personality_dataset_v14"
    assert manifest["row_counts"] == {"train": 324, "validation": 64, "frozen": 32, "adversarial": 32}
    assert manifest["row_total"] == 452
    assert manifest["refinement_target"] == "generic_how_do_you_speak_prefix_conditioning"
    assert manifest["targeted_concepts"] == ["personality_tone"]
    assert manifest["additional_train_rows"] == 12
    assert manifest["vocab_size"] == 96
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    rows = []
    for split in ("train", "validation", "frozen", "adversarial"):
        rows.extend(json.loads(line) for line in (DATASET / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
    assert len(rows) == 452
    assert len({row["prompt"] for row in rows}) == 452
    targeted = [row for row in rows if row["example_id"].startswith("v14-speech_prefix-train-")]
    assert len(targeted) == 12
    assert {row["split"] for row in targeted} == {"train"}
    assert {row["concept_id"] for row in targeted} == {"personality_tone"}
    assert all(row["prompt"].startswith("How do you speak") for row in targeted)
    assert all("master s_n" not in row["response"].casefold() and "rid=" not in row["response"].casefold() for row in rows)


def test_v14_inputs() -> None:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_TRAINING_CLOSED"
    assert manifest["dataset_manifest"].endswith("viv_slm_identity_personality_v14/MANIFEST.json")
    assert manifest["vocab_size"] == 96
    assert manifest["context_length"] == 128
    assert manifest["stride"] == 1
    assert manifest["train_examples"] > 41222
    assert manifest["validation_examples"] == 8673
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert manifest["world_knowledge_included"] is False


def main() -> int:
    test_v14_dataset()
    test_v14_inputs()
    print({"ok": True, "dataset": "v14", "rows": 452, "targeted_train_rows": 12, "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
