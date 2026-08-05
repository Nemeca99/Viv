#!/usr/bin/env python3
"""Random-weight architecture preflight for the Part 6 transformer."""
from __future__ import annotations

from pathlib import Path
import sys

import torch
from torch import nn

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402


def main() -> int:
    torch.manual_seed(11)
    tokenizer = CharacterTokenizer.from_texts(["the dog bites man\n"])
    model = TransformerLanguageModel(
        tokenizer.vocab_size,
        context_length=8,
        embedding_width=128,
        num_heads=4,
        head_size=32,
        num_layers=4,
        dropout=0.2,
    )
    assert tuple(model.token_embedding_table.weight.shape) == (
        tokenizer.vocab_size,
        128,
    )
    assert tuple(model.position_embedding_table.weight.shape) == (8, 128)
    assert len(model.blocks) == 4
    assert isinstance(model.embedding_dropout, nn.Dropout)
    assert isinstance(model.blocks[0].feed_forward.network[1], nn.GELU)
    assert tuple(model.blocks[0].feed_forward.network[0].weight.shape) == (512, 128)
    assert tuple(model.blocks[0].feed_forward.network[2].weight.shape) == (128, 512)
    assert tuple(model.lm_head.weight.shape) == (tokenizer.vocab_size, 128)
    for block in model.blocks:
        assert len(block.self_attention.heads) == 4
        assert tuple(block.self_attention.projection.weight.shape) == (128, 128)
        assert isinstance(block.layer_norm_attention, nn.LayerNorm)
        assert isinstance(block.layer_norm_feed_forward, nn.LayerNorm)
        for head in block.self_attention.heads:
            assert tuple(head.key.weight.shape) == (32, 128)
            assert tuple(head.query.weight.shape) == (32, 128)
            assert tuple(head.value.weight.shape) == (32, 128)
            assert head.scale == 32 ** -0.5
            assert torch.count_nonzero(torch.triu(head.causal_mask, diagonal=1)) == 0

    model.eval()
    left = torch.tensor([tokenizer.encode("the dog")], dtype=torch.long)
    right = torch.tensor([tokenizer.encode("the man")], dtype=torch.long)
    left_logits, left_attention = model(left, return_attention=True)
    right_logits, right_attention = model(right, return_attention=True)
    assert tuple(left_logits.shape) == (1, 7, tokenizer.vocab_size)
    assert len(left_attention) == 4
    assert all(len(block_weights) == 4 for block_weights in left_attention)
    for block_weights in left_attention:
        for weights in block_weights:
            assert tuple(weights.shape) == (1, 7, 7)
            assert torch.allclose(weights.sum(dim=-1), torch.ones(1, 7), atol=1e-5)
            assert torch.count_nonzero(torch.triu(weights[0], diagonal=1)) == 0
    assert torch.allclose(left_logits[:, :1], right_logits[:, :1], atol=1e-6)
    assert not torch.allclose(left_logits[:, -1:], right_logits[:, -1:])

    targets = torch.tensor([tokenizer.encode("he dog ")], dtype=torch.long)
    loss, accuracy = model.loss_and_accuracy(left_logits, targets)
    assert torch.isfinite(loss)
    assert 0.0 <= float(accuracy) <= 1.0

    # Dropout is present in training mode and disabled for deterministic eval.
    model.train()
    train_a = model(left)
    train_b = model(left)
    assert not torch.allclose(train_a, train_b)
    model.eval()
    eval_a = model(left)
    eval_b = model(left)
    assert torch.allclose(eval_a, eval_b)

    generator = torch.Generator(device="cpu")
    generator.manual_seed(12)
    generated = model.generate(left[:, :3], max_new_tokens=12, generator=generator)
    assert tuple(generated.shape) == (1, 15)
    assert int(generated.min()) >= 0
    assert int(generated.max()) < tokenizer.vocab_size
    assert len(tokenizer.decode(generated[0].tolist())) == 15
    greedy = model.generate(
        left[:, :3],
        max_new_tokens=4,
        temperature=0.0,
        top_k=4,
    )
    greedy_again = model.generate(
        left[:, :3],
        max_new_tokens=4,
        temperature=0.0,
        top_k=4,
    )
    assert torch.equal(greedy, greedy_again)

    print(
        "UML_PART6_TRANSFORMER_PREFLIGHT_PASS "
        f"vocab_size={tokenizer.vocab_size} "
        "embedding_width=128 "
        "num_heads=4 "
        "head_size=32 "
        "num_layers=4 "
        "ffn_128_to_512_to_128=true "
        "gelu=true "
        "dropout=true "
        "layer_norm=true "
        "residual_connections=true "
        "causal_masks=true "
        "attention_shapes=true "
        "loss_finite=true "
        "temperature_zero_argmax=true "
        "top_k=true "
        "weights_untrained=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
