#!/usr/bin/env python3
"""Focused regression for the Unicode-complete CPU Universal UML tokenizer."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.uml_character_tokenizer import (  # noqa: E402
    SCHEMA_VERSION,
    TOKEN_ID_MAX,
    TOKEN_ID_MIN,
    UMLCharacterTokenizer,
    UNICODE_SCALAR_COUNT,
    VOCAB_MODE,
    VOCAB_SIZE,
    character_to_token_id,
    decode,
    decode_structure,
    encode,
    itos,
    stoi,
    structure,
    token_id_to_character,
    vocab,
)


def main() -> int:
    assert SCHEMA_VERSION == "uml_universal_character_tokenizer_v1"
    assert VOCAB_MODE == "all_unicode_scalar_values"
    assert VOCAB_SIZE == UNICODE_SCALAR_COUNT == 1_112_064
    assert len(vocab) == VOCAB_SIZE
    assert isinstance(stoi, dict)
    assert isinstance(itos, dict)
    assert TOKEN_ID_MIN == 0
    assert TOKEN_ID_MAX == VOCAB_SIZE - 1

    # The universal UML index is the compact Unicode scalar index, independent
    # of the mathematical UML calculator's separate base-52 notation.
    assert character_to_token_id("A") == ord("A")
    assert character_to_token_id("z") == ord("z")
    assert character_to_token_id("é") == ord("é")
    assert character_to_token_id("🙂") == ord("🙂") - 0x800
    assert token_id_to_character(0) == "\x00"
    assert token_id_to_character(character_to_token_id("🙂")) == "🙂"

    assert encode("hello") == [104, 101, 108, 108, 111]
    sample = "Az !\nnaïve café — 日本語 🙂\x00"
    ids = encode(sample)
    assert len(ids) == len(sample)
    assert decode(ids) == sample
    assert UMLCharacterTokenizer.decode(UMLCharacterTokenizer.encode(sample)) == sample
    assert itos[stoi["🙂"]] == "🙂"

    encoded_structure = structure(sample)
    json.dumps(encoded_structure, ensure_ascii=False, sort_keys=True)
    assert encoded_structure["uml_layer"] == "universal_machine_language"
    assert encoded_structure["vocab_size"] == 1_112_064
    assert encoded_structure["lossless"] is True
    assert decode_structure(encoded_structure) == sample

    try:
        encode("bad\ud800")
    except ValueError as exc:
        assert "surrogate_not_scalar" in str(exc)
    else:
        raise AssertionError("surrogate_accepted")

    try:
        decode([TOKEN_ID_MAX + 1])
    except ValueError as exc:
        assert "token_id_out_of_range" in str(exc)
    else:
        raise AssertionError("unknown_token_id_accepted")

    try:
        decode_structure({**encoded_structure, "vocab_sha256": "wrong"})
    except ValueError as exc:
        assert str(exc) == "uml_unicode_structure_vocab_hash_mismatch"
    else:
        raise AssertionError("tampered_structure_vocab_hash_accepted")

    print(
        "UML_UNIVERSAL_CHARACTER_TOKENIZER_PASS "
        f"unicode_scalar_vocab_size={VOCAB_SIZE} "
        "stoi_itos_lazy_bijective=true "
        "hello_roundtrip=true "
        "newline_unicode_emoji_roundtrip=true "
        "surrogates_rejected=true "
        "math_base52_layer_separate=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
