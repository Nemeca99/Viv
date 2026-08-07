#!/usr/bin/env python3
"""Run aggressive weighted-loss sweep and keep best checkpoints."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import torch

SANDBOX = Path(__file__).resolve().parents[1]  # legacy home: parents[1] = test_training/
MODEL = SANDBOX.parent
PY = Path(r"L:\Continue\.venv\Scripts\python.exe")
EFF_CKPT = SANDBOX / "checkpoints" / "efficient" / "specialist.pt"
DEEP_CKPT = SANDBOX / "checkpoints" / "deep" / "specialist.pt"
RUNS = SANDBOX / "runs"
STAMP = "wild_weighted_sweep"

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
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402


def _run(cmd: list[str]) -> None:
    print("RUN", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=str(MODEL))


def _eval_checkpoint(path: Path) -> dict[str, float]:
    configure_plant_runtime(device="cuda")
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    _, vocab_path, tensor_dir = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    val_in, val_tg, val_mask = load_split(
        tensor_dir, "validation", vocab_size=tok.vocab_size, response_only_loss=True
    )
    payload = torch.load(path, map_location="cpu", weights_only=False)
    model = TransformerLanguageModel(tok.vocab_size, **IDENTITY_MODEL_CFG).to(device)
    model.load_state_dict(payload["model_state_dict"], strict=False)
    model.eval()
    val = evaluate_split(model, val_in, val_tg, device=device, batch_size=64, loss_masks=val_mask)
    return {"nll": float(val["nll"]), "acc": float(val["token_accuracy"])}


def _score_pair(eff: dict[str, float], deep: dict[str, float]) -> float:
    # Lower is better. Hard penalty if accuracy floor missed.
    penalty = 0.0
    if eff["acc"] < 0.961:
        penalty += 10.0
    if deep["acc"] < 0.961:
        penalty += 10.0
    return (eff["nll"] + deep["nll"]) + penalty


def main() -> int:
    start_step = int(torch.load(EFF_CKPT, map_location="cpu", weights_only=False)["train"]["steps_completed"])
    target_steps = start_step + 250
    backup_dir = RUNS / STAMP
    backup_dir.mkdir(parents=True, exist_ok=True)
    eff_base = backup_dir / "efficient_base.pt"
    deep_base = backup_dir / "deep_base.pt"
    shutil.copy2(EFF_CKPT, eff_base)
    shutil.copy2(DEEP_CKPT, deep_base)

    configs: list[dict[str, Any]] = [
        {
            "id": "A_weighted_kl015",
            "args": [
                "--training-phase", "teacher",
                "--loss-weighting", "teacher_confidence",
                "--learning-rate", "7e-6",
                "--anchor-weight", "0.15",
                "--weight-min", "0.15",
                "--weight-max", "1.85",
                "--boilerplate-scale", "0.25",
            ],
        },
        {
            "id": "B_weighted_kl025_wilder",
            "args": [
                "--training-phase", "teacher",
                "--loss-weighting", "teacher_confidence",
                "--learning-rate", "8e-6",
                "--anchor-weight", "0.25",
                "--weight-min", "0.10",
                "--weight-max", "2.20",
                "--boilerplate-scale", "0.15",
            ],
        },
        {
            "id": "C_weighted_noKL",
            "args": [
                "--training-phase", "default",
                "--loss-weighting", "teacher_confidence",
                "--learning-rate", "7e-6",
                "--weight-min", "0.20",
                "--weight-max", "1.90",
                "--boilerplate-scale", "0.20",
            ],
        },
    ]

    results: list[dict[str, Any]] = []
    for cfg in configs:
        shutil.copy2(eff_base, EFF_CKPT)
        shutil.copy2(deep_base, DEEP_CKPT)
        for lane, ckpt in (("efficient", EFF_CKPT), ("deep", DEEP_CKPT)):
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
                *cfg["args"],
            ]
            _run(cmd)

        eff_m = _eval_checkpoint(EFF_CKPT)
        deep_m = _eval_checkpoint(DEEP_CKPT)
        score = _score_pair(eff_m, deep_m)
        eff_out = backup_dir / f"{cfg['id']}_efficient.pt"
        deep_out = backup_dir / f"{cfg['id']}_deep.pt"
        shutil.copy2(EFF_CKPT, eff_out)
        shutil.copy2(DEEP_CKPT, deep_out)
        results.append(
            {
                "id": cfg["id"],
                "target_steps": target_steps,
                "efficient": eff_m,
                "deep": deep_m,
                "score": score,
                "paths": {"efficient": str(eff_out), "deep": str(deep_out)},
            }
        )
        print(
            f"SWEEP_RESULT {cfg['id']} "
            f"eff_nll={eff_m['nll']:.4f} eff_acc={eff_m['acc']:.4f} "
            f"deep_nll={deep_m['nll']:.4f} deep_acc={deep_m['acc']:.4f} "
            f"score={score:.4f}",
            flush=True,
        )

    best = min(results, key=lambda x: float(x["score"]))
    shutil.copy2(Path(best["paths"]["efficient"]), EFF_CKPT)
    shutil.copy2(Path(best["paths"]["deep"]), DEEP_CKPT)

    summary = {
        "status": "PASS",
        "start_step": start_step,
        "target_step": target_steps,
        "winner": best["id"],
        "results": results,
    }
    out = RUNS / "wild_weighted_sweep_latest.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        f"SWEEP_WINNER {best['id']} "
        f"eff_nll={best['efficient']['nll']:.4f} eff_acc={best['efficient']['acc']:.4f} "
        f"deep_nll={best['deep']['nll']:.4f} deep_acc={best['deep']['acc']:.4f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
