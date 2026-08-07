#!/usr/bin/env python3
"""Blend ID mix + OOD train to recover ID UML while keeping OOD competence.

Default recipe (items 69–73): auto heldout + ood-fraction=0.25.
Old full-OOD simultaneous blend: --ood-fraction 1.0 --no-heldout-tensor.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
PY = Path(r"L:\Continue\.venv\Scripts\python.exe")
SURVIVOR = SANDBOX / "runs" / "uml_mix_layers" / "layer_survivor.pt"
OUT = SANDBOX / "runs" / "uml_ood_blend_recover"
OOD_TENSOR = SANDBOX / "data" / "uml_ood_probe_v1" / "tensor_dataset"
DEFAULT_HELDOUT_TENSOR = SANDBOX / "data" / "uml_real_heldout_v1" / "tensor_A_after"

for p in (FOUNDATION, MODEL, SANDBOX):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
import run_uml_equation_ab as ab  # noqa: E402


def _cat_split(a, b):
    ai, at, am = a
    bi, bt, bm = b
    mask = None
    if am is not None and bm is not None:
        mask = torch.cat([am, bm], 0)
    return (torch.cat([ai, bi], 0), torch.cat([at, bt], 0), mask)


def _frac_split(split, fraction: float, *, seed: int = 120):
    """Deterministic row subsample; fraction in (0, 1]. fraction<=0 -> empty-ish skip upstream."""
    inputs, targets, mask = split
    n = int(inputs.shape[0])
    if n <= 0 or fraction >= 1.0:
        return split
    k = max(1, int(round(n * float(fraction))))
    k = min(k, n)
    g = torch.Generator()
    g.manual_seed(int(seed))
    idx = torch.randperm(n, generator=g)[:k]
    m = None if mask is None else mask[idx]
    return (inputs[idx], targets[idx], m)


def _resolve_heldout(args: argparse.Namespace) -> tuple[Path | None, bool]:
    """Return (heldout_path, auto_heldout). Explicit --heldout-tensor wins."""
    if args.heldout_tensor is not None:
        return Path(args.heldout_tensor), False
    if bool(args.no_heldout_tensor):
        return None, False
    if DEFAULT_HELDOUT_TENSOR.is_dir():
        return DEFAULT_HELDOUT_TENSOR, True
    return None, False


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=(
            "OOD blend recover. Default: auto heldout + ood-fraction=0.25 "
            "(BLEND_PRESERVE_HELDOUT recipe)."
        )
    )
    ap.add_argument("--mix-ratio", type=float, default=0.55)
    ap.add_argument("--prefer-cheap-boost", type=float, default=1.5)
    ap.add_argument(
        "--heldout-tensor",
        type=Path,
        default=None,
        help=(
            "Heldout tensor dir to concat into UML train. "
            f"Default when present: {DEFAULT_HELDOUT_TENSOR.as_posix()}"
        ),
    )
    ap.add_argument(
        "--no-heldout-tensor",
        action="store_true",
        help="Disable auto-include of default heldout tensor when present.",
    )
    ap.add_argument(
        "--no-ood-concat",
        action="store_true",
        help=(
            "If set, do not concat ood_train (ood_fraction effectively 0; "
            "extreme heldout-only experiment)."
        ),
    )
    ap.add_argument(
        "--ood-fraction",
        type=float,
        default=0.25,
        help=(
            "Fraction of ood_train rows to concat when OOD concat is on (0.0–1.0). "
            "Default 0.25. Use 1.0 for old full-OOD recipe."
        ),
    )
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=120)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not (0.0 <= float(args.ood_fraction) <= 1.0):
        raise SystemExit(f"--ood-fraction must be in [0,1], got {args.ood_fraction}")

    OUT.mkdir(parents=True, exist_ok=True)
    if not SURVIVOR.is_file():
        raise FileNotFoundError(SURVIVOR)

    _, vocab_path, codex_tensor = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    configure_plant_runtime(device=str(device))

    codex_train = load_split(
        codex_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True
    )
    codex_val = load_split(
        codex_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True
    )
    mix_tensor = ab._ensure_mix_dataset()
    mix_train = load_split(
        mix_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True
    )
    mix_val = load_split(
        mix_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True
    )

    uml_train = mix_train
    ood_rows = 0
    if not args.no_ood_concat and float(args.ood_fraction) > 0.0:
        ood_train = load_split(
            OOD_TENSOR, "train", vocab_size=tok.vocab_size, response_only_loss=True
        )
        if float(args.ood_fraction) < 1.0:
            ood_train = _frac_split(ood_train, float(args.ood_fraction), seed=int(args.seed))
        ood_rows = int(ood_train[0].shape[0])
        uml_train = _cat_split(uml_train, ood_train)

    heldout_rows = 0
    heldout_path, auto_heldout = _resolve_heldout(args)
    if heldout_path is not None:
        if not heldout_path.is_dir():
            raise FileNotFoundError(heldout_path)
        held_train = load_split(
            heldout_path, "train", vocab_size=tok.vocab_size, response_only_loss=True
        )
        heldout_rows = int(held_train[0].shape[0])
        uml_train = _cat_split(uml_train, held_train)

    print(
        f"BLEND_CONFIG heldout_rows={heldout_rows} ood_rows={ood_rows} "
        f"ood_fraction={float(args.ood_fraction)} "
        f"auto_heldout={'yes' if auto_heldout else 'no'} "
        f"no_ood_concat={bool(args.no_ood_concat)} "
        f"heldout_tensor="
        f"{'none' if heldout_path is None else str(heldout_path).replace(chr(92), '/')}",
        flush=True,
    )

    start = ab._metrics(
        SURVIVOR,
        tok=tok,
        device=device,
        codex_val=codex_val,
        uml_val=mix_val,
        batch_size=64,
    )
    print(
        f"BLEND_START codex={start['codex_acc']:.4f} "
        f"id_uml={start['uml_acc']:.6f} (print {start['uml_acc']:.3f})",
        flush=True,
    )
    warm = OUT / "warm.pt"
    shutil.copy2(SURVIVOR, warm)
    ckpt = ab._train_leg(
        name="ood_blend_recover",
        warm_ckpt=warm,
        steps=int(args.steps),
        batch_size=64,
        lr=7e-6,
        mix_ratio=float(args.mix_ratio),
        device=device,
        tok=tok,
        codex_train=codex_train,
        uml_train=uml_train,
        seed=int(args.seed),
        log_every=500,
        prefer_cheap_boost=float(args.prefer_cheap_boost),
        rid_residual_weight=0.0,
        thermal_route_weight=0.0,
        plant_sn_gate=False,
        out_dir=OUT,
    )
    after = ab._metrics(
        ckpt,
        tok=tok,
        device=device,
        codex_val=codex_val,
        uml_val=mix_val,
        batch_size=64,
    )
    d_codex = after["codex_acc"] - start["codex_acc"]
    print(
        f"BLEND_AFTER codex={after['codex_acc']:.4f} "
        f"id_uml={after['uml_acc']:.6f} (print {after['uml_acc']:.3f}) "
        f"d_codex={d_codex:+.4f}",
        flush=True,
    )

    subprocess.run(
        [
            str(PY),
            "-B",
            str(SANDBOX / "run_uml_ood_probe.py"),
            "--ckpt",
            str(ckpt),
            "--n-surfaces",
            "256",
            "--seed",
            "20260810",
            "--device",
            "cuda",
        ],
        check=True,
        cwd=str(SANDBOX),
    )
    ood = json.loads(
        (SANDBOX / "runs" / "uml_ood_probe_latest.json").read_text(encoding="utf-8")
    )
    hold = d_codex >= -0.001
    ood_acc = float(ood["ood_metrics"]["uml_acc"])
    match = float(ood["ood_speak"]["match_rate"])
    id_up = after["uml_acc"] >= start["uml_acc"] - 0.01

    if hold and match >= 0.9 and ood_acc >= 0.70 and after["uml_acc"] > start["uml_acc"]:
        objective = "PASS_BLEND"
    elif hold and match >= 0.9 and ood_acc >= 0.70:
        objective = "PASS_BLEND_HOLD_OOD"
    else:
        objective = "TIE_OR_FAIL"

    committed = False
    if hold and match >= 0.9 and ood_acc >= 0.70 and id_up:
        shutil.copy2(ckpt, SURVIVOR)
        committed = True

    finished_at = datetime.now(timezone.utc)
    receipt = {
        "schema_version": "uml_ood_blend_recover_v1",
        "finished_at": finished_at.isoformat(),
        "objective": objective,
        "blend_config": {
            "mix_ratio": float(args.mix_ratio),
            "prefer_cheap_boost": float(args.prefer_cheap_boost),
            "no_ood_concat": bool(args.no_ood_concat),
            "ood_fraction": float(args.ood_fraction),
            "ood_rows": ood_rows,
            "auto_heldout": bool(auto_heldout),
            "heldout_tensor": None
            if heldout_path is None
            else str(heldout_path).replace("\\", "/"),
            "heldout_rows": heldout_rows,
            "steps": int(args.steps),
            "seed": int(args.seed),
        },
        "start": start,
        "after": after,
        "delta_codex": d_codex,
        "delta_id_uml": after["uml_acc"] - start["uml_acc"],
        "fresh_ood_C": {
            "uml_acc": ood_acc,
            "speak_match": match,
            "speak_cheap": ood["ood_speak"]["cheap_rate"],
            "seed": 20260810,
        },
        "survivor_committed": committed,
        "ckpt": str(ckpt).replace("\\", "/"),
    }
    text = json.dumps(receipt, indent=2, sort_keys=True)
    stamp = finished_at.strftime("%Y%m%dT%H%M%SZ")
    (OUT / "blend_recover_latest.json").write_text(text + "\n", encoding="utf-8")
    (OUT / f"blend_recover_{stamp}.json").write_text(text + "\n", encoding="utf-8")
    (SANDBOX / "runs" / "uml_ood_blend_recover_latest.json").write_text(
        text + "\n", encoding="utf-8"
    )
    print(
        f"BLEND_{objective} id_uml {start['uml_acc']:.6f}->{after['uml_acc']:.6f} "
        f"(print {start['uml_acc']:.3f}->{after['uml_acc']:.3f}) "
        f"oodC={ood_acc:.3f} match={match:.3f} committed={committed}",
        flush=True,
    )
    return 0 if objective.startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
