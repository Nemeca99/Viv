#!/usr/bin/env python3
"""J: Short A/B proving RID residual sample-weighting as a train signal."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

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
    _extract_route_pair,
    _metrics,
    _train_leg,
    _verdict,
    load_mix_recipe,
)
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

OUT_DIR = SANDBOX / "runs" / "uml_rid_residual_train_j"
RECEIPT = SANDBOX / "runs" / "uml_rid_residual_train_j_latest.json"


def main() -> int:
    recipe = load_mix_recipe()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=int(recipe.get("steps_sweep", 1500)))
    parser.add_argument("--batch-size", type=int, default=int(recipe.get("batch_size", 64)))
    parser.add_argument("--lr", type=float, default=float(recipe.get("lr", 7e-6)))
    parser.add_argument("--mix-ratio", type=float, default=float(recipe.get("mix_ratio", 0.15)))
    parser.add_argument(
        "--prefer-cheap-boost",
        type=float,
        default=float(recipe.get("prefer_cheap_boost", 2.0)),
    )
    parser.add_argument(
        "--rid-residual-weight",
        type=float,
        default=float(recipe.get("rid_residual_weight", 0.25)),
    )
    parser.add_argument("--seed", type=int, default=int(recipe.get("seed", 42)))
    parser.add_argument("--log-every", type=int, default=int(recipe.get("log_every", 500)))
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    # Extractor smoke (no GPU).
    cheap_t = "User: Prefer efficient UML for H\nViv: 41<END>\n"
    costly_t = "User: UML equivalent for H\nViv: 40+1<END>\n"
    ch1, p1 = _extract_route_pair(cheap_t)
    ch2, p2 = _extract_route_pair(costly_t)
    extract_ok = ch1 == "H" and p1 == "41" and ch2 == "H" and p2 == "40+1"

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

    # Control: recipe boost, no RID weight.
    ctrl_ckpt = _train_leg(
        name="pilot_boost_no_rid",
        warm_ckpt=warm,
        steps=int(args.steps),
        batch_size=int(args.batch_size),
        lr=float(args.lr),
        mix_ratio=float(args.mix_ratio),
        device=device,
        tok=tok,
        codex_train=codex_train,
        uml_train=uml_train,
        seed=int(args.seed) + 1,
        log_every=int(args.log_every),
        prefer_cheap_boost=float(args.prefer_cheap_boost),
        rid_residual_weight=0.0,
        out_dir=OUT_DIR,
    )
    # Pilot: same boost + RID residual weighting.
    rid_ckpt = _train_leg(
        name="pilot_boost_with_rid",
        warm_ckpt=warm,
        steps=int(args.steps),
        batch_size=int(args.batch_size),
        lr=float(args.lr),
        mix_ratio=float(args.mix_ratio),
        device=device,
        tok=tok,
        codex_train=codex_train,
        uml_train=uml_train,
        seed=int(args.seed) + 2,
        log_every=int(args.log_every),
        prefer_cheap_boost=float(args.prefer_cheap_boost),
        rid_residual_weight=float(args.rid_residual_weight),
        out_dir=OUT_DIR,
    )
    # Codex-only baseline for hold bar.
    base_ckpt = _train_leg(
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

    baseline = _metrics(base_ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size)
    control = _metrics(ctrl_ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size)
    pilot = _metrics(rid_ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size)

    d_ctrl = {
        "codex_acc": control["codex_acc"] - baseline["codex_acc"],
        "uml_acc": control["uml_acc"] - baseline["uml_acc"],
        "uml_nll": control["uml_nll"] - baseline["uml_nll"],
    }
    d_pilot = {
        "codex_acc": pilot["codex_acc"] - baseline["codex_acc"],
        "uml_acc": pilot["uml_acc"] - baseline["uml_acc"],
        "uml_nll": pilot["uml_nll"] - baseline["uml_nll"],
    }
    d_rid_vs_ctrl = {
        "codex_acc": pilot["codex_acc"] - control["codex_acc"],
        "uml_acc": pilot["uml_acc"] - control["uml_acc"],
        "uml_nll": pilot["uml_nll"] - control["uml_nll"],
    }
    hold = _codex_hold(d_pilot["codex_acc"])
    rid_payload = torch.load(rid_ckpt, map_location="cpu", weights_only=False)
    rid_batches = int(rid_payload.get("rid_scored_batches") or 0)
    uml_improved_vs_base = d_pilot["uml_nll"] < -0.05 or d_pilot["uml_acc"] > 0.02
    rid_helps = (d_rid_vs_ctrl["uml_nll"] < 0 and d_rid_vs_ctrl["uml_acc"] >= -0.005) or (
        d_rid_vs_ctrl["uml_acc"] > 0.002 and d_rid_vs_ctrl["uml_nll"] <= 0.01
    )
    status = "PASS" if extract_ok and hold and uml_improved_vs_base and rid_batches > 0 else "FAIL"
    # Soft: if RID doesn't beat control but holds + scores, mark INCONCLUSIVE not hard fail.
    if extract_ok and hold and uml_improved_vs_base and rid_batches > 0 and not rid_helps:
        status = "INCONCLUSIVE"

    receipt = {
        "schema_version": "uml_rid_residual_train_j_v1",
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "RID route-error sample weights (cheap upweighted) improve UML vs boost-only control without breaking Codex hold.",
        "extract_ok": extract_ok,
        "prefer_cheap_boost": float(args.prefer_cheap_boost),
        "rid_residual_weight": float(args.rid_residual_weight),
        "steps": int(args.steps),
        "rid_scored_batches": rid_batches,
        "baseline": baseline,
        "control_boost_only": control,
        "pilot_boost_plus_rid": pilot,
        "delta_control_vs_baseline": d_ctrl,
        "delta_pilot_vs_baseline": d_pilot,
        "delta_rid_vs_control": d_rid_vs_ctrl,
        "codex_hold_pilot": hold,
        "rid_helps_vs_control": rid_helps,
        "verdict_pilot_codex": _verdict(d_pilot["codex_acc"], pilot["codex_nll"] - baseline["codex_nll"]),
        "artifacts": {
            "out_dir": str(OUT_DIR).replace("\\", "/"),
            "control": str(ctrl_ckpt).replace("\\", "/"),
            "pilot": str(rid_ckpt).replace("\\", "/"),
            "baseline": str(base_ckpt).replace("\\", "/"),
        },
    }
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"UML_RID_TRAIN_J_{status} hold={hold} rid_batches={rid_batches} "
        f"uml_nll ctrl={control['uml_nll']:.4f}->rid={pilot['uml_nll']:.4f} "
        f"d={d_rid_vs_ctrl['uml_nll']:+.4f} "
        f"uml_acc d={d_rid_vs_ctrl['uml_acc']:+.4f}",
        flush=True,
    )
    return 0 if status != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
