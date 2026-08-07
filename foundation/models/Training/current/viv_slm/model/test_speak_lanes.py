#!/usr/bin/env python3
"""Tests for dual speak lanes (CPU efficient / GPU deep, same weights)."""
from __future__ import annotations

from pathlib import Path
import sys

import torch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from plant_runtime import select_speak_device  # noqa: E402
from speak_lanes import lane_defaults, speak_viv  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402


def main() -> int:
    assert select_speak_device("efficient").type == "cpu"
    assert select_speak_device("mind").type == "cpu"
    deep = select_speak_device("deep")
    assert deep.type in ("cuda", "cpu")

    eff = lane_defaults("efficient")
    deep_d = lane_defaults("deep")
    assert eff["max_new_tokens"] < deep_d["max_new_tokens"]
    assert eff["draft_mode"] == "cpu_gate"
    assert deep_d["max_new_tokens"] >= 128

    torch.manual_seed(3)
    tokenizer = CharacterTokenizer.from_texts(["the dog bites man\n"])
    model = TransformerLanguageModel(
        tokenizer.vocab_size,
        context_length=32,
        embedding_width=64,
        num_heads=4,
        head_size=16,
        num_layers=2,
        dropout=0.0,
    )
    model.eval()
    prompt = torch.tensor([tokenizer.encode("the dog")], dtype=torch.long)

    efficient = speak_viv(
        model,
        prompt,
        lane="efficient",
        max_new_tokens=12,
        configure_runtime=True,
        stamp_master_rid=True,
        decode_fn=tokenizer.decode,
    )
    assert efficient["receipt"]["lane"] == "efficient"
    assert efficient["receipt"]["device"] == "cpu"
    assert efficient["receipt"]["same_weights"] is True
    assert efficient["receipt"]["piston_actuated"] is False
    assert efficient["ids"].shape[1] >= prompt.shape[1]

    deep_out = speak_viv(
        model,
        prompt,
        lane="deep",
        max_new_tokens=16,
        configure_runtime=True,
        stamp_master_rid=False,
        decode_fn=tokenizer.decode,
    )
    assert deep_out["receipt"]["lane"] == "deep"
    assert deep_out["receipt"]["device"] in ("cpu", "cuda", "cuda:0")
    assert deep_out["receipt"]["max_new_tokens"] == 16
    assert deep_out["ids"].device.type == (
        "cuda" if deep_out["receipt"]["device"].startswith("cuda") else "cpu"
    )

    print(
        "VIV_SPEAK_LANES_PASS "
        f"efficient_device={efficient['receipt']['device']} "
        f"deep_device={deep_out['receipt']['device']} "
        f"efficient_new={efficient['receipt']['new_tokens']} "
        f"deep_new={deep_out['receipt']['new_tokens']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
