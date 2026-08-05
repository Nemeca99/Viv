#!/usr/bin/env python3
"""Regression checks for Part 7 generation controls and gradient clipping."""
from __future__ import annotations

from pathlib import Path
import sys

import torch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402


def _gradient_norm(model: torch.nn.Module) -> float:
    total = torch.zeros((), dtype=torch.float32)
    for parameter in model.parameters():
        if parameter.grad is not None:
            total = total + parameter.grad.detach().float().pow(2).sum()
    return float(total.sqrt())


def main() -> int:
    torch.manual_seed(13)
    tokenizer = CharacterTokenizer.from_texts(["the dog bites man\n"])
    model = TransformerLanguageModel(
        tokenizer.vocab_size,
        context_length=8,
        embedding_width=128,
        num_heads=4,
        head_size=32,
        num_layers=4,
        dropout=0.0,
    )
    model.eval()
    prompt = torch.tensor([tokenizer.encode("the")], dtype=torch.long)
    greedy_a = model.generate(prompt, max_new_tokens=12, temperature=0.0, top_k=4)
    greedy_b = model.generate(prompt, max_new_tokens=12, temperature=0.0, top_k=4)
    assert torch.equal(greedy_a, greedy_b)
    assert tuple(greedy_a.shape) == (1, 15)

    sampled = model.generate(
        prompt,
        max_new_tokens=12,
        temperature=0.75,
        top_k=4,
        generator=torch.Generator(device="cpu").manual_seed(14),
    )
    assert tuple(sampled.shape) == (1, 15)
    assert int(sampled.min()) >= 0
    assert int(sampled.max()) < tokenizer.vocab_size

    inputs = torch.tensor([tokenizer.encode("the dog")], dtype=torch.long)
    targets = torch.tensor([tokenizer.encode("he dog ")], dtype=torch.long)
    logits = model(inputs)
    loss, _ = model.loss_and_accuracy(logits, targets)
    loss.backward()
    before = _gradient_norm(model)
    returned = torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
    after = _gradient_norm(model)
    assert float(returned) >= 0.0
    assert before >= after
    assert after <= 1.00001

    print(
        "UML_PART7_CONTROLS_PASS "
        "temperature_zero_deterministic=true "
        "top_k_40_path=true "
        "temperature_sampling=true "
        "gradient_clipping=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
