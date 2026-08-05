"""Corpus-derived character tokenizer used only by the Part 3 model."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "uml_part3_character_tokenizer_v1"
TOKEN_UNIT = "corpus_character"
VOCAB_MODE = "scanned_append_only"


def _validate_vocab(vocab: Sequence[str]) -> tuple[str, ...]:
    if isinstance(vocab, (str, bytes)):
        raise TypeError("vocab_requires_character_sequence")
    values = tuple(vocab)
    if not values:
        raise ValueError("vocab_must_not_be_empty")
    for index, value in enumerate(values):
        if not isinstance(value, str) or len(value) != 1:
            raise ValueError(f"vocab_entry_must_be_one_character:index={index}")
        if 0xD800 <= ord(value) <= 0xDFFF:
            raise ValueError(f"vocab_surrogate_not_allowed:index={index}")
    if len(set(values)) != len(values):
        raise ValueError("vocab_contains_duplicate_character")
    return values


def discover_characters(texts: Iterable[str]) -> tuple[str, ...]:
    """Return every scanned character once, in deterministic code-point order."""
    characters: set[str] = set()
    for text in texts:
        if not isinstance(text, str):
            raise TypeError("vocab_source_requires_text")
        characters.update(text)
    return tuple(sorted(characters, key=ord))


def extend_vocab(existing_vocab: Sequence[str], texts: Iterable[str]) -> tuple[str, ...]:
    """Preserve old IDs and append newly observed characters."""
    existing = _validate_vocab(existing_vocab)
    additions = tuple(
        character
        for character in discover_characters(texts)
        if character not in existing
    )
    return existing + additions


class CharacterTokenizer:
    """The requested ``stoi``/``itos`` mapping plus lossless encode/decode."""

    def __init__(self, vocab: Sequence[str]):
        self.vocab = _validate_vocab(vocab)
        self.stoi: dict[str, int] = {
            character: index for index, character in enumerate(self.vocab)
        }
        self.itos: dict[int, str] = {
            index: character for index, character in enumerate(self.vocab)
        }
        self.vocab_size = len(self.vocab)
        self.vocab_sha256 = sha256("".join(self.vocab).encode("utf-8")).hexdigest()

    @classmethod
    def from_texts(cls, texts: Iterable[str]) -> "CharacterTokenizer":
        return cls(discover_characters(texts))

    @classmethod
    def from_manifest(cls, path: Path | str) -> "CharacterTokenizer":
        with Path(path).open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, Mapping):
            raise ValueError("vocab_manifest_requires_object")
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("vocab_manifest_schema_mismatch")
        vocab = value.get("vocab")
        if not isinstance(vocab, list):
            raise ValueError("vocab_manifest_vocab_missing")
        tokenizer = cls(vocab)
        if value.get("vocab_size") != tokenizer.vocab_size:
            raise ValueError("vocab_manifest_size_mismatch")
        if value.get("vocab_sha256") != tokenizer.vocab_sha256:
            raise ValueError("vocab_manifest_hash_mismatch")
        return tokenizer

    def encode(self, text: str) -> list[int]:
        if not isinstance(text, str):
            raise TypeError("tokenizer_requires_text")
        ids: list[int] = []
        for position, character in enumerate(text):
            try:
                ids.append(self.stoi[character])
            except KeyError:
                raise ValueError(
                    f"character_not_in_vocab:U+{ord(character):04X}:position={position}"
                ) from None
        return ids

    def decode(self, token_ids: Iterable[int]) -> str:
        if isinstance(token_ids, (str, bytes)):
            raise TypeError("decoder_requires_integer_ids")
        output: list[str] = []
        for position, token_id in enumerate(token_ids):
            if not isinstance(token_id, int) or isinstance(token_id, bool):
                raise ValueError(f"token_id_must_be_integer:position={position}")
            if token_id not in self.itos:
                raise ValueError(f"token_id_out_of_range:{token_id}:position={position}")
            output.append(self.itos[token_id])
        return "".join(output)

    def expanded(self, texts: Iterable[str]) -> "CharacterTokenizer":
        return type(self)(extend_vocab(self.vocab, texts))

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "token_unit": TOKEN_UNIT,
            "vocab_mode": VOCAB_MODE,
            "vocab_size": self.vocab_size,
            "token_id_min": 0,
            "token_id_max": self.vocab_size - 1,
            "vocab_sha256": self.vocab_sha256,
            "vocab": list(self.vocab),
        }


def write_manifest(
    path: Path | str,
    tokenizer: CharacterTokenizer,
    *,
    source_records: Sequence[Mapping[str, Any]],
    parent_vocab_sha256: str | None = None,
) -> dict[str, Any]:
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"vocab_output_exists_refuse_overwrite:{output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = tokenizer.manifest()
    manifest.update(
        {
            "status": "COMPLETE",
            "parent_vocab_sha256": parent_vocab_sha256,
            "source_files": [dict(record) for record in source_records],
        }
    )
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return manifest
