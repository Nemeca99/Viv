#!/usr/bin/env python3
"""Matched A/B: plant_sn gated (existing L4) vs ungated twin from same L3 survivor.

Hypothesis
----------
SHED_LOAD is operationally compatible with UML gains (L4). This run tests whether
gating *causes* better/worse outcomes vs identical ungated training from the same
warm checkpoint (layer_math_bank.pt), same seed/steps/mix/boost/bank.
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
OUT_DIR = SANDBOX / "runs" / "uml_plant_sn_ab"
LAYERS = SANDBOX / "runs" / "uml_mix_layers"
WARM_L3 = LAYERS / "layer_math_bank.pt"
GATED_RECEIPT = LAYERS / "layer_plant_sn_latest.json"
RECEIPT_JSON = SANDBOX / "runs" / "uml_plant_sn_ab_latest.json"
RECEIPT_MD = SANDBOX / "runs" / "uml_plant_sn_ab_latest.md"
RECIPE_PATH = SANDBOX / "uml_mix_recipe.json"

for p in (MODEL, SANDBOX, FOUNDATION):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

import run_uml_equation_ab as ab  # noqa: E402


def _verdict(d_uml_acc: float, d_uml_nll: float, *, min_acc: float = 0.005, min_nll: float = 0.02) -> str:
    # gated − ungated
    if d_uml_acc >= min_acc and d_uml_nll <= -min_nll:
        return "GATED_WIN"
    if d_uml_acc <= -min_acc and d_uml_nll >= min_nll:
        return "UNGATED_WIN"
    if abs(d_uml_acc) < min_acc and abs(d_uml_nll) < min_nll:
        return "TIE"
    return "INCONCLUSIVE"


def main() -> int:
    recipe = ab.load_mix_recipe(RECIPE_PATH)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=int(recipe.get("steps_default", 10000)))
    parser.add_argument("--mix-ratio", type=float, default=float(recipe.get("mix_ratio", 0.779375)))
    parser.add_argument(
        "--prefer-cheap-boost",
        type=float,
        default=float(recipe.get("prefer_cheap_boost", 1.5)),
    )
    parser.add_argument("--batch-size", type=int, default=int(recipe.get("batch_size", 64)))
    parser.add_argument("--lr", type=float, default=float(recipe.get("lr", 7e-6)))
    parser.add_argument("--seed", type=int, default=int(recipe.get("seed", 42)) + 4)
    parser.add_argument("--log-every", type=int, default=int(recipe.get("log_every", 500)))
    parser.add_argument("--device", default="cuda")
    parser.add_argument(
        "--reuse-gated-receipt",
        type=Path,
        default=GATED_RECEIPT,
        help="Use existing L4 gated metrics if present (skip retrain gated).",
    )
    args = parser.parse_args()

    if not WARM_L3.is_file():
        raise FileNotFoundError(f"missing_l3_warm:{WARM_L3}")
    if not args.reuse_gated_receipt.is_file():
        raise FileNotFoundError(f"missing_gated_receipt:{args.reuse_gated_receipt}")

    gated = json.loads(args.reuse_gated_receipt.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    uml_tensor = ab._ensure_mix_dataset()
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

    warm = OUT_DIR / "warm_from_l3.pt"
    shutil.copy2(WARM_L3, warm)
    start = ab._metrics(
        warm, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
    )

    print(
        f"PLANT_SN_AB ungated twin steps={args.steps} mix={args.mix_ratio} "
        f"boost={args.prefer_cheap_boost} seed={args.seed}",
        flush=True,
    )
    ungated_ckpt = ab._train_leg(
        name="ungated_twin",
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
        out_dir=OUT_DIR,
    )
    ungated = ab._metrics(
        ungated_ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
    )

    g_after = gated["after"]
    delta = {
        "codex_acc": g_after["codex_acc"] - ungated["codex_acc"],
        "codex_nll": g_after["codex_nll"] - ungated["codex_nll"],
        "uml_acc": g_after["uml_acc"] - ungated["uml_acc"],
        "uml_nll": g_after["uml_nll"] - ungated["uml_nll"],
    }
    verdict = _verdict(delta["uml_acc"], delta["uml_nll"])
    hold_g = bool(gated.get("codex_hold"))
    hold_u = (ungated["codex_acc"] - start["codex_acc"]) >= -float(recipe.get("codex_hold_tol", 0.001))
    if not (hold_g and hold_u):
        objective = "FAIL_HOLD"
    elif verdict == "GATED_WIN":
        objective = "PASS_GATED_CAUSAL"
    elif verdict == "UNGATED_WIN":
        objective = "PASS_UNGATED_BETTER"
    elif verdict == "TIE":
        objective = "TIE_COMPATIBLE_ONLY"
    else:
        objective = "INCONCLUSIVE"

    receipt: dict[str, Any] = {
        "schema_version": "uml_plant_sn_ab_v1",
        "status": "PASS",
        "objective": objective,
        "verdict": verdict,
        "hypothesis": (
            "Matched ungated twin from L3 survivor vs L4 gated receipt. "
            "Tests whether SHED_LOAD *caused* UML lift, not merely coexisted with it."
        ),
        "binding_claim": (
            "L4 proved operational metabolism (plant→shed→train→UML↑→Codex hold). "
            "Causal credit to SHED_LOAD requires this matched A/B."
        ),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "matched": {
            "warm": str(WARM_L3).replace("\\", "/"),
            "steps": int(args.steps),
            "mix_ratio": float(args.mix_ratio),
            "prefer_cheap_boost": float(args.prefer_cheap_boost),
            "seed": int(args.seed),
            "bank": "v6_federation",
        },
        "start": start,
        "gated_l4": g_after,
        "ungated_twin": ungated,
        "delta_gated_minus_ungated": delta,
        "codex_hold_gated": hold_g,
        "codex_hold_ungated": hold_u,
        "gated_receipt": str(args.reuse_gated_receipt).replace("\\", "/"),
        "artifacts": {
            "warm": str(warm).replace("\\", "/"),
            "ungated": str(ungated_ckpt).replace("\\", "/"),
        },
        "device": str(device),
    }
    with RECEIPT_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    shutil.copy2(RECEIPT_JSON, OUT_DIR / f"receipt_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")

    md = "\n".join(
        [
            "# Plant S_n Gate Matched A/B",
            "",
            f"- Objective: **{objective}**",
            f"- Verdict (gated − ungated): **{verdict}**",
            f"- Warm: L3 `layer_math_bank.pt`",
            "",
            "## UML",
            f"- Gated   acc={g_after['uml_acc']:.6f} nll={g_after['uml_nll']:.6f}",
            f"- Ungated acc={ungated['uml_acc']:.6f} nll={ungated['uml_nll']:.6f}",
            f"- Delta   acc={delta['uml_acc']:+.6f} nll={delta['uml_nll']:+.6f}",
            "",
            "## Codex",
            f"- Gated   acc={g_after['codex_acc']:.6f} hold={hold_g}",
            f"- Ungated acc={ungated['codex_acc']:.6f} hold={hold_u}",
            "",
            f"Receipt: `{RECEIPT_JSON.as_posix()}`",
            "",
        ]
    )
    RECEIPT_MD.write_text(md, encoding="utf-8", newline="\n")
    print(
        f"PLANT_SN_AB_{objective} verdict={verdict} "
        f"uml_acc gated={g_after['uml_acc']:.6f} ungated={ungated['uml_acc']:.6f} "
        f"d={delta['uml_acc']:+.6f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main())
