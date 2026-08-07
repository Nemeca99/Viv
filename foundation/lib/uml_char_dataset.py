"""Streaming PyTorch examples for the CPU UML character tokenizer.

The dataset contract is the standard causal next-character objective:

``input_ids = tokens[start : start + context_length]``
``target_ids = tokens[start + 1 : start + context_length + 1]``

The builder processes source files incrementally, never edits the sources, and
refuses invalid input instead of dropping or replacing it. Tensor shards are
stored as ``torch.int32`` because the complete Unicode scalar vocabulary has
1,112,064 IDs; batches are converted to ``torch.long`` before model use.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
import codecs
import json
from pathlib import Path
from typing import Any

import torch

from lib.uml_character_tokenizer import (
    TOKEN_ID_MAX,
    TOKEN_ID_MIN,
    TOKEN_UNIT,
    VOCAB_MODE,
    VOCAB_SHA256,
    VOCAB_SIZE,
    character_to_token_id,
)

DEFAULT_CONTEXT_LENGTH = 128
DEFAULT_STRIDE = 128
DEFAULT_SHARD_EXAMPLES = 4096
DEFAULT_CHUNK_BYTES = 1024 * 1024
STORAGE_DTYPE = torch.int32
MODEL_DTYPE = torch.long
SCHEMA_VERSION = "uml_char_tensor_dataset_v1"


class UMLDatasetError(ValueError):
    """Fail-closed dataset preparation error."""


@dataclass
class SourceStats:
    """Read-only provenance collected while one source file is encoded."""

    path: Path
    bytes_read: int = 0
    characters: int = 0
    digest: Any = field(default_factory=sha256, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path.resolve()).replace("\\", "/"),
            "bytes": self.bytes_read,
            "characters": self.characters,
            "sha256": self.digest.hexdigest(),
        }


def source_files(source: Path | str, *, pattern: str = "*.txt") -> list[Path]:
    """Resolve one explicit source file or a deterministic recursive file set."""
    path = Path(source)
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise UMLDatasetError(f"source_not_found:{path}")
    files = sorted(
        candidate
        for candidate in path.rglob(pattern)
        if candidate.is_file() and not candidate.is_symlink()
    )
    if not files:
        raise UMLDatasetError(f"source_contains_no_matching_files:{path}:{pattern}")
    return files


def _iter_decoded_chunks(
    path: Path,
    stats: SourceStats,
    *,
    encoding: str,
    chunk_bytes: int,
) -> Iterator[str]:
    if chunk_bytes <= 0:
        raise UMLDatasetError("chunk_bytes_must_be_positive")
    try:
        decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
    except LookupError as exc:
        raise UMLDatasetError(f"unknown_source_encoding:{encoding}") from exc

    with path.open("rb") as handle:
        while True:
            raw = handle.read(chunk_bytes)
            if not raw:
                break
            stats.bytes_read += len(raw)
            stats.digest.update(raw)
            try:
                decoded = decoder.decode(raw, final=False)
            except UnicodeDecodeError as exc:
                raise UMLDatasetError(
                    f"source_decode_error:source={path}:byte_offset={stats.bytes_read - len(raw)}:{exc}"
                ) from None
            if decoded:
                yield decoded
        try:
            tail = decoder.decode(b"", final=True)
        except UnicodeDecodeError as exc:
            raise UMLDatasetError(f"source_decode_error:source={path}:{exc}") from None
        if tail:
            yield tail


def iter_encoded_file(
    path: Path | str,
    *,
    encoding: str = "utf-8",
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    stats: SourceStats | None = None,
) -> Iterator[int]:
    """Yield one UML token ID per source character without buffering the file."""
    source = Path(path)
    read_stats = stats if stats is not None else SourceStats(source)
    for chunk in _iter_decoded_chunks(
        source,
        read_stats,
        encoding=encoding,
        chunk_bytes=chunk_bytes,
    ):
        for character in chunk:
            position = read_stats.characters
            try:
                token_id = character_to_token_id(character)
            except ValueError as exc:
                raise UMLDatasetError(
                    f"unsupported_character:source={source.resolve()}"
                    f":character_offset={position}:{exc}"
                ) from None
            read_stats.characters += 1
            yield token_id


def iter_windows(
    token_ids: Iterable[int],
    *,
    context_length: int = DEFAULT_CONTEXT_LENGTH,
    stride: int = DEFAULT_STRIDE,
) -> Iterator[tuple[list[int], list[int]]]:
    """Yield causal input/target windows from a token stream.

    ``stride=1`` gives every overlapping training example.  The default
    ``stride=context_length`` produces non-overlapping windows, which keeps a
    large corpus bounded while retaining all next-character positions inside
    each window.
    """
    if context_length <= 0:
        raise UMLDatasetError("context_length_must_be_positive")
    if stride <= 0 or stride > context_length:
        raise UMLDatasetError("stride_must_be_between_one_and_context_length")

    buffer: deque[int] = deque(maxlen=context_length + 1)
    for token_id in token_ids:
        if not isinstance(token_id, int) or isinstance(token_id, bool):
            raise UMLDatasetError("token_stream_contains_non_integer")
        if not TOKEN_ID_MIN <= token_id <= TOKEN_ID_MAX:
            raise UMLDatasetError(f"token_stream_id_out_of_range:{token_id}")
        buffer.append(token_id)
        if len(buffer) < context_length + 1:
            continue
        window = list(buffer)
        yield window[:context_length], window[1:]
        for _ in range(stride):
            buffer.popleft()


def iter_file_windows(
    path: Path | str,
    *,
    context_length: int,
    stride: int,
    encoding: str,
    chunk_bytes: int,
    stats: SourceStats,
) -> Iterator[tuple[list[int], list[int]]]:
    """Yield windows from one file without creating windows across file boundaries."""
    yield from iter_windows(
        iter_encoded_file(
            path,
            encoding=encoding,
            chunk_bytes=chunk_bytes,
            stats=stats,
        ),
        context_length=context_length,
        stride=stride,
    )


def _write_shard(
    path: Path,
    inputs: Sequence[Sequence[int]],
    targets: Sequence[Sequence[int]],
) -> None:
    input_tensor = torch.tensor(inputs, dtype=STORAGE_DTYPE)
    target_tensor = torch.tensor(targets, dtype=STORAGE_DTYPE)
    torch.save(
        {
            "schema_version": SCHEMA_VERSION,
            "storage_dtype": str(STORAGE_DTYPE),
            "inputs": input_tensor,
            "targets": target_tensor,
        },
        path,
    )


def _write_json(path: Path, value: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _build_split(
    *,
    split: str,
    source: Path | str,
    split_output: Path,
    pattern: str,
    context_length: int,
    stride: int,
    shard_examples: int,
    encoding: str,
    chunk_bytes: int,
) -> dict[str, Any]:
    if shard_examples <= 0:
        raise UMLDatasetError("shard_examples_must_be_positive")
    paths = source_files(source, pattern=pattern)
    split_output.mkdir(parents=True, exist_ok=True)
    pending_inputs: list[list[int]] = []
    pending_targets: list[list[int]] = []
    shards: list[dict[str, Any]] = []
    source_records: list[dict[str, Any]] = []
    example_count = 0
    token_count = 0

    def flush() -> None:
        if not pending_inputs:
            return
        shard_index = len(shards)
        shard_path = split_output / f"shard_{shard_index:05d}.pt"
        _write_shard(shard_path, pending_inputs, pending_targets)
        shards.append(
            {
                "path": str(shard_path.relative_to(split_output.parent)).replace("\\", "/"),
                "examples": len(pending_inputs),
                "context_length": context_length,
                "storage_dtype": str(STORAGE_DTYPE),
            }
        )
        pending_inputs.clear()
        pending_targets.clear()

    for path in paths:
        stats = SourceStats(path)
        for inputs, targets in iter_file_windows(
            path,
            context_length=context_length,
            stride=stride,
            encoding=encoding,
            chunk_bytes=chunk_bytes,
            stats=stats,
        ):
            pending_inputs.append(inputs)
            pending_targets.append(targets)
            example_count += 1
            token_count += len(inputs) + 1
            if len(pending_inputs) >= shard_examples:
                flush()
        source_records.append(stats.as_dict())
    flush()

    if not shards:
        raise UMLDatasetError(f"split_contains_no_complete_context_windows:{split}")
    return {
        "source_files": source_records,
        "source_file_count": len(source_records),
        "examples": example_count,
        "tokens_consumed_for_windows": token_count,
        "shards": shards,
    }


def build_tensor_dataset(
    *,
    train_source: Path | str,
    validation_source: Path | str,
    output_dir: Path | str,
    context_length: int = DEFAULT_CONTEXT_LENGTH,
    stride: int = DEFAULT_STRIDE,
    shard_examples: int = DEFAULT_SHARD_EXAMPLES,
    pattern: str = "*.txt",
    encoding: str = "utf-8",
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
) -> dict[str, Any]:
    """Build train/validation PyTorch tensor shards and a provenance manifest."""
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise UMLDatasetError(f"output_exists_refuse_overwrite:{output}")
    output.mkdir(parents=True, exist_ok=True)

    train = _build_split(
        split="train",
        source=train_source,
        split_output=output / "train",
        pattern=pattern,
        context_length=context_length,
        stride=stride,
        shard_examples=shard_examples,
        encoding=encoding,
        chunk_bytes=chunk_bytes,
    )
    validation = _build_split(
        split="validation",
        source=validation_source,
        split_output=output / "validation",
        pattern=pattern,
        context_length=context_length,
        stride=stride,
        shard_examples=shard_examples,
        encoding=encoding,
        chunk_bytes=chunk_bytes,
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "tokenizer": {
            "schema_version": "uml_universal_character_tokenizer_v1",
            "token_unit": TOKEN_UNIT,
            "vocab_mode": VOCAB_MODE,
            "vocab_size": VOCAB_SIZE,
            "token_id_min": TOKEN_ID_MIN,
            "token_id_max": TOKEN_ID_MAX,
            "vocab_sha256": VOCAB_SHA256,
        },
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
        "source_policy": "source_files_read_only_unsupported_characters_rejected",
    }
    _write_json(output / "MANIFEST.json", manifest)
    return manifest


def tensor_shards(dataset_dir: Path | str, split: str) -> list[Path]:
    """Return deterministic shard paths for a completed split."""
    root = Path(dataset_dir) / split
    shards = sorted(root.glob("shard_*.pt"))
    if not shards:
        raise UMLDatasetError(f"no_tensor_shards:{split}:{root}")
    return shards


def load_tensor_shard(path: Path | str) -> tuple[torch.Tensor, torch.Tensor]:
    """Load one validated storage shard and return model-ready long tensors."""
    payload = torch.load(Path(path), map_location="cpu", weights_only=True)
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise UMLDatasetError(f"tensor_shard_schema_mismatch:{path}")
    inputs = payload.get("inputs")
    targets = payload.get("targets")
    if not isinstance(inputs, torch.Tensor) or not isinstance(targets, torch.Tensor):
        raise UMLDatasetError(f"tensor_shard_tensors_missing:{path}")
    if inputs.dtype != STORAGE_DTYPE or targets.dtype != STORAGE_DTYPE:
        raise UMLDatasetError(f"tensor_shard_storage_dtype_mismatch:{path}")
    if inputs.ndim != 2 or targets.shape != inputs.shape:
        raise UMLDatasetError(f"tensor_shard_shape_mismatch:{path}")
    if inputs.numel() and (
        int(inputs.min()) < TOKEN_ID_MIN
        or int(inputs.max()) > TOKEN_ID_MAX
        or int(targets.min()) < TOKEN_ID_MIN
        or int(targets.max()) > TOKEN_ID_MAX
    ):
        raise UMLDatasetError(f"tensor_shard_token_range_mismatch:{path}")
    return inputs.to(dtype=MODEL_DTYPE), targets.to(dtype=MODEL_DTYPE)


def iter_tensor_batches(
    shards: Iterable[Path | str],
    *,
    batch_size: int,
    shuffle: bool = False,
    seed: int = 0,
) -> Iterator[tuple[torch.Tensor, torch.Tensor]]:
    """Yield bounded model-ready batches from tensor shards."""
    if batch_size <= 0:
        raise UMLDatasetError("batch_size_must_be_positive")
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed)
    for shard in shards:
        inputs, targets = load_tensor_shard(shard)
        indices = (
            torch.randperm(inputs.shape[0], generator=generator)
            if shuffle
            else torch.arange(inputs.shape[0])
        )
        for start in range(0, inputs.shape[0], batch_size):
            selected = indices[start : start + batch_size]
            yield inputs[selected], targets[selected]


__all__ = [
    "DEFAULT_CHUNK_BYTES",
    "DEFAULT_CONTEXT_LENGTH",
    "DEFAULT_SHARD_EXAMPLES",
    "DEFAULT_STRIDE",
    "MODEL_DTYPE",
    "SCHEMA_VERSION",
    "STORAGE_DTYPE",
    "SourceStats",
    "UMLDatasetError",
    "build_tensor_dataset",
    "iter_encoded_file",
    "iter_tensor_batches",
    "iter_windows",
    "load_tensor_shard",
    "source_files",
    "tensor_shards",
]
