#!/usr/bin/env python3
"""Regression tests for the isolated Part 3 tokenizer and bigram model."""
from __future__ import annotations

from pathlib import Path
import sys

import torch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from bigram import BigramLanguageModel  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402


def main() -> int:
    tokenizer = CharacterTokenizer.from_texts(["hello q", "quick\n"])
    hello_ids = tokenizer.encode("hello")
    assert tokenizer.decode(hello_ids) == "hello"
    assert tokenizer.stoi["q"] < tokenizer.vocab_size
    assert tokenizer.itos[tokenizer.stoi["u"]] == "u"

    base = CharacterTokenizer.from_texts(["ab"])
    expanded = base.expanded(["abc"])
    assert expanded.stoi["a"] == base.stoi["a"]
    assert expanded.stoi["b"] == base.stoi["b"]
    assert expanded.stoi["c"] == base.vocab_size

    try:
        tokenizer.encode("hello🙂")
    except ValueError as exc:
        assert "character_not_in_vocab" in str(exc)
    else:
        raise AssertionError("unknown_character_accepted")

    model = BigramLanguageModel(tokenizer.vocab_size)
    assert tuple(model.logits_table.shape) == (
        tokenizer.vocab_size,
        tokenizer.vocab_size,
    )
    inputs = torch.tensor([tokenizer.encode("hello q")], dtype=torch.long)
    targets = torch.tensor([tokenizer.encode("ello q\n")], dtype=torch.long)
    logits = model(inputs)
    assert tuple(logits.shape) == (1, 7, tokenizer.vocab_size)
    loss, accuracy = model.loss_and_accuracy(logits, targets)
    assert torch.isfinite(loss)
    assert 0.0 <= float(accuracy) <= 1.0

    optimizer = torch.optim.AdamW(model.parameters(), lr=0.01)
    before = model.logits_table.detach().clone()
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    assert model.logits_table.grad is not None
    optimizer.step()
    assert not torch.equal(before, model.logits_table.detach())

    generator = torch.Generator(device="cpu")
    generator.manual_seed(7)
    generated = model.generate(
        inputs[:, :1],
        max_new_tokens=16,
        generator=generator,
    )
    assert tuple(generated.shape) == (1, 17)
    assert int(generated.min()) >= 0
    assert int(generated.max()) < tokenizer.vocab_size
    assert len(tokenizer.decode(generated[0].tolist())) == 17

    print(
        "UML_PART3_BIGRAM_PASS "
        f"vocab_size={tokenizer.vocab_size} "
        "stoi_itos_roundtrip=true "
        "logits_table=true "
        "cross_entropy=true "
        "adamw_update=true "
        "multinomial_generation=true "
        "append_only_vocab_expansion=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
