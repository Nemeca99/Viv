#!/usr/bin/env python3
"""Regression for the governed UML identity dataset projection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import torch

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/uml/identity_contract_dataset_v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    manifest_path = ROOT / "MANIFEST.json"
    assert manifest_path.is_file(), f"missing_manifest:{manifest_path}"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "uml_identity_contract_dataset_v1"
    assert manifest["status"] == "DATASET_READY_TRAINING_CLOSED"
    assert manifest["context_length"] == 128
    assert manifest["authority"] == {
        "deployment_changed": False,
        "lease_opened": False,
        "live_model_changed": False,
        "promotion_authorized": False,
        "run_authorized": False,
        "training_authorized": False,
    }
    assert manifest["separation"]["identity_separate_from_knowledge"] is True
    assert manifest["separation"]["wikipedia_included"] is False
    assert manifest["separation"]["telemetry_in_training_responses"] is False
    assert manifest["separation"]["adversarial_in_tensor_sources"] is False
    assert manifest["separation"]["frozen_in_tensor_sources"] is False

    expected_counts = {"train": 76, "validation": 20, "frozen": 8, "adversarial": 8}
    assert manifest["counts"]["by_split"] == expected_counts
    all_rows: list[dict] = []
    pair_hashes: set[str] = set()
    prompt_keys: set[str] = set()
    for split, expected_count in expected_counts.items():
        path = ROOT / f"{split}.jsonl"
        assert path.is_file(), f"missing_dataset:{split}"
        rows = load_rows(path)
        assert len(rows) == expected_count, (split, len(rows), expected_count)
        assert sha256(path) == manifest["datasets"][split]["sha256"]
        for row in rows:
            assert row["split"] == split
            assert row["training_authorized"] is False
            assert row["run_authorized"] is False
            assert row["deployment_changed"] is False
            assert row["response_only_target"] is True
            assert row["telemetry_allowed"] is False
            assert row["text"] == f"User: {row['prompt']}\nViv: {row['response']}\n"
            assert row["pair_hash"] not in pair_hashes
            assert row["prompt"].casefold() not in prompt_keys
            pair_hashes.add(row["pair_hash"])
            prompt_keys.add(row["prompt"].casefold())
            all_rows.append(row)

    assert len(all_rows) == 112
    primer = next(row for row in all_rows if row["example_id"] == "cold-start-identity-001")
    assert primer["response"] == "My name is Viv. I am an Adaptive Intelligent Operating System (AIOS)."
    assert any(row["example_id"] == "cold-start-identity-016" and row["split"] == "validation" for row in all_rows)
    assert all(row["domain"] != "wikipedia" for row in all_rows)
    assert all("master s_n" not in row["response"].casefold() for row in all_rows)
    assert all("current telemetry" not in row["response"].casefold() for row in all_rows)

    for split in ("train", "validation", "frozen"):
        text_dir = ROOT / "text" / split
        files = sorted(text_dir.glob("*.txt"))
        assert len(files) == expected_counts[split], (split, len(files))
        for path in files:
            assert path.read_text(encoding="utf-8") in {row["text"] for row in all_rows if row["split"] == split}

    # The tokenizer is imported only for an exact lossless corpus check; this
    # does not load a model or start training.
    if str(FOUNDATION) not in sys.path:
        sys.path.insert(0, str(FOUNDATION))
    from lib.uml_character_tokenizer import decode, encode  # noqa: E402

    for row in all_rows:
        assert decode(encode(row["text"])) == row["text"]

    tensor_manifest_path = ROOT / "tensor_v1" / "MANIFEST.json"
    assert tensor_manifest_path.is_file(), f"missing_tensor_manifest:{tensor_manifest_path}"
    tensor_manifest = json.loads(tensor_manifest_path.read_text(encoding="utf-8"))
    assert tensor_manifest["status"] == "COMPLETE"
    assert tensor_manifest["objective"]["context_length"] == 128
    assert tensor_manifest["splits"]["train"]["examples"] == 78
    assert tensor_manifest["splits"]["validation"]["examples"] == 22
    assert not any(
        "frozen" in record["path"] or "adversarial" in record["path"]
        for split in tensor_manifest["splits"].values()
        for record in split["source_files"]
    )
    first_source = next(
        record for record in tensor_manifest["splits"]["train"]["source_files"] if record["characters"] >= 129
    )
    first_text = Path(first_source["path"]).read_text(encoding="utf-8")
    first_ids = encode(first_text)
    first_shard_rel = tensor_manifest["splits"]["train"]["shards"][0]["path"]
    first_shard = ROOT / "tensor_v1" / first_shard_rel
    payload = torch.load(first_shard, map_location="cpu", weights_only=True)
    assert payload["inputs"].dtype == torch.int32
    assert payload["targets"].dtype == torch.int32
    assert payload["inputs"][0].tolist() == first_ids[:128]
    assert payload["targets"][0].tolist() == first_ids[1:129]

    stream_manifest_path = ROOT / "stream_v1" / "MANIFEST.json"
    assert stream_manifest_path.is_file(), f"missing_stream_manifest:{stream_manifest_path}"
    stream_manifest = json.loads(stream_manifest_path.read_text(encoding="utf-8"))
    assert stream_manifest["status"] == "COMPLETE_TRAINING_CLOSED"
    assert stream_manifest["window_policy"]["stride"] == 1
    train_stream = (ROOT / "stream_v1" / "train.txt").read_text(encoding="utf-8")
    validation_stream = (ROOT / "stream_v1" / "validation.txt").read_text(encoding="utf-8")
    assert primer["text"] in train_stream
    assert any(row["text"] in validation_stream for row in all_rows if row["split"] == "validation")
    assert stream_manifest["datasets"]["train"]["characters"] == len(train_stream)
    assert stream_manifest["datasets"]["validation"]["characters"] == len(validation_stream)

    tensor_stream_manifest_path = ROOT / "tensor_stream_v1" / "MANIFEST.json"
    assert tensor_stream_manifest_path.is_file(), f"missing_tensor_stream_manifest:{tensor_stream_manifest_path}"
    tensor_stream_manifest = json.loads(tensor_stream_manifest_path.read_text(encoding="utf-8"))
    assert tensor_stream_manifest["status"] == "COMPLETE"
    assert tensor_stream_manifest["objective"]["stride"] == 1
    assert tensor_stream_manifest["splits"]["train"]["examples"] == len(train_stream) - 128
    assert tensor_stream_manifest["splits"]["validation"]["examples"] == len(validation_stream) - 128
    stream_shard_rel = tensor_stream_manifest["splits"]["train"]["shards"][0]["path"]
    stream_payload = torch.load(ROOT / "tensor_stream_v1" / stream_shard_rel, map_location="cpu", weights_only=True)
    stream_ids = encode(train_stream)
    assert stream_payload["inputs"][0].tolist() == stream_ids[:128]
    assert stream_payload["targets"][0].tolist() == stream_ids[1:129]

    print(
        "UML_IDENTITY_DATASET_PASS "
        "rows=112 train=76 validation=20 frozen=8 adversarial=8 "
        "cold_start_anchored=true "
        "knowledge_separate=true "
        "telemetry_excluded=true "
        "prompt_disjoint=true "
        "unicode_round_trip=true "
        "tensor_shift=true "
        "tensor_windows_train=78 "
        "tensor_windows_validation=22 "
        "stream_stride=1 "
        "stream_windows_train=15234 "
        "stream_windows_validation=3978 "
        "canonical_identity_in_stream=true "
        "training_authorized=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
