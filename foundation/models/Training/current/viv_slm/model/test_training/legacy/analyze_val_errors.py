#!/usr/bin/env python3
"""Ceiling audit: val response-only error taxonomy vs hybrid/continue parent."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

SANDBOX = Path(__file__).resolve().parents[1]  # legacy home: parents[1] = test_training/
MODEL = SANDBOX.parent
RUNS = SANDBOX / "runs"
CKPT = (
    RUNS / "rid_breakthrough_continue_4450" / "hybrid_continue" / "efficient_final.pt"
)
OUT = RUNS / "acc99_ceiling_audit.json"

import sys

if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))
if str(SANDBOX) not in sys.path:
    sys.path.insert(0, str(SANDBOX))

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import IDENTITY_MODEL_CFG, load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402

BOILERPLATE_CHARS = {"\n", " ", "<", ">", "E", "N", "D"}


def main() -> int:
    configure_plant_runtime(device="cuda")
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    _, vocab_path, tensor_dir = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    val_in, val_tg, val_mask = load_split(
        tensor_dir, "validation", vocab_size=tok.vocab_size, response_only_loss=True
    )
    payload = torch.load(CKPT, map_location="cpu", weights_only=False)
    model = TransformerLanguageModel(
        tok.vocab_size,
        **IDENTITY_MODEL_CFG,
        rid_adapter=True,
        rid_rank=8,
        rid_alpha=16.0,
        rid_dropout=0.05,
    ).to(device)
    model.load_state_dict(payload["model_state_dict"], strict=False)
    model.set_rid_metrics(rid_residual=0.3, uml_nesting=2.0, uml_math=2.0)
    model.eval()

    boilerplate_ids = {int(tok.stoi[c]) for c in BOILERPLATE_CHARS if c in tok.stoi}
    total = 0
    correct = 0
    boiler_total = 0
    boiler_correct = 0
    content_total = 0
    content_correct = 0
    confusions: Counter[str] = Counter()
    tie_errors = 0
    high_entropy_errors = 0

    batch = 64
    n = int(val_in.shape[0])
    with torch.no_grad():
        for start in range(0, n, batch):
            end = min(start + batch, n)
            batch_in = val_in[start:end].to(device)
            batch_tg = val_tg[start:end].to(device)
            batch_mask = val_mask[start:end].to(device).bool()
            logits = model(batch_in)
            pred = logits.argmax(dim=-1)
            probs = torch.softmax(logits.float(), dim=-1)
            top2 = torch.topk(probs, k=2, dim=-1).values
            entropy = -(probs * (probs.clamp_min(1e-12).log())).sum(dim=-1)

            valid = batch_mask
            total += int(valid.sum().item())
            correct += int(((pred == batch_tg) & valid).sum().item())

            for b in range(end - start):
                idxs = valid[b].nonzero(as_tuple=False).flatten()
                for t in idxs.tolist():
                    tgt = int(batch_tg[b, t].item())
                    pr = int(pred[b, t].item())
                    is_boiler = tgt in boilerplate_ids
                    if is_boiler:
                        boiler_total += 1
                        if pr == tgt:
                            boiler_correct += 1
                    else:
                        content_total += 1
                        if pr == tgt:
                            content_correct += 1
                    if pr != tgt:
                        confusions[f"{tok.itos.get(tgt, '?')}->{tok.itos.get(pr, '?')}"] += 1
                        margin = float(top2[b, t, 0] - top2[b, t, 1])
                        if margin < 0.05:
                            tie_errors += 1
                        if float(entropy[b, t]) > 2.5:
                            high_entropy_errors += 1

    acc = correct / max(total, 1)
    boiler_acc = boiler_correct / max(boiler_total, 1)
    content_acc = content_correct / max(content_total, 1)
    err = 1.0 - acc
    # Headroom estimate: errors that look soft (near-ties / high entropy) vs hard.
    soft = tie_errors + high_entropy_errors
    # Avoid double-count roughly by taking max as soft pool proxy.
    soft_proxy = max(tie_errors, high_entropy_errors)
    hard_proxy = max(int(total * err) - soft_proxy, 0)
    headroom_to_99 = max(0.99 - acc, 0.0)
    # If soft_proxy covers most of the remaining gap, training may help; else data ceiling likely.
    remaining_errors = int(round(total * err))
    soft_frac = soft_proxy / max(remaining_errors, 1)

    summary: dict[str, Any] = {
        "status": "PASS",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "checkpoint": str(CKPT).replace("\\", "/"),
        "tokens": {
            "total": total,
            "correct": correct,
            "accuracy": acc,
            "error_rate": err,
        },
        "boilerplate": {
            "total": boiler_total,
            "correct": boiler_correct,
            "accuracy": boiler_acc,
        },
        "content": {
            "total": content_total,
            "correct": content_correct,
            "accuracy": content_acc,
        },
        "error_structure": {
            "tie_like_errors": tie_errors,
            "high_entropy_errors": high_entropy_errors,
            "soft_proxy": soft_proxy,
            "hard_proxy": hard_proxy,
            "soft_fraction_of_errors": soft_frac,
        },
        "top_confusions": confusions.most_common(25),
        "headroom": {
            "target_acc": 0.99,
            "gap_to_99": headroom_to_99,
            "estimate": (
                "TRAINABLE_SOFT_HEADROOM"
                if soft_frac >= 0.35 and headroom_to_99 > 0
                else "LIKELY_DATA_OR_HARD_CEILING"
            ),
            "note": (
                "soft_fraction high => hard-token / longer hybrid may still move acc; "
                "low soft_fraction => expand identity data before claiming 99 is blocked only by train."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"CEILING_AUDIT_PASS acc={acc:.5f} content={content_acc:.5f} "
        f"boiler={boiler_acc:.5f} gap99={headroom_to_99:.5f} est={summary['headroom']['estimate']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
