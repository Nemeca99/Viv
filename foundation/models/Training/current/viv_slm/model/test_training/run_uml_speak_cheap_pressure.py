#!/usr/bin/env python3
"""Targeted speak cheap-pressure train from layer_survivor.

Baseline: current survivor speak cheap_rate (match must hold).
Pilot: short mix train with elevated prefer_cheap_boost, then re-speak.

Primary gate: match_rate == 1.0 (destination seal) + Codex hold.
Secondary: cheap_rate / mean route error among prompts.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
PY = Path(r"L:\Continue\.venv\Scripts\python.exe")
OUT = SANDBOX / "runs" / "uml_speak_cheap_pressure"
SURVIVOR = SANDBOX / "runs" / "uml_mix_layers" / "layer_survivor.pt"
RECIPE = SANDBOX / "uml_mix_recipe.json"

for p in (FOUNDATION, MODEL, SANDBOX):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
import run_uml_equation_ab as ab  # noqa: E402
import run_uml_speak_ab_f as speak  # noqa: E402
from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402
from sandbox_paths import EFFICIENT_CKPT  # noqa: E402


def _speak_one(name: str, ckpt: Path, tok, reg, device) -> dict[str, Any]:
    model_e = speak._load(EFFICIENT_CKPT, tok, torch.device("cpu"))
    return speak._eval_ckpt(
        name=name, deep_path=ckpt, model_e=model_e, tok=tok, reg=reg, device=device
    )


def main() -> int:
    recipe = ab.load_mix_recipe(RECIPE)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=3000)
    parser.add_argument("--mix-ratio", type=float, default=float(recipe.get("mix_ratio", 0.779375)))
    parser.add_argument("--prefer-cheap-boost", type=float, default=3.0)
    parser.add_argument("--warm", type=Path, default=SURVIVOR)
    parser.add_argument("--batch-size", type=int, default=int(recipe.get("batch_size", 64)))
    parser.add_argument("--lr", type=float, default=float(recipe.get("lr", 7e-6)))
    parser.add_argument("--seed", type=int, default=int(recipe.get("seed", 42)) + 11)
    parser.add_argument("--log-every", type=int, default=500)
    parser.add_argument("--codex-hold-tol", type=float, default=0.001)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--commit-survivor", action="store_true")
    args = parser.parse_args()

    if not args.warm.is_file():
        raise FileNotFoundError(args.warm)
    OUT.mkdir(parents=True, exist_ok=True)

    uml_tensor = ab._ensure_mix_dataset()
    _, vocab_path, codex_tensor = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    if str(device).startswith("cuda") and not torch.cuda.is_available():
        device = torch.device("cpu")
    configure_plant_runtime(device=str(device))

    codex_train = load_split(codex_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True)
    codex_val = load_split(codex_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True)
    uml_train = load_split(uml_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True)
    uml_val = load_split(uml_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True)

    baseline_speak = _speak_one("baseline_survivor", args.warm, tok, reg, device)
    start_metrics = ab._metrics(
        args.warm, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
    )
    print(
        f"SPEAK_CHEAP_BASELINE match={baseline_speak['match_rate']:.3f} "
        f"cheap={baseline_speak['cheap_rate']:.3f} "
        f"err={baseline_speak['mean_route_error']:.3f}",
        flush=True,
    )

    warm = OUT / "warm_speak_cheap.pt"
    shutil.copy2(args.warm, warm)
    ckpt = ab._train_leg(
        name="speak_cheap_pressure",
        warm_ckpt=warm,
        steps=int(args.steps),
        batch_size=int(args.batch_size),
        lr=float(args.lr),
        mix_ratio=float(args.mix_ratio),
        device=device,
        tok=tok,
        codex_train=codex_train,
        uml_train=uml_train,
        seed=int(args.seed),
        log_every=int(args.log_every),
        prefer_cheap_boost=float(args.prefer_cheap_boost),
        rid_residual_weight=0.0,
        thermal_route_weight=0.0,
        plant_sn_gate=False,
        out_dir=OUT,
    )
    after_metrics = ab._metrics(
        ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
    )
    pilot_speak = _speak_one("pilot_boost3", ckpt, tok, reg, device)

    d_codex = after_metrics["codex_acc"] - start_metrics["codex_acc"]
    d_uml = after_metrics["uml_acc"] - start_metrics["uml_acc"]
    d_cheap = pilot_speak["cheap_rate"] - baseline_speak["cheap_rate"]
    hold = d_codex >= -float(args.codex_hold_tol)
    match_ok = (
        float(baseline_speak["match_rate"]) >= 1.0 - 1e-9
        and float(pilot_speak["match_rate"]) >= 1.0 - 1e-9
    )

    if not hold or not match_ok:
        objective = "FAIL_HOLD_OR_MATCH"
    elif d_cheap > 0.05:
        objective = "PASS_CHEAP_UP"
    elif abs(d_cheap) <= 0.05 and hold:
        objective = "TIE_NO_CHEAP_LIFT"
    else:
        objective = "FAIL_CHEAP_DOWN"

    if args.commit_survivor and objective == "PASS_CHEAP_UP" and hold and match_ok:
        shutil.copy2(ckpt, SURVIVOR)

    receipt = {
        "schema_version": "uml_speak_cheap_pressure_v1",
        "experiment_id": "uml_speak_cheap_pressure_v1",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "objective": objective,
        "hypothesis": (
            "Elevated prefer_cheap_boost on a short mix leg raises speak cheap_rate "
            "while holding match_rate=1.0 and Codex."
        ),
        "config": {
            "steps": int(args.steps),
            "mix_ratio": float(args.mix_ratio),
            "prefer_cheap_boost": float(args.prefer_cheap_boost),
            "warm": str(args.warm).replace("\\", "/"),
            "n_speak_prompts": 7,
        },
        "codex_hold": hold,
        "match_ok": match_ok,
        "baseline": {
            "metrics": start_metrics,
            "speak": {k: baseline_speak[k] for k in ("match_rate", "cheap_rate", "mean_route_error", "valid_rate", "dirty_rate")},
        },
        "pilot": {
            "metrics": after_metrics,
            "speak": {k: pilot_speak[k] for k in ("match_rate", "cheap_rate", "mean_route_error", "valid_rate", "dirty_rate")},
        },
        "delta": {
            "codex_acc": d_codex,
            "uml_acc": d_uml,
            "cheap_rate": d_cheap,
            "mean_route_error": pilot_speak["mean_route_error"] - baseline_speak["mean_route_error"],
        },
        "artifacts": {
            "ckpt": str(ckpt).replace("\\", "/"),
            "survivor_committed": bool(args.commit_survivor and objective == "PASS_CHEAP_UP"),
        },
        "audit_note": (
            "Org audit PASS_WITH_NOTES: legacy moves+shims+mint --execute OK; "
            "layer_survivor intact; EFF vocab=96 (hash differs from ADS warm_start metadata size)."
        ),
    }
    out_json = OUT / "speak_cheap_pressure_latest.json"
    latest = SANDBOX / "runs" / "uml_speak_cheap_pressure_latest.json"
    text = json.dumps(receipt, indent=2, sort_keys=True)
    out_json.write_text(text + "\n", encoding="utf-8")
    latest.write_text(text + "\n", encoding="utf-8")
    print(
        f"SPEAK_CHEAP_{objective} hold={hold} match_ok={match_ok} "
        f"cheap {baseline_speak['cheap_rate']:.3f}->{pilot_speak['cheap_rate']:.3f} "
        f"d={d_cheap:+.3f} codex_d={d_codex:+.4f}",
        flush=True,
    )
    return 0 if objective != "FAIL_HOLD_OR_MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
