#!/usr/bin/env python3
"""Thicken native bank → train side ckpt → snap-free audit.

Does NOT commit layer_survivor unless native cheap_rate clears 0.5 AND Codex holds.
On GAP: leave survivor untouched; record that a real cost-winner path is still required.
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
OUT_DIR = SANDBOX / "runs" / "uml_native_thicken"
NATIVE_DIR = SANDBOX / "data" / "uml_native_math_tokens_v1"
SURVIVOR = SANDBOX / "runs" / "uml_mix_layers" / "layer_survivor.pt"
MIX_RECIPE = SANDBOX / "uml_mix_recipe.json"
RECIPE = SANDBOX / "uml_domain_expert_train_recipe.json"
RECEIPT_JSON = SANDBOX / "runs" / "uml_native_thicken_latest.json"
RECEIPT_MD = SANDBOX / "runs" / "uml_native_thicken_latest.md"
AUDIT = SANDBOX / "run_uml_snap_free_audit.py"

for p in (MODEL, SANDBOX, FOUNDATION):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

import run_uml_equation_ab as ab  # noqa: E402
import run_uml_snap_free_audit as snap  # noqa: E402


def _rebuild_bank(*, repeat: int) -> Path:
    subprocess.run(
        [str(PY), "-B", str(SANDBOX / "build_uml_native_math_tokens.py")],
        check=True,
        cwd=str(SANDBOX),
    )
    dialogues = NATIVE_DIR / "train_dialogues.txt"
    tensor = NATIVE_DIR / "tensor_dataset"
    # Force rebuild tensor
    if tensor.exists():
        shutil.rmtree(tensor)
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
            str(repeat),
        ],
        check=True,
        cwd=str(SANDBOX),
    )
    return tensor


def _audit_ckpt(ckpt: Path, tok, device) -> dict[str, Any]:
    from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry
    from sandbox_paths import EFFICIENT_CKPT

    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    model_e, _ = snap._load(EFFICIENT_CKPT, tok, torch.device("cpu"))
    model_d, payload = snap._load(ckpt, tok, device)
    english = snap._probe_english_prefer(model_e, model_d, tok, reg, device)
    native = snap._probe_native_no_snap(model_d, tok, reg, device)
    return {
        "english": english,
        "native": native,
        "leg": payload.get("leg") if isinstance(payload, dict) else None,
    }


def main() -> int:
    mix_recipe = ab.load_mix_recipe(MIX_RECIPE)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=8000)
    parser.add_argument("--mix-ratio", type=float, default=float(mix_recipe.get("mix_ratio", 0.779375)))
    parser.add_argument(
        "--prefer-cheap-boost",
        type=float,
        default=float(mix_recipe.get("prefer_cheap_boost", 1.5)),
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=7e-6)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--log-every", type=int, default=500)
    parser.add_argument("--codex-hold-tol", type=float, default=0.001)
    parser.add_argument("--repeat", type=int, default=64)
    parser.add_argument("--warm-ckpt", type=Path, default=SURVIVOR)
    parser.add_argument("--device", default="cuda")
    parser.add_argument(
        "--commit-survivor",
        action="store_true",
        help="Only commits if native PASS and Codex hold (still opt-in).",
    )
    args = parser.parse_args()

    if not Path(args.warm_ckpt).is_file():
        raise FileNotFoundError(args.warm_ckpt)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bank_meta = json.loads(
        (SANDBOX / "runs" / "uml_native_math_tokens_build_latest.json").read_text(encoding="utf-8")
    ) if (SANDBOX / "runs" / "uml_native_math_tokens_build_latest.json").is_file() else {}

    print("NATIVE_THICKEN_BUILD", flush=True)
    tensor = _rebuild_bank(repeat=int(args.repeat))
    bank_meta = json.loads(
        (SANDBOX / "runs" / "uml_native_math_tokens_build_latest.json").read_text(encoding="utf-8")
    )

    _, vocab_path, codex_tensor = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    if str(device).startswith("cuda") and not torch.cuda.is_available():
        device = torch.device("cpu")
    configure_plant_runtime(device=str(device))

    codex_train = load_split(codex_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True)
    codex_val = load_split(codex_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True)
    uml_train = load_split(tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True)
    uml_val = load_split(tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True)

    # Baseline audit on warm survivor
    print("NATIVE_THICKEN_BASELINE_AUDIT", flush=True)
    baseline = _audit_ckpt(Path(args.warm_ckpt), tok, device)

    warm = OUT_DIR / "warm_native_thicken.pt"
    shutil.copy2(args.warm_ckpt, warm)
    start = ab._metrics(
        warm, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
    )
    print(
        f"NATIVE_THICKEN_TRAIN steps={args.steps} mix={args.mix_ratio} "
        f"dialogues={bank_meta.get('n_dialogues')}",
        flush=True,
    )
    ckpt = ab._train_leg(
        name="native_thicken",
        warm_ckpt=warm,
        steps=int(args.steps),
        batch_size=int(args.batch_size),
        lr=float(args.lr),
        mix_ratio=float(args.mix_ratio),
        device=device,
        tok=tok,
        codex_train=codex_train,
        uml_train=uml_train,
        seed=int(args.seed) + 77,
        log_every=int(args.log_every),
        prefer_cheap_boost=float(args.prefer_cheap_boost),
        plant_sn_gate=True,
        out_dir=OUT_DIR,
    )
    after = ab._metrics(
        ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
    )
    hold = (after["codex_acc"] - start["codex_acc"]) >= -float(args.codex_hold_tol)

    print("NATIVE_THICKEN_POST_AUDIT", flush=True)
    post = _audit_ckpt(ckpt, tok, device)
    native_before = float(baseline["native"]["cheap_raw_rate"])
    native_after = float(post["native"]["cheap_raw_rate"])
    native_pass = post["native"]["status"] == "PASS"
    improved = native_after > native_before + 0.01

    if native_pass and hold:
        objective = "PASS"
        leave = False
        next_note = "Native snap-free cleared after thicken; optional survivor commit."
    elif hold and improved:
        objective = "GAP_IMPROVED"
        leave = True
        next_note = (
            "Thicken helped but native still below 0.5. Leave survivor; "
            "need a real cost-winner (registry/route economics), not more bank weight alone."
        )
    else:
        objective = "GAP_LEAVE"
        leave = True
        next_note = (
            "Thicken did not close native snap-free. Leave as-is. "
            "Need a real promotion/cost winner — bank thickening is not the bottleneck."
        )

    committed = False
    if args.commit_survivor and objective == "PASS" and hold:
        shutil.copy2(ckpt, SURVIVOR)
        committed = True

    finished = datetime.now(timezone.utc).isoformat()
    receipt = {
        "schema_version": "uml_native_thicken_v1",
        "status": "PASS",
        "objective": objective,
        "leave_survivor_untouched": leave and not committed,
        "committed_survivor": committed,
        "hypothesis": (
            "Thickening costly→cheap native repairs raises no-snap cheap_rate to >=0.5 "
            "without English Prefer-efficient crutches."
        ),
        "hypothesis_supported": objective == "PASS",
        "finished_at": finished,
        "bank": bank_meta,
        "train": {
            "steps": int(args.steps),
            "mix_ratio": float(args.mix_ratio),
            "codex_hold": hold,
            "start": start,
            "after": after,
            "delta_uml_acc": after["uml_acc"] - start["uml_acc"],
            "delta_codex_acc": after["codex_acc"] - start["codex_acc"],
            "ckpt": str(ckpt).replace("\\", "/"),
        },
        "baseline_audit": {
            "english_cheap": baseline["english"]["cheap_raw_rate"],
            "native_cheap": native_before,
            "native_status": baseline["native"]["status"],
        },
        "post_audit": {
            "english_cheap": post["english"]["cheap_raw_rate"],
            "native_cheap": native_after,
            "native_status": post["native"]["status"],
            "english": post["english"],
            "native": post["native"],
        },
        "delta_native_cheap": native_after - native_before,
        "next": next_note,
        "device": str(device),
    }
    RECEIPT_JSON.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    md = "\n".join(
        [
            "# Native UML Thicken (snap-free)",
            "",
            f"- Objective: **{objective}**",
            f"- Native cheap: {native_before:.3f} → {native_after:.3f} "
            f"(Δ {native_after - native_before:+.3f})",
            f"- English cheap (post): {post['english']['cheap_raw_rate']:.3f}",
            f"- Codex hold: {hold}",
            f"- Survivor committed: {committed}",
            f"- Leave untouched: {leave and not committed}",
            f"- Next: {next_note}",
            "",
            f"Receipt: `{RECEIPT_JSON.as_posix()}`",
            "",
        ]
    )
    RECEIPT_MD.write_text(md, encoding="utf-8", newline="\n")

    # Also refresh main snap-free audit only if we committed; else write side note in recipe.
    if RECIPE.is_file():
        recipe = json.loads(RECIPE.read_text(encoding="utf-8"))
        recipe["last_run"] = finished
        recipe["last_objective"] = objective
        recipe["native_thicken"] = {
            "objective": objective,
            "native_before": native_before,
            "native_after": native_after,
            "leave": leave and not committed,
            "receipt": str(RECEIPT_JSON).replace("\\", "/"),
        }
        if leave:
            recipe["next_action"] = (
                "Native thicken left GAP. Hunt real cost-winner for promotion "
                "(registry/route economics where mixed federation beats mono/LIT)."
            )
            recipe["binding_read"]["not_yet"] = (
                "Persistent composites empty; native snap-free still weak after thicken."
            )
        else:
            recipe["next_action"] = (
                "Native snap-free PASS after thicken. Optional survivor commit already handled."
            )
        RECIPE.write_text(
            json.dumps(recipe, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    print(
        f"UML_NATIVE_THICKEN_{objective} native {native_before:.3f}->{native_after:.3f} "
        f"hold={hold} leave={leave and not committed}",
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
