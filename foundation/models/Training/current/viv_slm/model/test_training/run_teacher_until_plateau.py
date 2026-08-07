#!/usr/bin/env python3
"""Resume both specialists in teacher-anchor increments until val progress stalls."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import torch

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
PY = Path(r"L:\Continue\.venv\Scripts\python.exe")
INCREMENT = 250
# Near Codex target: gains are ~0.001–0.005 ppl per 250 steps.
PLATEAU_PPL_GAIN = 0.001
MIN_EXTRA_INCREMENTS = 1
MAX_TOTAL_STEPS = 3500


def _read_metrics(lane: str) -> dict[str, float | int]:
    ckpt = SANDBOX / "checkpoints" / lane / "specialist.pt"
    payload = torch.load(ckpt, map_location="cpu", weights_only=False)
    hist = payload.get("training_history") or []
    last = hist[-1] if hist else {}
    val = last.get("validation") or {}
    teacher = last.get("validation_teacher_kl") or {}
    return {
        "steps": int((payload.get("train") or {}).get("steps_completed") or 0),
        "val_nll": float(val.get("nll") or 999.0),
        "val_ppl": float(val.get("perplexity") or 999.0),
        "val_acc": float(val.get("token_accuracy") or 0.0),
        "val_teacher_kl": float(teacher.get("teacher_kl") or 0.0),
    }


def _run_train(lane: str, target_steps: int, *, dataset: str) -> None:
    ckpt = SANDBOX / "checkpoints" / lane / "specialist.pt"
    cmd = [
        str(PY),
        "-B",
        str(SANDBOX / "train_specialist.py"),
        "--lane",
        lane,
        "--codex-identity",
        dataset,
        "--device",
        "cuda",
        "--resume",
        str(ckpt),
        "--training-phase",
        "teacher",
        "--steps",
        str(target_steps),
    ]
    print(f"RUN {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, cwd=str(MODEL))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--increment", type=int, default=INCREMENT)
    parser.add_argument("--plateau-ppl", type=float, default=PLATEAU_PPL_GAIN)
    parser.add_argument("--min-extra", type=int, default=MIN_EXTRA_INCREMENTS)
    parser.add_argument("--max-steps", type=int, default=MAX_TOTAL_STEPS)
    parser.add_argument("--dataset", default="v61")
    args = parser.parse_args()

    baseline = {lane: _read_metrics(lane) for lane in ("efficient", "deep")}
    start_steps = baseline["efficient"]["steps"]
    if baseline["deep"]["steps"] != start_steps:
        raise RuntimeError("lane_step_mismatch")

    print(
        f"TEACHER_PLATEAU start_steps={start_steps} "
        f"eff_nll={baseline['efficient']['val_nll']:.4f} acc={baseline['efficient']['val_acc']:.4f} "
        f"deep_nll={baseline['deep']['val_nll']:.4f} acc={baseline['deep']['val_acc']:.4f}",
        flush=True,
    )

    prev = baseline
    increments_done = 0
    log: list[dict[str, Any]] = []
    target = start_steps + args.increment

    while target <= args.max_steps:
        for lane in ("efficient", "deep"):
            _run_train(lane, target, dataset=str(args.dataset))

        cur = {lane: _read_metrics(lane) for lane in ("efficient", "deep")}
        ppl_gains = {
            lane: prev[lane]["val_ppl"] - cur[lane]["val_ppl"]
            for lane in ("efficient", "deep")
        }
        nll_gains = {
            lane: prev[lane]["val_nll"] - cur[lane]["val_nll"]
            for lane in ("efficient", "deep")
        }
        entry = {
            "target_steps": target,
            "efficient": cur["efficient"],
            "deep": cur["deep"],
            "ppl_gain": ppl_gains,
            "nll_gain": nll_gains,
        }
        log.append(entry)
        print(
            f"INCREMENT steps={target} "
            f"eff_nll={cur['efficient']['val_nll']:.4f} gain={nll_gains['efficient']:.5f} "
            f"deep_nll={cur['deep']['val_nll']:.4f} gain={nll_gains['deep']:.5f} "
            f"eff_acc={cur['efficient']['val_acc']:.4f} deep_acc={cur['deep']['val_acc']:.4f}",
            flush=True,
        )
        increments_done += 1
        prev = cur

        if increments_done >= args.min_extra and all(
            g < args.plateau_ppl for g in ppl_gains.values()
        ):
            print(
                f"PLATEAU_DETECTED both ppl gains < {args.plateau_ppl} "
                f"after {increments_done} increments",
                flush=True,
            )
            break
        target += args.increment

    subprocess.run(
        [str(PY), "-B", str(SANDBOX / "eval_sandbox_checkpoints.py")],
        check=True,
        cwd=str(MODEL),
    )
    subprocess.run(
        [str(PY), "-B", str(SANDBOX / "run_sandbox_smoke.py")],
        check=True,
        cwd=str(MODEL),
    )

    out = SANDBOX / "runs" / "teacher_plateau_run_latest.json"
    summary = {
        "status": "PASS",
        "training_phase": "teacher",
        "dataset": str(args.dataset),
        "start_steps": start_steps,
        "final_steps": prev["efficient"]["steps"],
        "increments_run": increments_done,
        "plateau_ppl_threshold": args.plateau_ppl,
        "codex_target": {"val_nll": 0.130, "val_acc": 0.961},
        "history": log,
        "final": prev,
    }
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"TEACHER_PLATEAU_PASS final_steps={prev['efficient']['steps']} "
        f"eff_nll={prev['efficient']['val_nll']:.4f} deep_nll={prev['deep']['val_nll']:.4f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
