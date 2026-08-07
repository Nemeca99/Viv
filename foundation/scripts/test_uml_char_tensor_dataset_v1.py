#!/usr/bin/env python3
"""Focused regression for UML causal windows, tensor shards, and batching."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

import torch

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.uml_char_dataset import (  # noqa: E402
    MODEL_DTYPE,
    STORAGE_DTYPE,
    UMLDatasetError,
    build_tensor_dataset,
    iter_tensor_batches,
    iter_windows,
    load_tensor_shard,
    tensor_shards,
)
from lib.uml_character_tokenizer import encode  # noqa: E402


def main() -> int:
    hello_ids = encode("hello")
    windows = list(iter_windows(hello_ids, context_length=4, stride=4))
    assert windows == [
        ([104, 101, 108, 108], [101, 108, 108, 111]),
    ]

    overlapping = list(iter_windows(encode("hello"), context_length=3, stride=1))
    assert overlapping == [
        ([104, 101, 108], [101, 108, 108]),
        ([101, 108, 108], [108, 108, 111]),
    ]

    with tempfile.TemporaryDirectory(prefix="uml_char_dataset_test_") as raw:
        root = Path(raw)
        train = root / "train"
        validation = root / "validation"
        output = root / "tensor_dataset"
        train.mkdir()
        validation.mkdir()
        (train / "one.txt").write_text("hello", encoding="utf-8", newline="")
        (train / "two.txt").write_text("world", encoding="utf-8", newline="")
        (validation / "one.txt").write_text("hello", encoding="utf-8", newline="")

        manifest = build_tensor_dataset(
            train_source=train,
            validation_source=validation,
            output_dir=output,
            context_length=4,
            stride=4,
            shard_examples=1,
        )
        assert manifest["status"] == "COMPLETE"
        assert manifest["objective"]["next_character_losses_per_example"] == 4
        assert manifest["splits"]["train"]["examples"] == 2
        assert manifest["splits"]["validation"]["examples"] == 1

        train_shards = tensor_shards(output, "train")
        assert len(train_shards) == 2
        inputs, targets = load_tensor_shard(train_shards[0])
        assert inputs.dtype == MODEL_DTYPE
        assert targets.dtype == MODEL_DTYPE
        assert inputs.shape == (1, 4)
        assert targets.shape == (1, 4)
        assert inputs.tolist() == [[104, 101, 108, 108]]
        assert targets.tolist() == [[101, 108, 108, 111]]

        batches = list(iter_tensor_batches(train_shards, batch_size=2, shuffle=False))
        assert len(batches) == 2
        batch_inputs, batch_targets = batches[0]
        assert batch_inputs.dtype == MODEL_DTYPE
        assert batch_targets.dtype == MODEL_DTYPE
        assert batch_inputs.shape == (1, 4)
        assert batch_targets.shape == (1, 4)

        payload = torch.load(train_shards[0], map_location="cpu", weights_only=True)
        assert payload["inputs"].dtype == STORAGE_DTYPE
        assert payload["targets"].dtype == STORAGE_DTYPE

        bad = root / "bad.txt"
        bad.write_bytes(b"hello\xff")
        bad_output = root / "bad_output"
        try:
            build_tensor_dataset(
                train_source=bad,
                validation_source=validation,
                output_dir=bad_output,
                context_length=4,
                stride=4,
                shard_examples=1,
            )
        except UMLDatasetError as exc:
            assert "source_decode_error" in str(exc)
        else:
            raise AssertionError("unsupported_dataset_character_accepted")
        assert bad.read_bytes() == b"hello\xff"

    print(
        "UML_CHAR_TENSOR_DATASET_PASS "
        "hello_shift=true "
        "context_window=true "
        "tensor_shards=true "
        "model_batches=true "
        "unsupported_characters_rejected=true "
        "sources_unchanged=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
