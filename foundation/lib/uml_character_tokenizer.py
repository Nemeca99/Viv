"""CPU Universal Machine Language (UML) Unicode character tokenizer.

This module is deliberately separate from ``lib.uml_engine``.  The latter is
the existing mathematical UML calculator with its base-52 notation.  This
module implements the Universal Machine Language character address space:
every Unicode scalar value is one valid character token.

The mapping is deterministic and mathematical rather than corpus-derived:

* Unicode scalar code points ``0x0000..0xD7FF`` map to the same integer index.
* The surrogate range ``0xD800..0xDFFF`` is excluded because surrogates are
  not Unicode scalar values.
* Code points ``0xE000..0x10FFFF`` are compacted by subtracting ``0x800``.

The module-level ``stoi`` and ``itos`` objects are dictionary-compatible lazy
dictionaries.  They resolve every Unicode scalar on demand without allocating
over a million Python dictionary entries at import time.  ``vocab`` is the
complete Unicode-scalar string, and ``vocab_size`` is therefore 1,112,064.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from hashlib import sha256
from typing import Any

SCHEMA_VERSION = "uml_universal_character_tokenizer_v1"
TOKEN_UNIT = "unicode_scalar"
TOKEN_ID_BASE = 0
MAX_UNICODE = 0x10FFFF
SURROGATE_START = 0xD800
SURROGATE_END = 0xDFFF
SURROGATE_COUNT = SURROGATE_END - SURROGATE_START + 1
UNICODE_SCALAR_COUNT = MAX_UNICODE + 1 - SURROGATE_COUNT
TOKEN_ID_MIN = TOKEN_ID_BASE
TOKEN_ID_MAX = UNICODE_SCALAR_COUNT - 1
VOCAB_MODE = "all_unicode_scalar_values"


def _build_unicode_vocab() -> str:
    """Build the complete ordered Unicode scalar vocabulary once."""
    return "".join(
        chr(codepoint)
        for codepoint in range(MAX_UNICODE + 1)
        if not SURROGATE_START <= codepoint <= SURROGATE_END
    )


# ``vocab`` is the complete list, not a guessed 65-character subset.
vocab = _build_unicode_vocab()
VOCAB = vocab
VOCAB_SIZE = len(vocab)
VOCAB_SHA256 = sha256(vocab.encode("utf-8")).hexdigest()
if VOCAB_SIZE != UNICODE_SCALAR_COUNT:
    raise RuntimeError("uml_unicode_vocab_size_mismatch")


def _validate_character(character: str) -> int:
    if not isinstance(character, str) or len(character) != 1:
        raise ValueError("uml_unicode_token_requires_one_character")
    codepoint = ord(character)
    if SURROGATE_START <= codepoint <= SURROGATE_END:
        raise ValueError("uml_unicode_token_surrogate_not_scalar")
    return codepoint


def _character_to_token_id(character: str) -> int:
    codepoint = _validate_character(character)
    return codepoint if codepoint < SURROGATE_START else codepoint - SURROGATE_COUNT


def _token_id_to_character(token_id: int) -> str:
    if not isinstance(token_id, int) or isinstance(token_id, bool):
        raise ValueError("uml_unicode_token_id_must_be_integer")
    if not TOKEN_ID_MIN <= token_id <= TOKEN_ID_MAX:
        raise ValueError(f"uml_unicode_token_id_out_of_range:{token_id}")
    codepoint = token_id if token_id < SURROGATE_START else token_id + SURROGATE_COUNT
    return chr(codepoint)


class UnicodeStoi(dict[str, int]):
    """Lazy ``character -> integer`` dictionary for every Unicode scalar."""

    def __missing__(self, character: str) -> int:
        token_id = _character_to_token_id(character)
        self[character] = token_id
        return token_id


class UnicodeItos(dict[int, str]):
    """Lazy ``integer -> character`` dictionary for every Unicode scalar."""

    def __missing__(self, token_id: int) -> str:
        character = _token_id_to_character(token_id)
        self[token_id] = character
        return character


# These are real dictionaries, as requested, with lazy materialization for
# the full Unicode range.  Common characters become ordinary dict entries as
# soon as they are used by encode/decode.
stoi: dict[str, int] = UnicodeStoi()
itos: dict[int, str] = UnicodeItos()


def character_to_token_id(character: str) -> int:
    """Return the deterministic Unicode-scalar token ID for one character."""
    return stoi[character]


def token_id_to_character(token_id: int) -> str:
    """Return the Unicode scalar addressed by one token ID."""
    return itos[token_id]


def encode(text: str) -> list[int]:
    """Encode every Unicode scalar in ``text`` as one UML token ID."""
    if not isinstance(text, str):
        raise TypeError("uml_unicode_tokenizer_requires_text")
    token_ids: list[int] = []
    for position, character in enumerate(text):
        try:
            token_ids.append(stoi[character])
        except ValueError as exc:
            raise ValueError(f"{exc}:position={position}") from None
    return token_ids


def decode(token_ids: Iterable[int]) -> str:
    """Decode a Unicode-scalar token-ID sequence back to exact text."""
    if isinstance(token_ids, (str, bytes)):
        raise TypeError("uml_unicode_decoder_requires_integer_token_ids")
    characters: list[str] = []
    for position, token_id in enumerate(token_ids):
        try:
            characters.append(itos[token_id])
        except ValueError as exc:
            raise ValueError(f"{exc}:position={position}") from None
    return "".join(characters)


tokenize = encode


def _text_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def structure(text: str) -> dict[str, Any]:
    """Return a serializable UML structure for one encoded text sample."""
    token_ids = encode(text)
    return {
        "schema_version": SCHEMA_VERSION,
        "notation": "UML",
        "uml_layer": "universal_machine_language",
        "token_unit": TOKEN_UNIT,
        "token_id_base": TOKEN_ID_BASE,
        "lossless": True,
        "vocab_mode": VOCAB_MODE,
        "vocab_size": VOCAB_SIZE,
        "vocab_sha256": VOCAB_SHA256,
        "text_length": len(text),
        "utf8_byte_length": len(text.encode("utf-8")),
        "text_sha256": _text_sha256(text),
        "token_ids": token_ids,
    }


def decode_structure(value: Mapping[str, Any]) -> str:
    """Decode and validate a structure produced by :func:`structure`."""
    if not isinstance(value, Mapping):
        raise TypeError("uml_unicode_structure_requires_mapping")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("uml_unicode_structure_schema_mismatch")
    if value.get("vocab_mode") != VOCAB_MODE or value.get("vocab_size") != VOCAB_SIZE:
        raise ValueError("uml_unicode_structure_vocab_mismatch")
    if value.get("vocab_sha256") != VOCAB_SHA256:
        raise ValueError("uml_unicode_structure_vocab_hash_mismatch")
    token_ids = value.get("token_ids")
    if not isinstance(token_ids, list):
        raise ValueError("uml_unicode_structure_token_ids_missing")
    text = decode(token_ids)
    if value.get("text_length") != len(text):
        raise ValueError("uml_unicode_structure_text_length_mismatch")
    if value.get("text_sha256") != _text_sha256(text):
        raise ValueError("uml_unicode_structure_text_hash_mismatch")
    return text


class UMLCharacterTokenizer:
    """Stateless facade for the Universal Machine Language tokenizer."""

    schema_version = SCHEMA_VERSION
    token_unit = TOKEN_UNIT
    vocab = vocab
    vocab_size = VOCAB_SIZE
    stoi = stoi
    itos = itos

    @staticmethod
    def encode(text: str) -> list[int]:
        return encode(text)

    @staticmethod
    def decode(token_ids: Iterable[int]) -> str:
        return decode(token_ids)

    @staticmethod
    def structure(text: str) -> dict[str, Any]:
        return structure(text)

    @staticmethod
    def tokenize(text: str) -> list[int]:
        return encode(text)


__all__ = [
    "MAX_UNICODE",
    "SCHEMA_VERSION",
    "TOKEN_ID_BASE",
    "TOKEN_ID_MAX",
    "TOKEN_ID_MIN",
    "TOKEN_UNIT",
    "UNICODE_SCALAR_COUNT",
    "UMLCharacterTokenizer",
    "UnicodeItos",
    "UnicodeStoi",
    "VOCAB",
    "VOCAB_MODE",
    "VOCAB_SHA256",
    "VOCAB_SIZE",
    "character_to_token_id",
    "decode",
    "decode_structure",
    "encode",
    "itos",
    "stoi",
    "structure",
    "token_id_to_character",
    "tokenize",
    "vocab",
]
