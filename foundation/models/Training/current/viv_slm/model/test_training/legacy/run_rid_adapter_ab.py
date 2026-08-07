#!/usr/bin/env python3
"""A/B compare baseline vs RID adapter fine-tune on sandbox checkpoints."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import torch

SANDBOX = Path(__file__).resolve().parents[1]  # legacy home: parents[1] = test_training/
MODEL = SANDBOX.parent
PY = Path(r"L:\Continue\.venv\Scripts\python.exe")
EFF = SANDBOX / "checkpoints" / "efficient" / "specialist.pt"
DEEP = SANDBOX / "checkpoints" / "deep" / "specialist.pt"
OUT = SANDBOX / "runs" / "rid_adapter_ab_latest.json"


def _run(cmd: list[str]) -> None:
    print("RUN", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=str(MODEL))


def _metrics(path: Path, *, rid: bool) -> dict[str, float]:
    import sys

    if str(MODEL) not in sys.path:
        sys.path.insert(0, str(MODEL))
    if str(SANDBOX) not in sys.path:
        sys.path.insert(0, str(SANDBOX))
    from sandbox_codex_identity import IDENTITY_MODEL_CFG, evaluate_split, load_split, resolve_codex_dataset
    from tokenizer import CharacterTokenizer
    from transformer import TransformerLanguageModel

    payload = torch.load(path, map_location="cpu", weights_only=False)
    _, vocab_path, tensor_dir = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    val_in, val_tg, val_mask = load_split(tensor_dir, "validation", vocab_size=tok.vocab_size, response_only_loss=True)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model = TransformerLanguageModel(
        tok.vocab_size,
        **IDENTITY_MODEL_CFG,
        rid_adapter=rid,
        rid_rank=8,
        rid_alpha=16.0,
        rid_dropout=0.05,
    ).to(device)
    model.load_state_dict(payload["model_state_dict"], strict=False)
    if rid:
        model.set_rid_metrics(rid_residual=0.7, uml_nesting=5.0, uml_math=4.0)
    model.eval()
    m = evaluate_split(model, val_in, val_tg, device=device, batch_size=64, loss_masks=val_mask)
    return {"nll": float(m["nll"]), "acc": float(m["token_accuracy"]), "ppl": float(m["perplexity"])}


def main() -> int:
    backup_dir = SANDBOX / "runs" / "rid_adapter_ab"
    backup_dir.mkdir(parents=True, exist_ok=True)
    eff_backup = backup_dir / "efficient_pre_ab.pt"
    deep_backup = backup_dir / "deep_pre_ab.pt"
    shutil.copy2(EFF, eff_backup)
    shutil.copy2(DEEP, deep_backup)
    try:
        baseline = {
            "efficient": _metrics(EFF, rid=False),
            "deep": _metrics(DEEP, rid=False),
        }
        start_steps = int(torch.load(EFF, map_location="cpu", weights_only=False)["train"]["steps_completed"])
        target_steps = start_steps + 250
        for lane, ckpt in (("efficient", EFF), ("deep", DEEP)):
            cmd = [
                str(PY),
                "-B",
                str(SANDBOX / "train_specialist.py"),
                "--lane",
                lane,
                "--codex-identity",
                "v61",
                "--device",
                "cuda",
                "--resume",
                str(ckpt),
                "--steps",
                str(target_steps),
                "--training-phase",
                "default",
                "--learning-rate",
                "7e-6",
                "--rid-adapter",
                "--rid-rank",
                "8",
                "--rid-alpha",
                "16",
                "--rid-dropout",
                "0.05",
                "--rid-adapter-only",
                "--rid-residual",
                "0.7",
                "--uml-nesting",
                "5",
                "--uml-math",
                "4",
            ]
            _run(cmd)
        adapted = {
            "efficient": _metrics(EFF, rid=True),
            "deep": _metrics(DEEP, rid=True),
        }
        summary: dict[str, Any] = {
            "status": "PASS",
            "start_steps": start_steps,
            "target_steps": target_steps,
            "baseline": baseline,
            "adapted": adapted,
            "delta": {
                "efficient": {
                    "nll": adapted["efficient"]["nll"] - baseline["efficient"]["nll"],
                    "acc": adapted["efficient"]["acc"] - baseline["efficient"]["acc"],
                },
                "deep": {
                    "nll": adapted["deep"]["nll"] - baseline["deep"]["nll"],
                    "acc": adapted["deep"]["acc"] - baseline["deep"]["acc"],
                },
            },
        }
        OUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(
            "RID_ADAPTER_AB",
            f"eff_nll {baseline['efficient']['nll']:.4f}->{adapted['efficient']['nll']:.4f}",
            f"deep_nll {baseline['deep']['nll']:.4f}->{adapted['deep']['nll']:.4f}",
            flush=True,
        )
    finally:
        shutil.copy2(eff_backup, EFF)
        shutil.copy2(deep_backup, DEEP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
