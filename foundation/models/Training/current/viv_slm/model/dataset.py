"""Small, source-preserving causal character tensor dataset for Part 3."""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator, Sequence
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import torch

from tokenizer import CharacterTokenizer

SCHEMA_VERSION = "uml_part3_tensor_dataset_v1"
DEFAULT_CONTEXT_LENGTH = 128
DEFAULT_STRIDE = 1
DEFAULT_SHARD_EXAMPLES = 2048
STORAGE_DTYPE = torch.int16
MODEL_DTYPE = torch.long


class DatasetError(ValueError):
    """Fail-closed model dataset preparation error."""


def read_source(path: Path) -> tuple[str, dict[str, Any]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DatasetError(f"source_decode_error:{path}:{exc}") from None
    return text, {
        "path": str(path.resolve()).replace("\\", "/"),
        "bytes": len(raw),
        "characters": len(text),
        "sha256": sha256(raw).hexdigest(),
    }


def iter_windows(
    token_ids: Iterable[int],
    *,
    context_length: int,
    stride: int,
) -> Iterator[tuple[list[int], list[int]]]:
    if context_length <= 0:
        raise DatasetError("context_length_must_be_positive")
    if stride <= 0 or stride > context_length:
        raise DatasetError("stride_must_be_between_one_and_context_length")
    buffer: deque[int] = deque(maxlen=context_length + 1)
    for token_id in token_ids:
        if not isinstance(token_id, int) or isinstance(token_id, bool):
            raise DatasetError("token_stream_contains_non_integer")
        buffer.append(token_id)
        if len(buffer) < context_length + 1:
            continue
        window = list(buffer)
        yield window[:context_length], window[1:]
        for _ in range(stride):
            buffer.popleft()


def _write_shard(path: Path, inputs: Sequence[Sequence[int]], targets: Sequence[Sequence[int]]) -> None:
    torch.save(
        {
            "schema_version": SCHEMA_VERSION,
            "storage_dtype": str(STORAGE_DTYPE),
            "inputs": torch.tensor(inputs, dtype=STORAGE_DTYPE),
            "targets": torch.tensor(targets, dtype=STORAGE_DTYPE),
        },
        path,
    )


def _build_split(
    *,
    split: str,
    sources: Sequence[Path],
    output: Path,
    tokenizer: CharacterTokenizer,
    context_length: int,
    stride: int,
    shard_examples: int,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    pending_inputs: list[list[int]] = []
    pending_targets: list[list[int]] = []
    shards: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    examples = 0
    tokens_consumed = 0

    def flush() -> None:
        if not pending_inputs:
            return
        path = output / f"shard_{len(shards):05d}.pt"
        _write_shard(path, pending_inputs, pending_targets)
        shards.append(
            {
                "path": str(path.relative_to(output.parent)).replace("\\", "/"),
                "examples": len(pending_inputs),
                "context_length": context_length,
                "storage_dtype": str(STORAGE_DTYPE),
            }
        )
        pending_inputs.clear()
        pending_targets.clear()

    for source in sources:
        text, record = read_source(source)
        records.append(record)
        try:
            token_ids = tokenizer.encode(text)
        except ValueError as exc:
            raise DatasetError(f"unsupported_character:source={source}:{exc}") from None
        for inputs, targets in iter_windows(
            token_ids,
            context_length=context_length,
            stride=stride,
        ):
            pending_inputs.append(inputs)
            pending_targets.append(targets)
            examples += 1
            tokens_consumed += context_length + 1
            if len(pending_inputs) >= shard_examples:
                flush()
    flush()
    if not shards:
        raise DatasetError(f"split_contains_no_complete_windows:{split}")
    return {
        "source_files": records,
        "source_file_count": len(records),
        "examples": examples,
        "tokens_consumed_for_windows": tokens_consumed,
        "shards": shards,
    }


def build_tensor_dataset(
    *,
    train_sources: Sequence[Path],
    validation_sources: Sequence[Path],
    output_dir: Path | str,
    tokenizer: CharacterTokenizer,
    context_length: int = DEFAULT_CONTEXT_LENGTH,
    stride: int = DEFAULT_STRIDE,
    shard_examples: int = DEFAULT_SHARD_EXAMPLES,
) -> dict[str, Any]:
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise DatasetError(f"output_exists_refuse_overwrite:{output}")
    if shard_examples <= 0:
        raise DatasetError("shard_examples_must_be_positive")
    output.mkdir(parents=True, exist_ok=True)
    train = _build_split(
        split="train",
        sources=train_sources,
        output=output / "train",
        tokenizer=tokenizer,
        context_length=context_length,
        stride=stride,
        shard_examples=shard_examples,
    )
    validation = _build_split(
        split="validation",
        sources=validation_sources,
        output=output / "validation",
        tokenizer=tokenizer,
        context_length=context_length,
        stride=stride,
        shard_examples=shard_examples,
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "tokenizer": tokenizer.manifest(),
        "objective": {
            "kind": "causal_next_character",
            "context_length": context_length,
            "stride": stride,
            "input_ids": "tokens[start:start+context_length]",
            "target_ids": "tokens[start+1:start+context_length+1]",
            "next_character_losses_per_example": context_length,
        },
        "storage": {
            "dtype": str(STORAGE_DTYPE),
            "model_batch_dtype": str(MODEL_DTYPE),
            "shard_examples": shard_examples,
        },
        "splits": {"train": train, "validation": validation},
        "source_policy": "source_files_read_only_strict_utf8_no_character_replacement",
    }
    with (output / "MANIFEST.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return manifest


def tensor_shards(dataset_dir: Path | str, split: str) -> list[Path]:
    paths = sorted((Path(dataset_dir) / split).glob("shard_*.pt"))
    if not paths:
        raise DatasetError(f"no_tensor_shards:{split}")
    return paths


def load_tensor_shard(
    path: Path | str,
    *,
    vocab_size: int,
) -> tuple[torch.Tensor, torch.Tensor]:
    payload = torch.load(Path(path), map_location="cpu", weights_only=True)
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise DatasetError(f"tensor_shard_schema_mismatch:{path}")
    inputs = payload.get("inputs")
    targets = payload.get("targets")
    if not isinstance(inputs, torch.Tensor) or not isinstance(targets, torch.Tensor):
        raise DatasetError(f"tensor_shard_tensors_missing:{path}")
    if inputs.dtype != STORAGE_DTYPE or targets.dtype != STORAGE_DTYPE:
        raise DatasetError(f"tensor_shard_storage_dtype_mismatch:{path}")
    if inputs.ndim != 2 or targets.shape != inputs.shape:
        raise DatasetError(f"tensor_shard_shape_mismatch:{path}")
    if inputs.numel() and (
        int(inputs.min()) < 0
        or int(inputs.max()) >= vocab_size
        or int(targets.min()) < 0
        or int(targets.max()) >= vocab_size
    ):
        raise DatasetError(f"tensor_shard_token_range_mismatch:{path}")
    return inputs.to(dtype=MODEL_DTYPE), targets.to(dtype=MODEL_DTYPE)


def first_batch(
    dataset_dir: Path | str,
    *,
    vocab_size: int,
    batch_size: int,
) -> tuple[torch.Tensor, torch.Tensor]:
    if batch_size <= 0:
        raise DatasetError("batch_size_must_be_positive")
    inputs, targets = load_tensor_shard(
        tensor_shards(dataset_dir, "train")[0],
        vocab_size=vocab_size,
    )
    if inputs.shape[0] < batch_size:
        raise DatasetError("first_shard_smaller_than_requested_batch")
    return inputs[:batch_size].contiguous(), targets[:batch_size].contiguous()
