#!/usr/bin/env python3
"""Resume both specialists in 250-step increments until val progress slows."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
PY = Path(r"L:\Continue\.venv\Scripts\python.exe")
INCREMENT = 250
PLATEAU_PPL_GAIN = 0.35  # stop when BOTH lanes improve less than this in one increment
MIN_EXTRA_INCREMENTS = 2  # always run at least this many after launch
MAX_TOTAL_STEPS = 3000


def _read_metrics(lane: str) -> dict:
    path = SANDBOX / "runs" / lane / "train_latest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    history = data.get("checkpoint") or {}
    # Prefer last history entry from saved checkpoint payload via train manifest
    run = json.loads(path.read_text(encoding="utf-8"))
    steps = int(run.get("steps_completed") or 0)
    # Parse last eval from train script output file - read checkpoint directly
    ckpt = SANDBOX / "checkpoints" / lane / "specialist.pt"
    import torch

    payload = torch.load(ckpt, map_location="cpu", weights_only=False)
    hist = payload.get("training_history") or []
    last = hist[-1] if hist else {}
    val = last.get("validation") or {}
    return {
        "steps": int((payload.get("train") or {}).get("steps_completed") or steps),
        "val_ppl": float(val.get("perplexity") or 999.0),
        "val_acc": float(val.get("token_accuracy") or 0.0),
    }


def _run_train(lane: str, target_steps: int) -> None:
    ckpt = SANDBOX / "checkpoints" / lane / "specialist.pt"
    cmd = [
        str(PY),
        "-B",
        str(SANDBOX / "train_specialist.py"),
        "--lane",
        lane,
        "--codex-identity",
        "v43",
        "--device",
        "cuda",
        "--resume",
        str(ckpt),
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
    args = parser.parse_args()

    import train_specialist  # noqa: F401 — ensure importable

    baseline = {lane: _read_metrics(lane) for lane in ("efficient", "deep")}
    start_steps = baseline["efficient"]["steps"]
    if baseline["deep"]["steps"] != start_steps:
        raise RuntimeError("lane_step_mismatch")
    print(
        f"PLATEAU_RUN start_steps={start_steps} "
        f"eff_ppl={baseline['efficient']['val_ppl']:.2f} "
        f"deep_ppl={baseline['deep']['val_ppl']:.2f}",
        flush=True,
    )

    prev = baseline
    increments_done = 0
    log: list[dict] = []
    target = start_steps + args.increment

    while target <= args.max_steps:
        for lane in ("efficient", "deep"):
            _run_train(lane, target)

        cur = {lane: _read_metrics(lane) for lane in ("efficient", "deep")}
        gains = {
            lane: prev[lane]["val_ppl"] - cur[lane]["val_ppl"]
            for lane in ("efficient", "deep")
        }
        entry = {
            "target_steps": target,
            "efficient": cur["efficient"],
            "deep": cur["deep"],
            "ppl_gain": gains,
        }
        log.append(entry)
        print(
            f"INCREMENT steps={target} "
            f"eff_ppl={cur['efficient']['val_ppl']:.2f} gain={gains['efficient']:.2f} "
            f"deep_ppl={cur['deep']['val_ppl']:.2f} gain={gains['deep']:.2f}",
            flush=True,
        )
        increments_done += 1
        prev = cur

        if increments_done >= args.min_extra and all(
            g < args.plateau_ppl for g in gains.values()
        ):
            print(
                f"PLATEAU_DETECTED both gains < {args.plateau_ppl} after {increments_done} increments",
                flush=True,
            )
            break
        target += args.increment

    subprocess.run(
        [str(PY), "-B", str(SANDBOX / "run_sandbox_smoke.py")],
        check=True,
        cwd=str(MODEL),
    )

    out = SANDBOX / "runs" / "plateau_run_latest.json"
    summary = {
        "status": "PASS",
        "start_steps": start_steps,
        "final_steps": prev["efficient"]["steps"],
        "increments_run": increments_done,
        "plateau_ppl_threshold": args.plateau_ppl,
        "history": log,
        "final": prev,
    }
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PLATEAU_RUN_PASS final_steps={prev['efficient']['steps']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
