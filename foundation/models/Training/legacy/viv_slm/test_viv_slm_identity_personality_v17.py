"""Verify the V17 targeted speech and evidence repair corpus."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v17"
INPUTS = FOUNDATION.parent / "models" / "viv_slm_identity_personality_v17" / "inputs"


def _rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for split in ("train", "validation", "frozen", "adversarial"):
        rows.extend(
            json.loads(line)
            for line in (DATASET / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return rows


def test_v17_dataset() -> None:
    manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "viv_slm_identity_personality_dataset_v17"
    assert manifest["row_counts"] == {"train": 366, "validation": 64, "frozen": 32, "adversarial": 32}
    assert manifest["row_total"] == 494
    assert manifest["refinement_target"] == "speech_style_greeting_and_missing_evidence_boundary_retention"
    assert manifest["additional_train_rows"] == 18
    assert manifest["parent_train_rows"] == 348
    assert manifest["targeted_row_counts"] == {"personality_tone": 12, "missing_evidence": 6}
    assert manifest["vocab_size"] == 96
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    rows = _rows()
    assert len(rows) == 494
    assert len({row["prompt"] for row in rows}) == 494
    targeted = [row for row in rows if str(row["example_id"]).startswith("v17-targeted-train-")]
    assert len(targeted) == 18
    assert {row["split"] for row in targeted} == {"train"}
    assert {row["concept_id"] for row in targeted} == {"personality_tone", "missing_evidence"}
    assert all(prompt not in {row["prompt"] for row in rows} for prompt in manifest["holdout_probe_prompts"])
    assert all(
        "master s_n" not in str(row["response"]).casefold()
        and "rid=" not in str(row["response"]).casefold()
        for row in rows
    )


def test_v17_response_only_inputs() -> None:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_TRAINING_CLOSED"
    assert manifest["dataset_manifest"].endswith("viv_slm_identity_personality_v17/MANIFEST.json")
    assert manifest["vocab_size"] == 96
    assert manifest["context_length"] == 128
    assert manifest["stride"] == 1
    assert manifest["train_examples"] == 46673
    assert manifest["validation_examples"] == 8672
    assert manifest["response_only_loss"] is True
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert manifest["world_knowledge_included"] is False


def main() -> int:
    test_v17_dataset()
    test_v17_response_only_inputs()
    print({"ok": True, "dataset": "v17", "rows": 494, "targeted_train_rows": 18, "response_only_loss": True, "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
