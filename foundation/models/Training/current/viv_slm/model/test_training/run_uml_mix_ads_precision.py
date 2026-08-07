#!/usr/bin/env python3
"""ADS precision search — expand mix decimal places until diminishing returns.

Starts from a known-good floor and known-fail ceiling, bisects the mix window,
and stops when either:
  - window width <= min_step, or
  - consecutive held UML-acc gains fall below uml_eps (diminishing returns).
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
OUT_DIR = SANDBOX / "runs" / "uml_mix_ads_precision"
RECEIPT_JSON = SANDBOX / "runs" / "uml_mix_ads_precision_latest.json"
RECEIPT_MD = SANDBOX / "runs" / "uml_mix_ads_precision_latest.md"
RECIPE_PATH = SANDBOX / "uml_mix_recipe.json"
DEFAULT_SURVIVOR = SANDBOX / "runs" / "uml_mix_ads" / "ads_survivor.pt"

for p in (MODEL, SANDBOX, FOUNDATION):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

import run_uml_equation_ab as ab  # noqa: E402


def _decimals_for_step(step: float) -> int:
    s = f"{step:.10f}".rstrip("0")
    if "." not in s:
        return 0
    return len(s.split(".", 1)[1])


def _fmt_mix(x: float, decimals: int) -> float:
    return round(float(x), max(2, decimals))


def main() -> int:
    recipe = ab.load_mix_recipe(RECIPE_PATH)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--floor", type=float, default=float(recipe.get("mix_ratio", 0.76)))
    parser.add_argument("--ceiling", type=float, default=0.78)
    parser.add_argument(
        "--warm-ckpt",
        type=Path,
        default=DEFAULT_SURVIVOR if DEFAULT_SURVIVOR.is_file() else EFF,
    )
    parser.add_argument(
        "--steps-per-probe",
        type=int,
        default=int(recipe.get("steps_sweep", 1500)),
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
    parser.add_argument(
        "--codex-hold-tol",
        type=float,
        default=float(recipe.get("codex_hold_tol", 0.001)),
    )
    parser.add_argument("--min-step", type=float, default=0.001)
    parser.add_argument(
        "--uml-eps",
        type=float,
        default=0.001,
        help="Stop when held UML-acc gain vs prior floor < this (diminishing returns).",
    )
    parser.add_argument("--max-probes", type=int, default=12)
    parser.add_argument(
        "--commit-recipe",
        action="store_true",
        help="Write best held mix into uml_mix_recipe.json.",
    )
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    lo = float(args.floor)
    hi = float(args.ceiling)
    if not (0.0 < lo < hi <= 1.0):
        raise ValueError(f"ads_precision_bad_window:lo={lo}:hi={hi}")

    warm_src = Path(args.warm_ckpt)
    if not warm_src.is_file():
        raise FileNotFoundError(f"ads_precision_missing_warm:{warm_src}")

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
    best_ckpt = warm
    best_mix = lo
    best_metrics = start_metrics
    probes: list[dict[str, Any]] = []
    stop_reason = "max_probes"
    decimals = max(2, _decimals_for_step((hi - lo) / 2.0))

    print(
        f"ADS_PREC_START lo={lo} hi={hi} min_step={args.min_step} uml_eps={args.uml_eps} "
        f"codex_start={start_codex:.6f}",
        flush=True,
    )

    for i in range(int(args.max_probes)):
        width = hi - lo
        if width <= float(args.min_step) + 1e-12:
            stop_reason = "window_min_step"
            break
        decimals = max(decimals, _decimals_for_step(width / 2.0), _decimals_for_step(args.min_step))
        mid = _fmt_mix((lo + hi) / 2.0, decimals)
        # Avoid re-probing endpoints.
        if mid <= lo + 1e-12 or mid >= hi - 1e-12:
            stop_reason = "window_collapsed"
            break

        name = f"prec_{i:02d}_mix_{mid}".replace(".", "p")
        print(f"ADS_PREC_PROBE mix={mid} window=[{lo},{hi}] decimals={decimals}", flush=True)
        ckpt = ab._train_leg(
            name=name,
            warm_ckpt=current_ckpt if mid > best_mix else best_ckpt,
            steps=int(args.steps_per_probe),
            batch_size=int(args.batch_size),
            lr=float(args.lr),
            mix_ratio=float(mid),
            device=device,
            tok=tok,
            codex_train=codex_train,
            uml_train=uml_train,
            seed=int(args.seed) + 100 + i,
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
        uml_gain = float(metrics["uml_acc"]) - float(best_metrics["uml_acc"])
        row = {
            "probe": i,
            "mix_ratio": mid,
            "lo_before": lo,
            "hi_before": hi,
            "decimals": decimals,
            "metrics": metrics,
            "delta_codex_vs_start": delta_codex,
            "uml_gain_vs_best": uml_gain,
            "codex_hold": hold,
            "decision": "RAISE_FLOOR" if hold else "LOWER_CEILING",
        }
        probes.append(row)
        print(
            f"ADS_PREC mix={mid} hold={hold} codex={metrics['codex_acc']:.6f} "
            f"d={delta_codex:+.6f} uml={metrics['uml_acc']:.6f} "
            f"uml_gain={uml_gain:+.6f} -> {row['decision']}",
            flush=True,
        )

        if hold:
            lo = mid
            best_mix = mid
            best_ckpt = ckpt
            current_ckpt = ckpt
            # Diminishing returns: held, but UML barely moved vs prior best.
            if uml_gain < float(args.uml_eps):
                best_metrics = metrics
                stop_reason = "diminishing_uml_gain"
                break
            best_metrics = metrics
        else:
            hi = mid
            # Failed probe does not become warm; stay on best held ckpt.
            current_ckpt = best_ckpt

    survivor = OUT_DIR / "ads_precision_survivor.pt"
    if best_ckpt.is_file() and best_ckpt != warm:
        shutil.copy2(best_ckpt, survivor)
    else:
        survivor = best_ckpt

    # Also refresh main ADS survivor pointer for continuity.
    main_surv = SANDBOX / "runs" / "uml_mix_ads" / "ads_survivor.pt"
    if survivor.is_file() and main_surv.parent.is_dir():
        shutil.copy2(survivor, main_surv)

    if args.commit_recipe:
        data = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
        data["mix_ratio"] = float(best_mix)
        data["mix_ratio_note"] = (
            f"Precision ADS best={best_mix} stop={stop_reason}; "
            f"receipt runs/uml_mix_ads_precision_latest.json"
        )
        data["ads_precision_last"] = datetime.now(timezone.utc).isoformat()
        RECIPE_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    objective = (
        "PASS_DIMINISHING"
        if stop_reason == "diminishing_uml_gain"
        else ("PASS_MIN_STEP" if stop_reason in {"window_min_step", "window_collapsed"} else "PASS_PARTIAL")
    )
    receipt: dict[str, Any] = {
        "schema_version": "uml_mix_ads_precision_v1",
        "status": "PASS",
        "objective": objective,
        "stop_reason": stop_reason,
        "hypothesis": (
            "Bisect mix between floor/ceiling; expand decimal precision until "
            "window <= min_step or held UML gains fall below uml_eps."
        ),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "sandbox_only": True,
        "floor_start": float(args.floor),
        "ceiling_start": float(args.ceiling),
        "final_window": [lo, hi],
        "best_mix": best_mix,
        "best_metrics": best_metrics,
        "start": start_metrics,
        "min_step": float(args.min_step),
        "uml_eps": float(args.uml_eps),
        "steps_per_probe": int(args.steps_per_probe),
        "probes": probes,
        "bank_version": mix_build.get("bank_version"),
        "warm_source": str(warm_src).replace("\\", "/"),
        "artifacts": {
            "warm": str(warm).replace("\\", "/"),
            "survivor": str(survivor).replace("\\", "/"),
            "best": str(best_ckpt).replace("\\", "/"),
        },
        "device": str(device),
    }
    with RECEIPT_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    stamped = OUT_DIR / f"receipt_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    shutil.copy2(RECEIPT_JSON, stamped)

    md = [
        "# UML Mix ADS Precision",
        "",
        f"- Objective: **{objective}**",
        f"- Stop: **{stop_reason}**",
        f"- Best mix: **{best_mix}**",
        f"- Final window: [{lo}, {hi}]",
        f"- Probes: {len(probes)}",
        "",
        "## Probes",
    ]
    for r in probes:
        m = r["metrics"]
        md.append(
            f"- mix={r['mix_ratio']} hold={r['codex_hold']} "
            f"codex={m['codex_acc']:.6f} uml={m['uml_acc']:.6f} "
            f"uml_gain={r['uml_gain_vs_best']:+.6f} -> {r['decision']}"
        )
    md.extend(["", f"Receipt: `{RECEIPT_JSON.as_posix()}`", ""])
    RECEIPT_MD.write_text("\n".join(md), encoding="utf-8", newline="\n")

    print(
        f"ADS_PREC_{objective} best={best_mix} window=[{lo},{hi}] "
        f"stop={stop_reason} probes={len(probes)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    # Windows consoles are often cp1252; keep status lines ASCII-safe.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main())
