#!/usr/bin/env python3
"""Mint sandbox efficient + deep specialist checkpoints (sandbox writes only).

Discovery found no live *.pt under viv_slm — freshly train a tiny specialist pair
here. Shared tokenizer/vocab = same identity; different seeds/steps = distinct weights.

Does not touch Codex/operator campaign trees or checkpoints outside test_training/.
"""
from __future__ import annotations

from hashlib import sha256
import json
import sys
from pathlib import Path

import torch

SANDBOX = Path(__file__).resolve().parents[1]  # legacy home: parents[1] = test_training/
MODEL = SANDBOX.parent
if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))
if str(SANDBOX) not in sys.path:
    sys.path.insert(0, str(SANDBOX))

from sandbox_paths import (  # noqa: E402
    CHECKPOINTS_DIR,
    DEEP_CKPT,
    DEEP_TRAIN,
    EFFICIENT_CKPT,
    EFFICIENT_TRAIN,
    IDENTITY_CORPUS,
    RUNS_DIR,
    SCHEMA_CKPT,
    SHARED_DIR,
    TINY_CFG,
    VOCAB_MANIFEST,
)
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402


def _fingerprint(state: dict) -> str:
    blob: list[str] = []
    for key, tensor in sorted(state.items()):
        if torch.is_tensor(tensor):
            blob.append(
                f"{key}:{float(tensor.detach().float().sum())}:{tuple(tensor.shape)}"
            )
    return sha256("|".join(blob).encode("utf-8")).hexdigest().upper()


def _tiny_train(
    model: torch.nn.Module, batch: torch.Tensor, *, steps: int, lr: float
) -> float:
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    last = 0.0
    for _ in range(steps):
        opt.zero_grad(set_to_none=True)
        logits = model(batch[:, :-1])
        loss, _ = model.loss_and_accuracy(logits, batch[:, 1:])
        loss.backward()
        opt.step()
        last = float(loss.detach().cpu())
    model.eval()
    return last


def _ensure_vocab() -> CharacterTokenizer:
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    if VOCAB_MANIFEST.is_file():
        return CharacterTokenizer.from_manifest(VOCAB_MANIFEST)
    tok = CharacterTokenizer.from_texts(IDENTITY_CORPUS)
    manifest = tok.manifest()
    manifest.update(
        {
            "status": "COMPLETE",
            "purpose": "sandbox_shared_identity_vocab",
            "sandbox_only": True,
            "originals_untouched": True,
            "source_texts": list(IDENTITY_CORPUS),
        }
    )
    with VOCAB_MANIFEST.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return tok


def _build_batch(tok: CharacterTokenizer) -> torch.Tensor:
    text = tok.encode(IDENTITY_CORPUS[0])
    while len(text) < TINY_CFG["context_length"] + 1:
        text = text + text
    return torch.tensor(
        [text[: TINY_CFG["context_length"] + 1]], dtype=torch.long
    )


def _save_specialist(
    *,
    path: Path,
    model: TransformerLanguageModel,
    tok: CharacterTokenizer,
    train_meta: dict,
    loss: float,
) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
    fp = _fingerprint(state)
    payload = {
        "schema_version": SCHEMA_CKPT,
        "sandbox_only": True,
        "originals_untouched": True,
        "lane": train_meta["label"],
        "vocab_size": tok.vocab_size,
        "vocab_sha256": tok.vocab_sha256,
        "vocab_manifest": str(VOCAB_MANIFEST).replace("\\", "/"),
        "config": {
            "vocab_size": tok.vocab_size,
            **{k: v for k, v in TINY_CFG.items()},
            **model.plant_config(),
        },
        "train": {
            "seed": train_meta["seed"],
            "steps": train_meta["steps"],
            "learning_rate": train_meta["lr"],
            "final_loss": loss,
            "device": "cpu",
        },
        "weight_fingerprint": fp,
        "model_state_dict": state,
    }
    torch.save(payload, path)
    return {
        "path": str(path).replace("\\", "/"),
        "lane": train_meta["label"],
        "weight_fingerprint": fp,
        "vocab_size": tok.vocab_size,
        "vocab_sha256": tok.vocab_sha256,
        "steps": train_meta["steps"],
        "final_loss": loss,
        "bytes": path.stat().st_size,
    }


def main() -> int:
    assert SANDBOX.name == "test_training"
    assert str(CHECKPOINTS_DIR).replace("\\", "/").endswith(
        "model/test_training/checkpoints"
    ) or "test_training" in str(CHECKPOINTS_DIR)

    tok = _ensure_vocab()
    batch = _build_batch(tok)
    cfg = dict(vocab_size=tok.vocab_size, **TINY_CFG)

    torch.manual_seed(int(EFFICIENT_TRAIN["seed"]))
    efficient = TransformerLanguageModel(**cfg)
    loss_e = _tiny_train(
        efficient,
        batch,
        steps=int(EFFICIENT_TRAIN["steps"]),
        lr=float(EFFICIENT_TRAIN["lr"]),
    )
    meta_e = _save_specialist(
        path=EFFICIENT_CKPT,
        model=efficient,
        tok=tok,
        train_meta=EFFICIENT_TRAIN,
        loss=loss_e,
    )

    torch.manual_seed(int(DEEP_TRAIN["seed"]))
    deep = TransformerLanguageModel(**cfg)
    loss_d = _tiny_train(
        deep,
        batch,
        steps=int(DEEP_TRAIN["steps"]),
        lr=float(DEEP_TRAIN["lr"]),
    )
    meta_d = _save_specialist(
        path=DEEP_CKPT,
        model=deep,
        tok=tok,
        train_meta=DEEP_TRAIN,
        loss=loss_d,
    )

    distinct = meta_e["weight_fingerprint"] != meta_d["weight_fingerprint"]
    same_vocab = meta_e["vocab_sha256"] == meta_d["vocab_sha256"]
    status = "PASS" if distinct and same_vocab else "FAIL"

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run = {
        "schema_version": "viv_slm_sandbox_mint_run_v1",
        "sandbox_only": True,
        "originals_untouched": True,
        "status": status,
        "source": "freshly_minted_no_live_checkpoints_found",
        "vocab_manifest": str(VOCAB_MANIFEST).replace("\\", "/"),
        "efficient": meta_e,
        "deep": meta_d,
        "gates": {
            "fingerprints_distinct": distinct,
            "vocab_shared": same_vocab,
            "checkpoints_under_sandbox": True,
        },
    }
    run_path = RUNS_DIR / "mint_specialists_latest.json"
    with run_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(run, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    print(
        f"VIV_SANDBOX_MINT_{status} "
        f"distinct={distinct} vocab_shared={same_vocab} "
        f"efficient={meta_e['path']} deep={meta_d['path']}"
    )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
