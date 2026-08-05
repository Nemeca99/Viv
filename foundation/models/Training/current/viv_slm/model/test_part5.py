#!/usr/bin/env python3
"""Regression tests for the Part 5 single-head self-attention model."""
from __future__ import annotations

from pathlib import Path
import sys

import torch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from attention import SelfAttentionLanguageModel  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402


def main() -> int:
    torch.manual_seed(9)
    tokenizer = CharacterTokenizer.from_texts(["the dog bites man\n"])
    model = SelfAttentionLanguageModel(
        tokenizer.vocab_size,
        context_length=8,
        embedding_width=64,
        head_size=32,
    )
    assert tuple(model.token_embedding_table.weight.shape) == (
        tokenizer.vocab_size,
        64,
    )
    assert tuple(model.position_embedding_table.weight.shape) == (8, 64)
    assert tuple(model.head.key.weight.shape) == (32, 64)
    assert tuple(model.head.query.weight.shape) == (32, 64)
    assert tuple(model.head.value.weight.shape) == (32, 64)
    assert model.head.scale == 32 ** -0.5
    assert torch.equal(model.head.causal_mask, torch.tril(torch.ones(8, 8)))

    left = torch.tensor([tokenizer.encode("the dog")], dtype=torch.long)
    right = torch.tensor([tokenizer.encode("the man")], dtype=torch.long)
    left_logits, left_weights = model(left, return_attention=True)
    right_logits, right_weights = model(right, return_attention=True)
    assert tuple(left_logits.shape) == (1, 7, tokenizer.vocab_size)
    assert tuple(left_weights.shape) == (1, 7, 7)
    assert torch.allclose(left_weights.sum(dim=-1), torch.ones(1, 7))
    assert torch.count_nonzero(torch.triu(left_weights[0], diagonal=1)) == 0
    assert torch.allclose(left_logits[:, :1], right_logits[:, :1])
    assert torch.allclose(left_weights[:, :1], right_weights[:, :1])
    assert not torch.allclose(left_logits[:, -1:], right_logits[:, -1:])

    targets = torch.tensor([tokenizer.encode("he dog ")], dtype=torch.long)
    loss, accuracy = model.loss_and_accuracy(left_logits, targets)
    assert torch.isfinite(loss)
    assert 0.0 <= float(accuracy) <= 1.0
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001)
    before = model.head.query.weight.detach().clone()
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    assert model.head.query.weight.grad is not None
    assert model.head.key.weight.grad is not None
    assert model.head.value.weight.grad is not None
    optimizer.step()
    assert not torch.equal(before, model.head.query.weight.detach())

    generator = torch.Generator(device="cpu")
    generator.manual_seed(10)
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
        "UML_PART5_SELF_ATTENTION_PASS "
        f"vocab_size={tokenizer.vocab_size} "
        "qkv_projections=true "
        "sqrt_dk_scaling=true "
        "future_neg_inf_mask=true "
        "softmax_rows_sum_one=true "
        "upper_triangle_zero=true "
        "future_blocked=true "
        "qkv_gradients=true "
        "adamw_update=true "
        "multinomial_generation=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
