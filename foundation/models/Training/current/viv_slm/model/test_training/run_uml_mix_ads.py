#!/usr/bin/env python3
"""Adaptive Dose Schedule (ADS) — auto-climb UML mix_ratio toward a target.

Idea
----
You want 0.5 UML. Don't jump. ADS doses mix upward on a ladder, keeps the
checkpoint only when Codex hold survives, rolls back and halts on break.

Default ladder: 0.15 → 0.25 → 0.35 → 0.45 → 0.50
Each rung trains from the previous surviving ckpt (progressive climb).
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
OUT_DIR = SANDBOX / "runs" / "uml_mix_ads"
RECEIPT_JSON = SANDBOX / "runs" / "uml_mix_ads_latest.json"
RECEIPT_MD = SANDBOX / "runs" / "uml_mix_ads_latest.md"
RECIPE_PATH = SANDBOX / "uml_mix_recipe.json"

for p in (MODEL, SANDBOX, FOUNDATION):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

import run_uml_equation_ab as ab  # noqa: E402


def _parse_ladder(text: str) -> list[float]:
    vals = [float(x.strip()) for x in str(text).split(",") if x.strip()]
    if not vals:
        raise ValueError("ads_empty_ladder")
    for v in vals:
        if not (0.0 < v <= 1.0):
            raise ValueError(f"ads_mix_out_of_range:{v}")
    return vals


def _default_ladder(*, start: float, target: float, step: float) -> list[float]:
    if target < start:
        raise ValueError("ads_target_below_start")
    out: list[float] = []
    x = float(start)
    # Inclusive climb; snap last rung to target.
    while x < target - 1e-9:
        out.append(round(x, 4))
        x = min(target, x + step)
    if not out or abs(out[-1] - target) > 1e-9:
        out.append(round(float(target), 4))
    # Dedup while preserving order.
    seen: set[float] = set()
    uniq: list[float] = []
    for v in out:
        key = round(v, 4)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(key)
    return uniq


def main() -> int:
    recipe = ab.load_mix_recipe(RECIPE_PATH)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--steps-per-rung",
        type=int,
        default=int(recipe.get("steps_sweep", 1500)),
        help="Train steps per mix dose (default: recipe steps_sweep).",
    )
    parser.add_argument("--batch-size", type=int, default=int(recipe.get("batch_size", 64)))
    parser.add_argument("--lr", type=float, default=float(recipe.get("lr", 7e-6)))
    parser.add_argument(
        "--prefer-cheap-boost",
        type=float,
        default=float(recipe.get("prefer_cheap_boost", 2.0)),
    )
    parser.add_argument("--seed", type=int, default=int(recipe.get("seed", 42)))
    parser.add_argument("--log-every", type=int, default=int(recipe.get("log_every", 500)))
    parser.add_argument("--start-mix", type=float, default=float(recipe.get("mix_ratio", 0.15)))
    parser.add_argument("--target-mix", type=float, default=0.5)
    parser.add_argument("--mix-step", type=float, default=0.1)
    parser.add_argument(
        "--ladder",
        type=str,
        default="",
        help="Explicit comma ladder, e.g. 0.15,0.25,0.35,0.45,0.5 (overrides start/step/target).",
    )
    parser.add_argument(
        "--codex-hold-tol",
        type=float,
        default=float(recipe.get("codex_hold_tol", 0.001)),
    )
    parser.add_argument(
        "--warm-ckpt",
        type=Path,
        default=None,
        help="Continue from this checkpoint (default: efficient specialist).",
    )
    parser.add_argument(
        "--commit-recipe",
        action="store_true",
        help="Write last surviving mix_ratio into uml_mix_recipe.json.",
    )
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    if args.ladder.strip():
        ladder = _parse_ladder(args.ladder)
    else:
        ladder = _default_ladder(
            start=float(args.start_mix),
            target=float(args.target_mix),
            step=float(args.mix_step),
        )

    warm_src = Path(args.warm_ckpt) if args.warm_ckpt else EFF
    if not warm_src.is_file():
        raise FileNotFoundError(f"ads_missing_warm:{warm_src}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
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
    shutil.copy2(warm_src, warm)
    start_metrics = ab._metrics(
        warm, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
    )
    start_codex = float(start_metrics["codex_acc"])
    current_ckpt = warm
    last_good_ckpt = warm
    last_good_mix = 0.0
    last_good_metrics = start_metrics
    rungs: list[dict[str, Any]] = []
    halted_reason = None
    best_mix_reached = 0.0

    print(
        f"ADS_START ladder={ladder} steps_per_rung={args.steps_per_rung} "
        f"codex_start={start_codex:.6f} tol={args.codex_hold_tol}",
        flush=True,
    )

    for i, mix in enumerate(ladder):
        name = f"rung_{i:02d}_mix_{mix:.2f}".replace(".", "p")
        print(f"ADS_RUNG begin mix={mix:.2f} from={current_ckpt.name}", flush=True)
        ckpt = ab._train_leg(
            name=name,
            warm_ckpt=current_ckpt,
            steps=int(args.steps_per_rung),
            batch_size=int(args.batch_size),
            lr=float(args.lr),
            mix_ratio=float(mix),
            device=device,
            tok=tok,
            codex_train=codex_train,
            uml_train=uml_train,
            seed=int(args.seed) + i,
            log_every=int(args.log_every),
            prefer_cheap_boost=float(args.prefer_cheap_boost),
            rid_residual_weight=0.0,
            thermal_route_weight=0.0,
            out_dir=OUT_DIR,
        )
        metrics = ab._metrics(
            ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
        )
        delta_codex = float(metrics["codex_acc"]) - start_codex
        hold = delta_codex >= -float(args.codex_hold_tol)
        uml_gain = float(metrics["uml_acc"]) - float(start_metrics["uml_acc"])
        row = {
            "rung": i,
            "mix_ratio": mix,
            "ckpt": str(ckpt).replace("\\", "/"),
            "metrics": metrics,
            "delta_codex_vs_start": delta_codex,
            "uml_acc_gain_vs_start": uml_gain,
            "codex_hold": hold,
            "decision": "ADVANCE" if hold else "ROLLBACK_HALT",
        }
        rungs.append(row)
        print(
            f"ADS_RUNG mix={mix:.2f} hold={hold} "
            f"codex={metrics['codex_acc']:.6f} d={delta_codex:+.6f} "
            f"uml={metrics['uml_acc']:.6f} decision={row['decision']}",
            flush=True,
        )
        if not hold:
            halted_reason = f"codex_hold_break_at_mix_{mix:.2f}"
            # Keep last good; do not advance current.
            break
        last_good_ckpt = ckpt
        last_good_mix = mix
        last_good_metrics = metrics
        current_ckpt = ckpt
        best_mix_reached = mix

    reached_target = abs(best_mix_reached - float(args.target_mix if not args.ladder else ladder[-1])) < 1e-9
    if halted_reason is None and reached_target:
        objective = "PASS_TARGET"
    elif halted_reason is None:
        objective = "PASS_PARTIAL"
    elif best_mix_reached > 0.0:
        objective = "HALT_ROLLBACK"
    else:
        objective = "FAIL_FIRST_RUNG"

    # Promote surviving ckpt to a stable name.
    survivor = OUT_DIR / "ads_survivor.pt"
    if last_good_ckpt.is_file() and last_good_ckpt != warm:
        shutil.copy2(last_good_ckpt, survivor)
    else:
        survivor = last_good_ckpt

    if args.commit_recipe and last_good_mix > 0.0:
        data = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
        data["mix_ratio"] = float(last_good_mix)
        data["mix_ratio_note"] = (
            f"ADS committed {last_good_mix} ({objective}); "
            f"receipt runs/uml_mix_ads_latest.json"
        )
        data["ads_last_run"] = datetime.now(timezone.utc).isoformat()
        RECIPE_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    receipt: dict[str, Any] = {
        "schema_version": "uml_mix_ads_v1",
        "status": "PASS",
        "objective": objective,
        "hypothesis": (
            "Adaptive Dose Schedule climbs UML mix_ratio toward target; "
            "advance only while Codex hold vs start survives; else rollback/halt."
        ),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "sandbox_only": True,
        "ladder": ladder,
        "target_mix": float(ladder[-1]),
        "warm_source": str(warm_src).replace("\\", "/"),
        "steps_per_rung": int(args.steps_per_rung),
        "prefer_cheap_boost": float(args.prefer_cheap_boost),
        "codex_hold_tol": float(args.codex_hold_tol),
        "bank_version": mix_build.get("bank_version"),
        "start": start_metrics,
        "rungs": rungs,
        "best_mix_reached": best_mix_reached,
        "last_good_mix": last_good_mix,
        "last_good_metrics": last_good_metrics,
        "halted_reason": halted_reason,
        "commit_recipe": bool(args.commit_recipe),
        "artifacts": {
            "warm": str(warm).replace("\\", "/"),
            "survivor": str(survivor).replace("\\", "/"),
            "last_good": str(last_good_ckpt).replace("\\", "/"),
        },
        "device": str(device),
    }
    with RECEIPT_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    stamped = OUT_DIR / f"receipt_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    shutil.copy2(RECEIPT_JSON, stamped)

    md_lines = [
        "# UML Mix ADS (Adaptive Dose Schedule)",
        "",
        f"- Objective: **{objective}**",
        f"- Ladder: {ladder}",
        f"- Best mix reached: **{best_mix_reached}**",
        f"- Last good mix: **{last_good_mix}**",
        f"- Steps/rung: {args.steps_per_rung}",
        f"- Halted: {halted_reason or 'none'}",
        "",
        "## Rungs",
    ]
    for r in rungs:
        m = r["metrics"]
        md_lines.append(
            f"- mix={r['mix_ratio']:.2f} hold={r['codex_hold']} "
            f"codex={m['codex_acc']:.6f} uml={m['uml_acc']:.6f} -> {r['decision']}"
        )
    md_lines.extend(["", f"Receipt: `{RECEIPT_JSON.as_posix()}`", ""])
    RECEIPT_MD.write_text("\n".join(md_lines), encoding="utf-8", newline="\n")

    print(
        f"ADS_{objective} best_mix={best_mix_reached} last_good={last_good_mix} "
        f"rungs={len(rungs)} halt={halted_reason or 'none'}",
        flush=True,
    )
    return 0 if objective.startswith("PASS") or objective == "HALT_ROLLBACK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
