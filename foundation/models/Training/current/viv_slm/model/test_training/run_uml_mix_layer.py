#!/usr/bin/env python3
"""One-layer-at-a-time mix experiments from the precision survivor.

Layers (run separately; check receipt before next):
  1) long_steps  — +N steps at locked mix, boost unchanged
  2) soft_boost  — same mix/steps, prefer_cheap_boost softened
  3) math_bank   — blend/switch UML bank toward native math tokens
  4) plant_sn    — furnace S_n mix shed gate
  5) continue_train — +N steps from survivor with plant_sn gate held

Each layer warms from --warm-ckpt (default: latest layer survivor chain).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
PY = Path(r"L:\Continue\.venv\Scripts\python.exe")
EFF = SANDBOX / "checkpoints" / "efficient" / "specialist.pt"
PREC_SURV = SANDBOX / "runs" / "uml_mix_ads_precision" / "ads_precision_survivor.pt"
OUT_DIR = SANDBOX / "runs" / "uml_mix_layers"
RECIPE_PATH = SANDBOX / "uml_mix_recipe.json"
NATIVE_DIR = SANDBOX / "data" / "uml_native_math_tokens_v1"
MIX_DIR = SANDBOX / "data" / "uml_equation_mix_v1"

for p in (MODEL, SANDBOX, FOUNDATION):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

import run_uml_equation_ab as ab  # noqa: E402


def _load_recipe() -> dict[str, Any]:
    return ab.load_mix_recipe(RECIPE_PATH)


def _ensure_native_bank() -> Path:
    """Build native dialogues + tensor dataset if missing."""
    tensor = NATIVE_DIR / "tensor_dataset"
    dialogues = NATIVE_DIR / "train_dialogues.txt"
    if tensor.is_dir() and (tensor / "MANIFEST.json").is_file() and dialogues.is_file():
        return tensor
    build = SANDBOX / "build_uml_native_math_tokens.py"
    subprocess.run([str(PY), "-B", str(build)], check=True, cwd=str(SANDBOX))
    if not dialogues.is_file():
        raise FileNotFoundError(f"native_dialogues_missing:{dialogues}")
    subprocess.run(
        [
            str(PY),
            "-B",
            str(SANDBOX / "pack_uml_dialogues_tensor.py"),
            "--dialogues",
            str(dialogues),
            "--out",
            str(tensor),
            "--repeat",
            "48",
        ],
        check=True,
        cwd=str(SANDBOX),
    )
    if not (tensor / "MANIFEST.json").is_file():
        raise FileNotFoundError(f"native_tensor_missing:{tensor}")
    return tensor


def _chain_warm(default: Path) -> Path:
    chain = OUT_DIR / "layer_survivor.pt"
    if chain.is_file():
        return chain
    if PREC_SURV.is_file():
        return PREC_SURV
    return default


def main() -> int:
    recipe = _load_recipe()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--layer",
        required=True,
        choices=["long_steps", "soft_boost", "math_bank", "plant_sn", "continue_train"],
    )
    parser.add_argument("--steps", type=int, default=int(recipe.get("steps_default", 10000)))
    parser.add_argument("--mix-ratio", type=float, default=float(recipe.get("mix_ratio", 0.779375)))
    parser.add_argument(
        "--prefer-cheap-boost",
        type=float,
        default=None,
        help="Override boost; soft_boost layer defaults to 1.5",
    )
    parser.add_argument("--warm-ckpt", type=Path, default=None)
    parser.add_argument("--batch-size", type=int, default=int(recipe.get("batch_size", 64)))
    parser.add_argument("--lr", type=float, default=float(recipe.get("lr", 7e-6)))
    parser.add_argument("--seed", type=int, default=int(recipe.get("seed", 42)))
    parser.add_argument("--log-every", type=int, default=int(recipe.get("log_every", 500)))
    parser.add_argument(
        "--codex-hold-tol",
        type=float,
        default=float(recipe.get("codex_hold_tol", 0.001)),
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument(
        "--commit-survivor",
        action="store_true",
        help="If Codex holds, promote ckpt to layer_survivor.pt",
    )
    args = parser.parse_args()

    if args.prefer_cheap_boost is None:
        if args.layer == "soft_boost":
            boost = 1.5
        else:
            boost = float(recipe.get("prefer_cheap_boost", 2.0))
    else:
        boost = float(args.prefer_cheap_boost)

    warm_src = Path(args.warm_ckpt) if args.warm_ckpt else _chain_warm(EFF)
    if not warm_src.is_file():
        raise FileNotFoundError(f"layer_missing_warm:{warm_src}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # UML tensor source
    if args.layer == "math_bank":
        try:
            uml_tensor = _ensure_native_bank()
            bank_label = "uml_native_math_tokens_v1"
        except Exception as exc:
            print(f"LAYER_MATH_BANK_FALLBACK:{exc!r}", flush=True)
            uml_tensor = ab._ensure_mix_dataset()
            bank_label = "v6_federation_fallback"
    else:
        uml_tensor = ab._ensure_mix_dataset()
        bank_label = "v6_federation"

    mix_build = {}
    build_json = MIX_DIR / "BUILD.json"
    if build_json.is_file():
        mix_build = json.loads(build_json.read_text(encoding="utf-8"))

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

    warm = OUT_DIR / f"warm_{args.layer}.pt"
    shutil.copy2(warm_src, warm)
    start = ab._metrics(
        warm, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
    )

    use_plant_sn = args.layer in {"plant_sn", "continue_train"}
    print(
        f"LAYER_{args.layer}_START mix={args.mix_ratio} steps={args.steps} "
        f"boost={boost} bank={bank_label} plant_sn={use_plant_sn} "
        f"warm={warm_src.name}",
        flush=True,
    )
    seed_off = {
        "long_steps": 1,
        "soft_boost": 2,
        "math_bank": 3,
        "plant_sn": 4,
        "continue_train": 5,
    }[args.layer]
    ckpt = ab._train_leg(
        name=f"layer_{args.layer}",
        warm_ckpt=warm,
        steps=int(args.steps),
        batch_size=int(args.batch_size),
        lr=float(args.lr),
        mix_ratio=float(args.mix_ratio),
        device=device,
        tok=tok,
        codex_train=codex_train,
        uml_train=uml_train,
        seed=int(args.seed) + seed_off,
        log_every=int(args.log_every),
        prefer_cheap_boost=boost,
        rid_residual_weight=0.0,
        thermal_route_weight=0.0,
        plant_sn_gate=use_plant_sn,
        plant_sn_refresh_every=50,
        out_dir=OUT_DIR,
    )
    after = ab._metrics(
        ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
    )
    v6_after = None
    if args.layer == "math_bank":
        try:
            v6_tensor = ab._ensure_mix_dataset()
            v6_val = load_split(
                v6_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True
            )
            v6_after = ab._metrics(
                ckpt,
                tok=tok,
                device=device,
                codex_val=codex_val,
                uml_val=v6_val,
                batch_size=args.batch_size,
            )
        except Exception as exc:
            v6_after = {"error": repr(exc)}
    delta = {
        "codex_acc": after["codex_acc"] - start["codex_acc"],
        "codex_nll": after["codex_nll"] - start["codex_nll"],
        "uml_acc": after["uml_acc"] - start["uml_acc"],
        "uml_nll": after["uml_nll"] - start["uml_nll"],
    }
    hold = delta["codex_acc"] >= -float(args.codex_hold_tol)
    uml_up = delta["uml_acc"] > 0.002 or delta["uml_nll"] < -0.01
    if not hold:
        objective = "FAIL_HOLD"
    elif uml_up:
        objective = "PASS"
    elif abs(delta["uml_acc"]) < 0.002 and abs(delta["uml_nll"]) < 0.01:
        objective = "TIE"
    else:
        objective = "INCONCLUSIVE"

    if args.commit_survivor and hold:
        shutil.copy2(ckpt, OUT_DIR / "layer_survivor.pt")

    receipt = {
        "schema_version": "uml_mix_layer_v1",
        "layer": args.layer,
        "status": "PASS",
        "objective": objective,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "hypothesis": {
            "long_steps": "More steps at locked mix improves UML without breaking Codex hold.",
            "soft_boost": "Softer prefer-cheap boost reduces Codex pressure / improves hold margin.",
            "math_bank": "Native UML math-token bank improves UML vs v6 prose-drill mix.",
            "plant_sn": (
                "Furnace-style master_rid S_n gate sheds UML mix dose under thermal stress "
                "while holding Codex and recovering v6 UML after native bank layer."
            ),
            "continue_train": (
                "Further matched steps at locked mix with plant_sn gate held improve "
                "UML without breaking Codex; speak cheap-rate secondary."
            ),
        }[args.layer],
        "config": {
            "mix_ratio": float(args.mix_ratio),
            "steps": int(args.steps),
            "prefer_cheap_boost": boost,
            "bank": bank_label,
            "plant_sn_gate": use_plant_sn,
            "lr": float(args.lr),
            "batch_size": int(args.batch_size),
            "warm_source": str(warm_src).replace("\\", "/"),
        },
        "codex_hold": hold,
        "start": start,
        "after": after,
        "delta": delta,
        "v6_continuity_after": v6_after,
        "mix_build": {
            "bank_version": mix_build.get("bank_version"),
            "dialogues": mix_build.get("dialogue_rows"),
        },
        "artifacts": {
            "warm": str(warm).replace("\\", "/"),
            "ckpt": str(ckpt).replace("\\", "/"),
            "survivor": str((OUT_DIR / "layer_survivor.pt")).replace("\\", "/"),
        },
        "device": str(device),
    }
    out_json = OUT_DIR / f"layer_{args.layer}_latest.json"
    out_md = OUT_DIR / f"layer_{args.layer}_latest.md"
    latest = SANDBOX / "runs" / f"uml_mix_layer_{args.layer}_latest.json"
    with out_json.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    shutil.copy2(out_json, latest)

    md = "\n".join(
        [
            f"# UML Mix Layer: {args.layer}",
            "",
            f"- Objective: **{objective}**",
            f"- Mix: {args.mix_ratio}",
            f"- Steps: {args.steps}",
            f"- Boost: {boost}",
            f"- Bank: {bank_label}",
            f"- Codex hold: {hold}",
            "",
            "## Delta (after - start)",
            f"- Codex acc {start['codex_acc']:.6f} -> {after['codex_acc']:.6f} ({delta['codex_acc']:+.6f})",
            f"- UML   acc {start['uml_acc']:.6f} -> {after['uml_acc']:.6f} ({delta['uml_acc']:+.6f})",
            f"- UML   nll {start['uml_nll']:.6f} -> {after['uml_nll']:.6f} ({delta['uml_nll']:+.6f})",
            "",
            f"Receipt: `{out_json.as_posix()}`",
            "",
        ]
    )
    out_md.write_text(md, encoding="utf-8", newline="\n")
    print(
        f"LAYER_{args.layer}_{objective} hold={hold} "
        f"uml_acc {start['uml_acc']:.6f}->{after['uml_acc']:.6f} d={delta['uml_acc']:+.6f} "
        f"codex_acc {start['codex_acc']:.6f}->{after['codex_acc']:.6f} d={delta['codex_acc']:+.6f}",
        flush=True,
    )
    return 0 if objective != "FAIL_HOLD" else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main())
