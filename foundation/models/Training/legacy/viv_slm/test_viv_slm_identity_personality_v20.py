"""Verify the V20 protected-rehearsal corpus and response-only inputs."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v20"
INPUTS = FOUNDATION.parent / "models" / "viv_slm_identity_personality_v20" / "inputs"


def _rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for split in ("train", "validation", "frozen", "adversarial"):
        rows.extend(
            json.loads(line)
            for line in (DATASET / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return rows


def test_v20_dataset() -> None:
    manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "viv_slm_identity_personality_dataset_v20"
    assert manifest["row_counts"] == {"train": 382, "validation": 64, "frozen": 32, "adversarial": 32}
    assert manifest["row_total"] == 510
    assert manifest["refinement_target"] == "protect_identity_authority_and_evidence_with_small_surface_conditioning_probe"
    assert manifest["additional_train_rows"] == 16
    assert manifest["parent_train_rows"] == 366
    assert manifest["rehearsal_row_counts"] == {"identity": 4, "authority": 4, "evidence": 4, "surface": 4}
    assert manifest["v18_surface_rows_included"] is False
    assert manifest["vocab_size"] == 96
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    rows = _rows()
    assert len(rows) == 510
    assert len({row["prompt"] for row in rows}) == 510
    rehearsal = [row for row in rows if str(row["example_id"]).startswith("v20-rehearsal-")]
    assert len(rehearsal) == 16
    assert {row["split"] for row in rehearsal} == {"train"}
    assert {row["repair_family"] for row in rehearsal} == {"identity", "authority", "evidence", "surface"}
    assert not any(str(row["example_id"]).startswith("v18-") for row in rows)
    assert all(
        "master s_n" not in str(row["response"]).casefold()
        and "rid=" not in str(row["response"]).casefold()
        for row in rows
    )


def test_v20_response_only_inputs() -> None:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_TRAINING_CLOSED"
    assert manifest["dataset_manifest"].endswith("viv_slm_identity_personality_v20/MANIFEST.json")
    assert manifest["vocab_size"] == 96
    assert manifest["context_length"] == 128
    assert manifest["stride"] == 1
    assert manifest["train_examples"] > 46673
    assert manifest["validation_examples"] == 8672
    assert manifest["response_only_loss"] is True
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert manifest["world_knowledge_included"] is False


def main() -> int:
    test_v20_dataset()
    test_v20_response_only_inputs()
    print({"ok": True, "dataset": "v20", "rows": 510, "rehearsal_train_rows": 16, "response_only_loss": True, "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
