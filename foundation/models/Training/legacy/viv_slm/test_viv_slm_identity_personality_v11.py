"""Verify the balanced V11 corpus and input package."""
from __future__ import annotations

import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v11"
INPUTS = VIV_ROOT / "models" / "viv_slm_identity_personality_v11" / "inputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_viv_slm_identity_personality_v11 import (  # noqa: E402
    CLAIM_SOURCES,
    CONCEPTS,
    RESERVED_ASCII,
    _assert_source_claims,
)


def test_source_claims() -> None:
    hashes = _assert_source_claims()
    assert len(hashes) == 4
    assert set(Path(path) for path in hashes) == set(path for path, _ in CLAIM_SOURCES.values())


def test_balanced_dataset() -> None:
    manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "viv_slm_identity_personality_dataset_v11"
    assert manifest["row_counts"] == {"train": 264, "validation": 64, "frozen": 32, "adversarial": 32}
    assert manifest["row_total"] == 392
    assert manifest["every_concept_in_train"] is True
    assert manifest["vocab_size"] == 96
    assert manifest["world_knowledge_included"] is False
    assert manifest["telemetry_in_training_responses"] is False
    rows = []
    for split in ("train", "validation", "frozen", "adversarial"):
        rows.extend(json.loads(line) for line in (DATASET / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
    assert len(rows) == 392
    assert len({row["prompt"] for row in rows}) == 392
    assert {claim for row in rows if row["split"] == "train" for claim in row["canonical_claims"]} >= {concept["claims"][0] for concept in CONCEPTS}
    for row in rows:
        assert row["termination_marker"] in row["text"]
        assert row["authority_owner"] == "cpu_foundation"
        assert row["model_role"] == "replaceable_renderer"
        assert row["training_authorized"] is False
        assert row["run_authorized"] is False
        assert row["world_knowledge_included"] is False
        assert row["telemetry_allowed"] is False
        assert not (set(row["text"]) - set(RESERVED_ASCII))
        assert not any(marker in row["response"].casefold() for marker in ("master s_n", "rid="))


def test_inputs() -> None:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_TRAINING_CLOSED"
    assert manifest["dataset_manifest"].endswith("viv_slm_identity_personality_v11/MANIFEST.json")
    assert manifest["vocab_size"] == 96
    assert manifest["context_length"] == 128
    assert manifest["stride"] == 1
    assert manifest["train_examples"] > 264 * 10
    assert manifest["validation_examples"] > 64 * 10
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert manifest["world_knowledge_included"] is False


def main() -> int:
    test_source_claims()
    test_balanced_dataset()
    test_inputs()
    print({"ok": True, "dataset": "v11", "rows": 392, "every_concept_in_train": True, "vocab_size": 96, "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
