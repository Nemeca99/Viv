#!/usr/bin/env python3
"""I: Prefer-cheap boost sweep (1.5 / 2.0 / 3.0) on short matched windows.

Shares one Codex-only baseline; trains one pilot per boost. RID residual off
so the sweep isolates G/H boost magnitude.
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
if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))
if str(SANDBOX) not in sys.path:
    sys.path.insert(0, str(SANDBOX))

from plant_runtime import configure_plant_runtime  # noqa: E402
from run_uml_equation_ab import (  # noqa: E402
    EFF,
    _codex_hold,
    _ensure_mix_dataset,
    _metrics,
    _train_leg,
    _verdict,
    load_mix_recipe,
)
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

OUT_DIR = SANDBOX / "runs" / "uml_prefer_cheap_boost_sweep"
RECEIPT = SANDBOX / "runs" / "uml_prefer_cheap_boost_sweep_latest.json"


def main() -> int:
    recipe = load_mix_recipe()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=int(recipe.get("steps_sweep", 1500)))
    parser.add_argument("--batch-size", type=int, default=int(recipe.get("batch_size", 64)))
    parser.add_argument("--lr", type=float, default=float(recipe.get("lr", 7e-6)))
    parser.add_argument("--mix-ratio", type=float, default=float(recipe.get("mix_ratio", 0.15)))
    parser.add_argument("--seed", type=int, default=int(recipe.get("seed", 42)))
    parser.add_argument("--log-every", type=int, default=int(recipe.get("log_every", 500)))
    parser.add_argument(
        "--boosts",
        type=float,
        nargs="+",
        default=[float(x) for x in recipe.get("boost_sweep", [1.5, 2.0, 3.0])],
    )
    parser.add_argument("--include-control", action="store_true", default=True)
    parser.add_argument("--no-control", action="store_true", help="Skip boost=1.0 control leg.")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    if args.no_control:
        args.include_control = False

    if not EFF.is_file():
        raise FileNotFoundError(f"missing_warm:{EFF}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    uml_tensor = _ensure_mix_dataset()
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

    print("SWEEP_BASELINE_START", flush=True)
    baseline_ckpt = _train_leg(
        name="baseline_codex_only",
        warm_ckpt=warm,
        steps=int(args.steps),
        batch_size=int(args.batch_size),
        lr=float(args.lr),
        mix_ratio=0.0,
        device=device,
        tok=tok,
        codex_train=codex_train,
        uml_train=uml_train,
        seed=int(args.seed),
        log_every=int(args.log_every),
        prefer_cheap_boost=1.0,
        rid_residual_weight=0.0,
        out_dir=OUT_DIR,
    )
    baseline = _metrics(
        baseline_ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
    )

    boosts = list(args.boosts)
    if args.include_control and 1.0 not in boosts:
        boosts = [1.0] + boosts

    rows: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for i, boost in enumerate(boosts):
        name = f"pilot_boost_{str(boost).replace('.', 'p')}"
        print(f"SWEEP_PILOT_START boost={boost}", flush=True)
        pilot_ckpt = _train_leg(
            name=name,
            warm_ckpt=warm,
            steps=int(args.steps),
            batch_size=int(args.batch_size),
            lr=float(args.lr),
            mix_ratio=float(args.mix_ratio),
            device=device,
            tok=tok,
            codex_train=codex_train,
            uml_train=uml_train,
            seed=int(args.seed) + 1 + i,
            log_every=int(args.log_every),
            prefer_cheap_boost=float(boost),
            rid_residual_weight=0.0,
            out_dir=OUT_DIR,
        )
        pilot = _metrics(
            pilot_ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
        )
        delta = {
            "codex_acc": pilot["codex_acc"] - baseline["codex_acc"],
            "codex_nll": pilot["codex_nll"] - baseline["codex_nll"],
            "uml_acc": pilot["uml_acc"] - baseline["uml_acc"],
            "uml_nll": pilot["uml_nll"] - baseline["uml_nll"],
        }
        hold = _codex_hold(delta["codex_acc"])
        uml_improved = delta["uml_nll"] < -0.05 or delta["uml_acc"] > 0.02
        row = {
            "boost": float(boost),
            "hold": hold,
            "uml_improved": uml_improved,
            "objective": "PASS" if hold and uml_improved else ("HOLD_ONLY" if hold else "FAIL_HOLD"),
            "verdict_codex": _verdict(delta["codex_acc"], delta["codex_nll"]),
            "pilot": pilot,
            "delta_vs_baseline": delta,
            "ckpt": str(pilot_ckpt).replace("\\", "/"),
        }
        rows.append(row)
        # Prefer lower UML NLL among Codex-holding pilots; tie-break higher UML acc.
        if hold:
            if best is None or (
                (pilot["uml_nll"], -pilot["uml_acc"])
                < (best["pilot"]["uml_nll"], -best["pilot"]["uml_acc"])
            ):
                best = row
        print(
            f"SWEEP_PILOT_DONE boost={boost} hold={hold} "
            f"uml_acc={pilot['uml_acc']:.4f} uml_nll={pilot['uml_nll']:.4f}",
            flush=True,
        )

    receipt = {
        "schema_version": "uml_prefer_cheap_boost_sweep_v1",
        "status": "PASS" if best is not None else "FAIL",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "Among boosts {1.5,2.0,3.0} (+control 1.0), some hold Codex and minimize UML NLL on short matched windows.",
        "steps": int(args.steps),
        "mix_ratio": float(args.mix_ratio),
        "rid_residual_weight": 0.0,
        "baseline": baseline,
        "rows": rows,
        "best": best,
        "artifacts": {"out_dir": str(OUT_DIR).replace("\\", "/"), "warm": str(warm).replace("\\", "/")},
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    if best is not None:
        pointer = OUT_DIR / "_best_pointer.json"
        with pointer.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {
                    "boost": best["boost"],
                    "ckpt": best["ckpt"],
                    "uml_acc": best["pilot"]["uml_acc"],
                    "uml_nll": best["pilot"]["uml_nll"],
                },
                handle,
                indent=2,
            )
            handle.write("\n")
    best_s = (
        f"boost={best['boost']} uml_acc={best['pilot']['uml_acc']:.4f} "
        f"uml_nll={best['pilot']['uml_nll']:.4f}"
        if best
        else "none"
    )
    print(f"UML_BOOST_SWEEP_{receipt['status']} best={best_s}", flush=True)
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
