#!/usr/bin/env python3
"""Eval Codex parent checkpoint vs sandbox metrics (read-only)."""
from __future__ import annotations

import sys
from pathlib import Path

import torch

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))
if str(SANDBOX) not in sys.path:
    sys.path.insert(0, str(SANDBOX))

from plant_checkpoint import load_plant_state_dict  # noqa: E402
from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import (  # noqa: E402
    CODEX_PARENT_CHECKPOINT,
    IDENTITY_MODEL_CFG,
    evaluate_split,
    load_split,
    read_input_manifest,
    resolve_codex_dataset,
)
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402


def main() -> int:
    configure_plant_runtime(device="cuda")
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    parent = torch.load(CODEX_PARENT_CHECKPOINT, map_location="cpu", weights_only=False)
    model = TransformerLanguageModel(
        int(parent.get("vocab_size") or 96), **IDENTITY_MODEL_CFG
    ).to(device)
    load_plant_state_dict(model, parent["model_state_dict"], strict=False, config=IDENTITY_MODEL_CFG)
    model.eval()

    for lane_id in ("v43", "v61"):
        root, vocab_path, tensor_dir = resolve_codex_dataset(lane_id)
        read_input_manifest(root)
        tok = CharacterTokenizer.from_manifest(vocab_path)
        val_in, val_tg, val_mask = load_split(
            tensor_dir, "validation", vocab_size=tok.vocab_size, response_only_loss=True
        )
        val = evaluate_split(
            model, val_in, val_tg, device=device, batch_size=64, loss_masks=val_mask
        )
        print(
            f"CODEX_PARENT on {lane_id} val: "
            f"nll={val['nll']:.4f} ppl={val['perplexity']:.3f} acc={val['token_accuracy']:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
