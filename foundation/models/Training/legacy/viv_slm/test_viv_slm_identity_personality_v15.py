"""Verify the V15 direct-speech-anchor refinement corpus and inputs."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v15"
INPUTS = FOUNDATION.parent / "models" / "viv_slm_identity_personality_v15" / "inputs"


def _rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for split in ("train", "validation", "frozen", "adversarial"):
        rows.extend(
            json.loads(line)
            for line in (DATASET / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return rows


def test_v15_dataset() -> None:
    manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "viv_slm_identity_personality_dataset_v15"
    assert manifest["row_counts"] == {"train": 348, "validation": 64, "frozen": 32, "adversarial": 32}
    assert manifest["row_total"] == 476
    assert manifest["refinement_target"] == "ordinary_conversation_surface_with_unseen_style_and_greeting_holdouts"
    assert manifest["additional_train_rows"] == 24
    assert manifest["parent_train_rows"] == 324
    assert manifest["vocab_size"] == 96
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    rows = _rows()
    assert len(rows) == 476
    assert len({row["prompt"] for row in rows}) == 476
    targeted = [row for row in rows if str(row["example_id"]).startswith("v15-interaction-train-")]
    assert len(targeted) == 24
    assert {row["split"] for row in targeted} == {"train"}
    assert {row["concept_id"] for row in targeted} == {"personality_tone"}
    assert "Hello, Viv." in {row["prompt"] for row in targeted}
    assert all(prompt not in {row["prompt"] for row in rows} for prompt in manifest["holdout_probe_prompts"])
    assert all(
        "master s_n" not in str(row["response"]).casefold()
        and "rid=" not in str(row["response"]).casefold()
        for row in rows
    )


def test_v15_inputs() -> None:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_TRAINING_CLOSED"
    assert manifest["dataset_manifest"].endswith("viv_slm_identity_personality_v15/MANIFEST.json")
    assert manifest["vocab_size"] == 96
    assert manifest["context_length"] == 128
    assert manifest["stride"] == 1
    assert manifest["train_examples"] > 42630
    assert manifest["validation_examples"] == 8673
    assert manifest.get("response_only_loss", False) is False
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert manifest["world_knowledge_included"] is False


def main() -> int:
    test_v15_dataset()
    test_v15_inputs()
    print({"ok": True, "dataset": "v15", "rows": 476, "targeted_train_rows": 24, "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
