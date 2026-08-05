"""Verify the V18 surface-balance corpus and response-only inputs."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v18"
INPUTS = FOUNDATION.parent / "models" / "viv_slm_identity_personality_v18" / "inputs"


def _rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for split in ("train", "validation", "frozen", "adversarial"):
        rows.extend(json.loads(line) for line in (DATASET / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
    return rows


def test_v18_dataset() -> None:
    manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "viv_slm_identity_personality_dataset_v18"
    assert manifest["row_counts"] == {"train": 426, "validation": 64, "frozen": 32, "adversarial": 32}
    assert manifest["row_total"] == 554
    assert manifest["refinement_target"] == "surface_balance_for_speech_style_greeting_and_plain_language"
    assert manifest["additional_train_rows"] == 60
    assert manifest["parent_train_rows"] == 366
    assert manifest["targeted_row_counts"] == {"speech_style": 20, "greeting": 20, "plain_language": 20}
    assert manifest["vocab_size"] == 96
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    rows = _rows()
    assert len(rows) == 554
    assert len({row["prompt"] for row in rows}) == 554
    targeted = [row for row in rows if str(row["example_id"]).startswith("v18-")]
    assert len(targeted) == 60
    assert {row["split"] for row in targeted} == {"train"}
    assert {row["repair_family"] for row in targeted} == {"speech_style", "greeting", "plain_language"}
    assert all(prompt not in {row["prompt"] for row in rows} for prompt in manifest["holdout_probe_prompts"])
    assert all("master s_n" not in str(row["response"]).casefold() and "rid=" not in str(row["response"]).casefold() for row in rows)


def test_v18_response_only_inputs() -> None:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_TRAINING_CLOSED"
    assert manifest["dataset_manifest"].endswith("viv_slm_identity_personality_v18/MANIFEST.json")
    assert manifest["vocab_size"] == 96
    assert manifest["context_length"] == 128
    assert manifest["stride"] == 1
    assert manifest["response_only_loss"] is True
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert manifest["world_knowledge_included"] is False


def main() -> int:
    test_v18_dataset()
    test_v18_response_only_inputs()
    print({"ok": True, "dataset": "v18", "rows": 554, "targeted_train_rows": 60, "response_only_loss": True, "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
