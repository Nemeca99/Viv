"""Verify the source-grounded Viv-SLM v10 corpus and its model inputs."""
from __future__ import annotations

import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v10"
INPUTS = VIV_ROOT / "models" / "viv_slm_identity_personality_v10" / "inputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_viv_slm_identity_personality_v10 import (  # noqa: E402
    CLAIM_SOURCES,
    RESERVED_ASCII,
    _assert_source_claims,
)


def test_source_claims_are_present() -> None:
    hashes = _assert_source_claims()
    assert len(hashes) == 4
    assert set(path for path, _ in CLAIM_SOURCES.values()) == set(Path(path) for path in hashes)


def test_dataset_contract() -> None:
    manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "viv_slm_identity_personality_dataset_v10"
    assert manifest["status"] == "COMPLETE_DATASET_TRAINING_CLOSED"
    assert manifest["row_counts"] == {"train": 176, "validation": 32, "frozen": 24, "adversarial": 24}
    assert manifest["row_total"] == 256
    assert manifest["vocab_size"] == 96
    assert manifest["world_knowledge_included"] is False
    assert manifest["telemetry_in_training_responses"] is False
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert manifest["live_model_changed"] is False

    prompts: set[str] = set()
    for split in ("train", "validation", "frozen", "adversarial"):
        rows = [
            json.loads(line)
            for line in (DATASET / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == manifest["row_counts"][split]
        for row in rows:
            assert row["split"] == split
            assert row["authority_owner"] == "cpu_foundation"
            assert row["model_role"] == "replaceable_renderer"
            assert row["response_only_target"] is True
            assert row["telemetry_allowed"] is False
            assert row["training_authorized"] is False
            assert row["run_authorized"] is False
            assert row["world_knowledge_included"] is False
            assert row["termination_marker"] in row["text"]
            assert not any(marker in row["response"].casefold() for marker in ("master s_n", "rid=", "wikipedia dump"))
            assert not (set(row["text"]) - set(RESERVED_ASCII))
            assert row["prompt"] not in prompts
            prompts.add(row["prompt"])
            for claim in row["canonical_claims"]:
                assert claim in CLAIM_SOURCES
    assert len(prompts) == 256


def test_training_inputs_contract() -> None:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_TRAINING_CLOSED"
    assert manifest["dataset_manifest"].endswith("viv_slm_identity_personality_v10/MANIFEST.json")
    assert manifest["vocab_size"] == 96
    assert manifest["context_length"] == 128
    assert manifest["stride"] == 1
    assert manifest["train_examples"] == 23450
    assert manifest["validation_examples"] == 4364
    assert manifest["world_knowledge_included"] is False
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert manifest["live_model_changed"] is False


def main() -> int:
    test_source_claims_are_present()
    test_dataset_contract()
    test_training_inputs_contract()
    print(
        {
            "ok": True,
            "dataset": "v10",
            "rows": 256,
            "train_examples": 23450,
            "validation_examples": 4364,
            "vocab_size": 96,
            "training_authorized": False,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
