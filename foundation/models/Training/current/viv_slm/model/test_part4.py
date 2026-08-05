#!/usr/bin/env python3
"""Regression tests for the Part 4 causal context model."""
from __future__ import annotations

from pathlib import Path
import sys

import torch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from context import ContextLanguageModel  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402


def main() -> int:
    torch.manual_seed(7)
    tokenizer = CharacterTokenizer.from_texts(["the dog bites man\n"])
    model = ContextLanguageModel(
        tokenizer.vocab_size,
        context_length=8,
        embedding_width=64,
    )
    assert tuple(model.token_embedding_table.weight.shape) == (
        tokenizer.vocab_size,
        64,
    )
    assert tuple(model.position_embedding_table.weight.shape) == (8, 64)
    assert torch.equal(model.causal_mask, torch.tril(torch.ones(8, 8)))
    assert torch.count_nonzero(torch.triu(model.causal_mask, diagonal=1)) == 0
    assert torch.all(model.causal_mask.diagonal() == 1)
    assert not torch.equal(
        model.position_embedding_table.weight[0],
        model.position_embedding_table.weight[1],
    )

    left = torch.tensor([tokenizer.encode("the dog")], dtype=torch.long)
    right = torch.tensor([tokenizer.encode("the man")], dtype=torch.long)
    left_logits = model(left)
    right_logits = model(right)
    assert tuple(left_logits.shape) == (1, 7, tokenizer.vocab_size)
    assert torch.allclose(left_logits[:, :1], right_logits[:, :1])
    assert not torch.allclose(left_logits[:, -1:], right_logits[:, -1:])

    targets = torch.tensor([tokenizer.encode("he dog ")], dtype=torch.long)
    loss, accuracy = model.loss_and_accuracy(left_logits, targets)
    assert torch.isfinite(loss)
    assert 0.0 <= float(accuracy) <= 1.0
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001)
    before = model.token_embedding_table.weight.detach().clone()
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    assert model.token_embedding_table.weight.grad is not None
    optimizer.step()
    assert not torch.equal(before, model.token_embedding_table.weight.detach())

    generator = torch.Generator(device="cpu")
    generator.manual_seed(8)
    generated = model.generate(
        left[:, :3],
        max_new_tokens=12,
        generator=generator,
    )
    assert tuple(generated.shape) == (1, 15)
    assert int(generated.min()) >= 0
    assert int(generated.max()) < tokenizer.vocab_size
    assert len(tokenizer.decode(generated[0].tolist())) == 15

    print(
        "UML_PART4_CONTEXT_PASS "
        f"vocab_size={tokenizer.vocab_size} "
        "token_embedding_64=true "
        "position_embedding_64=true "
        "causal_lower_triangle=true "
        "future_blocked=true "
        "position_order_sensitive=true "
        "adamw_update=true "
        "multinomial_generation=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
