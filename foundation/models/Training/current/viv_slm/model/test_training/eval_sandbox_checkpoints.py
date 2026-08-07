#!/usr/bin/env python3
"""Eval sandbox specialist checkpoints on v43 (Codex fixed lane) and v61 validation."""
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

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import (  # noqa: E402
    IDENTITY_MODEL_CFG,
    evaluate_split,
    load_split,
    resolve_codex_dataset,
)
from sandbox_paths import DEEP_CKPT, EFFICIENT_CKPT  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402


def _eval_checkpoint(path: Path, lane: str) -> None:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    _, vocab_path, _ = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model = TransformerLanguageModel(tok.vocab_size, **IDENTITY_MODEL_CFG).to(device)
    model.load_state_dict(payload["model_state_dict"], strict=False)
    model.eval()
    for ds in ("v43", "v61"):
        _, _, tensor_dir = resolve_codex_dataset(ds)
        val_in, val_tg, val_mask = load_split(
            tensor_dir, "validation", vocab_size=tok.vocab_size, response_only_loss=True
        )
        val = evaluate_split(
            model, val_in, val_tg, device=device, batch_size=64, loss_masks=val_mask
        )
        print(
            f"SANDBOX_{lane} on {ds} val: "
            f"nll={val['nll']:.4f} ppl={val['perplexity']:.3f} acc={val['token_accuracy']:.4f}"
        )


def main() -> int:
    configure_plant_runtime(device="cuda")
    _eval_checkpoint(EFFICIENT_CKPT, "efficient")
    _eval_checkpoint(DEEP_CKPT, "deep")
    print("CODEX_TARGET (v43 fixed lane): nll=0.130 acc=0.961")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
