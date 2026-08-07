#!/usr/bin/env python3
"""Matched A/B: thermal_route_weight 0 vs 1.0 (same seed/steps/bank/boost).

Hypothesis
----------
Among sealed UML routes, upweighting thermal-best teacher rows improves UML
response metrics vs boost-only, without breaking Codex hold.

Design
------
- One warm-start copy from efficient specialist.
- Two matched pilot legs (identical except thermal_route_weight).
- No Codex-only baseline leg (that knob is already proven elsewhere).
- Primary compare: pilot_w1 − pilot_w0 on UML acc/nll; Codex hold vs start.
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
EFF = SANDBOX / "checkpoints" / "efficient" / "specialist.pt"
OUT_DIR = SANDBOX / "runs" / "uml_thermal_weight_ab"
RECEIPT_JSON = SANDBOX / "runs" / "uml_thermal_weight_ab_latest.json"
RECEIPT_MD = SANDBOX / "runs" / "uml_thermal_weight_ab_latest.md"
RECIPE_PATH = SANDBOX / "uml_mix_recipe.json"

for p in (MODEL, SANDBOX, FOUNDATION):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

import run_uml_equation_ab as ab  # noqa: E402


def _verdict(delta_uml_acc: float, delta_uml_nll: float, *, min_acc: float = 0.005, min_nll: float = 0.02) -> str:
    """Causal claim on thermal weight only (pilot1 − pilot0)."""
    if delta_uml_acc >= min_acc and delta_uml_nll <= -min_nll:
        return "THERMAL_WIN"
    if delta_uml_acc <= -min_acc and delta_uml_nll >= min_nll:
        return "THERMAL_REGRESS"
    if abs(delta_uml_acc) < min_acc and abs(delta_uml_nll) < min_nll:
        return "THERMAL_TIE"
    return "INCONCLUSIVE"


def main() -> int:
    recipe = ab.load_mix_recipe(RECIPE_PATH)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=int(recipe.get("steps_default", 10000)))
    parser.add_argument("--batch-size", type=int, default=int(recipe.get("batch_size", 64)))
    parser.add_argument("--lr", type=float, default=float(recipe.get("lr", 7e-6)))
    parser.add_argument("--mix-ratio", type=float, default=float(recipe.get("mix_ratio", 0.15)))
    parser.add_argument(
        "--prefer-cheap-boost",
        type=float,
        default=float(recipe.get("prefer_cheap_boost", 2.0)),
    )
    parser.add_argument("--seed", type=int, default=int(recipe.get("seed", 42)))
    parser.add_argument("--log-every", type=int, default=int(recipe.get("log_every", 500)))
    parser.add_argument("--weight-control", type=float, default=0.0)
    parser.add_argument("--weight-pilot", type=float, default=1.0)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    if not EFF.is_file():
        raise FileNotFoundError(f"thermal_ab_missing_warm:{EFF}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Preserve prior operator thermal=1 full A/B if present.
    prior = SANDBOX / "runs" / "uml_equation_ab_v2_latest.json"
    if prior.is_file():
        shutil.copy2(prior, OUT_DIR / "prior_uml_equation_ab_v2_latest.json")

    uml_tensor = ab._ensure_mix_dataset()
    mix_build = json.loads(
        (SANDBOX / "data" / "uml_equation_mix_v1" / "BUILD.json").read_text(encoding="utf-8")
    )
    _, vocab_path, codex_tensor = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)

    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    if str(device).startswith("cuda") and not torch.cuda.is_available():
        device = torch.device("cpu")
    configure_plant_runtime(device=str(device))

    codex_train = load_split(codex_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True)
    codex_val = load_split(codex_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True)
    uml_train = load_split(uml_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True)
    uml_val = load_split(uml_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True)

    warm = OUT_DIR / "warm_start.pt"
    shutil.copy2(EFF, warm)
    start_metrics = ab._metrics(
        warm, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
    )
    start_step = int(torch.load(warm, map_location="cpu", weights_only=False)["train"]["steps_completed"])
    pilot_seed = int(args.seed) + 1  # match run_uml_equation_ab pilot seed offset

    common = dict(
        warm_ckpt=warm,
        steps=int(args.steps),
        batch_size=int(args.batch_size),
        lr=float(args.lr),
        mix_ratio=float(args.mix_ratio),
        device=device,
        tok=tok,
        codex_train=codex_train,
        uml_train=uml_train,
        seed=pilot_seed,
        log_every=int(args.log_every),
        prefer_cheap_boost=float(args.prefer_cheap_boost),
        rid_residual_weight=0.0,
        out_dir=OUT_DIR,
    )

    print(
        f"THERMAL_AB start steps={start_step}+{args.steps} "
        f"w0={args.weight_control} w1={args.weight_pilot} seed={pilot_seed}",
        flush=True,
    )
    ckpt0 = ab._train_leg(
        name="pilot_thermal_w0",
        thermal_route_weight=float(args.weight_control),
        **common,
    )
    ckpt1 = ab._train_leg(
        name="pilot_thermal_w1",
        thermal_route_weight=float(args.weight_pilot),
        **common,
    )

    m0 = ab._metrics(ckpt0, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size)
    m1 = ab._metrics(ckpt1, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size)

    delta = {
        "codex_acc": m1["codex_acc"] - m0["codex_acc"],
        "codex_nll": m1["codex_nll"] - m0["codex_nll"],
        "uml_acc": m1["uml_acc"] - m0["uml_acc"],
        "uml_nll": m1["uml_nll"] - m0["uml_nll"],
    }
    hold0 = ab._codex_hold(m0["codex_acc"] - start_metrics["codex_acc"])
    hold1 = ab._codex_hold(m1["codex_acc"] - start_metrics["codex_acc"])
    verdict = _verdict(delta["uml_acc"], delta["uml_nll"])
    both_hold = hold0 and hold1
    if not both_hold:
        objective = "FAIL_HOLD"
    elif verdict == "THERMAL_WIN":
        objective = "PASS"
    elif verdict == "THERMAL_TIE":
        objective = "TIE"
    elif verdict == "THERMAL_REGRESS":
        objective = "REGRESS"
    else:
        objective = "INCONCLUSIVE"

    payload0 = torch.load(ckpt0, map_location="cpu", weights_only=False)
    payload1 = torch.load(ckpt1, map_location="cpu", weights_only=False)

    receipt: dict[str, Any] = {
        "schema_version": "uml_thermal_weight_ab_v1",
        "status": "PASS",
        "objective": objective,
        "verdict_thermal": verdict,
        "hypothesis": (
            "Matched pilots (same seed/steps/bank/boost); only thermal_route_weight differs. "
            "Thermal weight improves UML vs boost-only without Codex hold break."
        ),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "sandbox_only": True,
        "matched": {
            "steps": int(args.steps),
            "start_steps": start_step,
            "batch_size": int(args.batch_size),
            "lr": float(args.lr),
            "mix_ratio": float(args.mix_ratio),
            "prefer_cheap_boost": float(args.prefer_cheap_boost),
            "rid_residual_weight": 0.0,
            "pilot_seed": pilot_seed,
            "bank_version": mix_build.get("bank_version"),
            "bank_dialogues": mix_build.get("dialogue_rows"),
        },
        "weights": {
            "control": float(args.weight_control),
            "pilot": float(args.weight_pilot),
        },
        "codex_hold_control": hold0,
        "codex_hold_pilot": hold1,
        "start": start_metrics,
        "control_thermal_0": m0,
        "pilot_thermal_1": m1,
        "delta_pilot_minus_control": delta,
        "train_receipts": {
            "control_thermal_scored_batches": int(payload0.get("thermal_scored_batches") or 0),
            "pilot_thermal_scored_batches": int(payload1.get("thermal_scored_batches") or 0),
            "control_prefer_hits": int(payload0.get("prefer_hits") or 0),
            "pilot_prefer_hits": int(payload1.get("prefer_hits") or 0),
        },
        "thresholds": {"min_uml_acc_delta": 0.005, "min_uml_nll_delta": 0.02},
        "artifacts": {
            "warm": str(warm).replace("\\", "/"),
            "control": str(ckpt0).replace("\\", "/"),
            "pilot": str(ckpt1).replace("\\", "/"),
        },
        "device": str(device),
    }
    with RECEIPT_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    stamped = OUT_DIR / f"receipt_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    shutil.copy2(RECEIPT_JSON, stamped)

    md = "\n".join(
        [
            "# UML Thermal Route Weight A/B",
            "",
            f"- Objective: **{objective}**",
            f"- Thermal verdict: **{verdict}**",
            f"- Steps: {start_step} + {args.steps} (matched pilots)",
            f"- Weights: control={args.weight_control} vs pilot={args.weight_pilot}",
            f"- Prefer-cheap boost: {args.prefer_cheap_boost}",
            f"- Bank: {mix_build.get('bank_version')}",
            "",
            "## Codex (hold vs start)",
            f"- Start   acc={start_metrics['codex_acc']:.6f}",
            f"- Control acc={m0['codex_acc']:.6f} hold={hold0}",
            f"- Pilot   acc={m1['codex_acc']:.6f} hold={hold1}",
            f"- Delta (p−c) acc={delta['codex_acc']:+.6f} nll={delta['codex_nll']:+.6f}",
            "",
            "## UML response (primary thermal compare)",
            f"- Control acc={m0['uml_acc']:.6f} nll={m0['uml_nll']:.6f}",
            f"- Pilot   acc={m1['uml_acc']:.6f} nll={m1['uml_nll']:.6f}",
            f"- Delta   acc={delta['uml_acc']:+.6f} nll={delta['uml_nll']:+.6f}",
            "",
            f"Receipt: `{RECEIPT_JSON.as_posix()}`",
            "",
        ]
    )
    RECEIPT_MD.write_text(md, encoding="utf-8", newline="\n")
    print(
        f"THERMAL_AB_{objective} verdict={verdict} "
        f"uml_acc {m0['uml_acc']:.6f}->{m1['uml_acc']:.6f} d={delta['uml_acc']:+.6f} "
        f"uml_nll {m0['uml_nll']:.6f}->{m1['uml_nll']:.6f} d={delta['uml_nll']:+.6f} "
        f"codex_hold={both_hold}",
        flush=True,
    )
    return 0 if objective in {"PASS", "TIE", "INCONCLUSIVE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
