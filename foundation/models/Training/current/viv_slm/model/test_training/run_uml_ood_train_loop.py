#!/usr/bin/env python3
"""OOD train loop: measure never-seen → train on it → measure again (+ fresh holdout).

Protocol:
  1) Probe set A (seed_a) on warm survivor — baseline
  2) Train +N steps on set-A OOD dialogues (response-masked)
  3) Re-probe set A (seen during train) and set B (new seed, never trained)
  4) Codex hold vs warm; speak match must stay high

Does not commit survivor unless --commit-survivor and gates pass.
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
SURVIVOR = SANDBOX / "runs" / "uml_mix_layers" / "layer_survivor.pt"
OUT = SANDBOX / "runs" / "uml_ood_train_loop"
RECIPE = SANDBOX / "uml_mix_recipe.json"
PROBE = SANDBOX / "run_uml_ood_probe.py"

for p in (FOUNDATION, MODEL, SANDBOX):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
import run_uml_equation_ab as ab  # noqa: E402


def _run_probe(
    *,
    ckpt: Path,
    seed: int,
    n_surfaces: int,
    tag: str,
    device: str,
    hard: bool = False,
) -> dict[str, Any]:
    # Probe always writes uml_ood_probe_latest.json; copy aside per tag.
    cmd = [
        str(PY),
        "-B",
        str(PROBE),
        "--ckpt",
        str(ckpt),
        "--n-surfaces",
        str(n_surfaces),
        "--seed",
        str(seed),
        "--device",
        device,
    ]
    if hard:
        cmd.append("--hard")
    subprocess.run(cmd, check=True, cwd=str(SANDBOX))
    latest = SANDBOX / "runs" / "uml_ood_probe_latest.json"
    data = json.loads(latest.read_text(encoding="utf-8"))
    tagged = OUT / f"probe_{tag}.json"
    tagged.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def _slice(probe: dict[str, Any]) -> dict[str, Any]:
    return {
        "objective": probe.get("objective"),
        "uml_acc": probe["ood_metrics"]["uml_acc"],
        "uml_nll": probe["ood_metrics"]["uml_nll"],
        "codex_acc": probe["ood_metrics"]["codex_acc"],
        "speak_match": probe["ood_speak"]["match_rate"],
        "speak_cheap": probe["ood_speak"]["cheap_rate"],
        "seal_rate": probe["surface_seal"]["rate"],
        "ood_surfaces": probe["ood_surfaces"],
        "surfaces_sha256": probe["artifacts"]["surfaces_sha256"],
    }


def main() -> int:
    recipe = ab.load_mix_recipe(RECIPE)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warm", type=Path, default=SURVIVOR)
    parser.add_argument("--steps", type=int, default=3000)
    parser.add_argument("--n-surfaces", type=int, default=128)
    parser.add_argument("--seed-a", type=int, default=20260806)
    parser.add_argument("--seed-b", type=int, default=20260807)
    parser.add_argument("--mix-ratio", type=float, default=float(recipe.get("mix_ratio", 0.779375)))
    parser.add_argument(
        "--prefer-cheap-boost",
        type=float,
        default=float(recipe.get("prefer_cheap_boost", 1.5)),
    )
    parser.add_argument("--batch-size", type=int, default=int(recipe.get("batch_size", 64)))
    parser.add_argument("--lr", type=float, default=float(recipe.get("lr", 7e-6)))
    parser.add_argument("--seed", type=int, default=int(recipe.get("seed", 42)) + 21)
    parser.add_argument("--log-every", type=int, default=500)
    parser.add_argument("--codex-hold-tol", type=float, default=0.001)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--hard", action="store_true", help="Use harder OOD surface generator")
    parser.add_argument("--commit-survivor", action="store_true")
    args = parser.parse_args()

    if not args.warm.is_file():
        raise FileNotFoundError(args.warm)
    OUT.mkdir(parents=True, exist_ok=True)

    print("OOD_LOOP_1_BASELINE_A", flush=True)
    base_a = _run_probe(
        ckpt=args.warm,
        seed=int(args.seed_a),
        n_surfaces=int(args.n_surfaces),
        tag="A_baseline",
        device=str(args.device),
        hard=bool(args.hard),
    )
    # Training tensor from the A probe pack written by run_uml_ood_probe.
    ood_tensor = SANDBOX / "data" / "uml_ood_probe_v1" / "tensor_dataset"
    if not (ood_tensor / "MANIFEST.json").is_file():
        raise FileNotFoundError(ood_tensor)

    _, vocab_path, codex_tensor = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    if str(device).startswith("cuda") and not torch.cuda.is_available():
        device = torch.device("cpu")
    configure_plant_runtime(device=str(device))

    codex_train = load_split(codex_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True)
    codex_val = load_split(codex_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True)
    ood_train = load_split(ood_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True)
    mix_val = load_split(
        ab._ensure_mix_dataset(), "validation", vocab_size=tok.vocab_size, response_only_loss=True
    )

    start = ab._metrics(
        args.warm, tok=tok, device=device, codex_val=codex_val, uml_val=mix_val, batch_size=args.batch_size
    )

    print(
        f"OOD_LOOP_2_TRAIN steps={args.steps} mix={args.mix_ratio} "
        f"boost={args.prefer_cheap_boost} uml_ood_base={base_a['ood_metrics']['uml_acc']:.3f}",
        flush=True,
    )
    warm = OUT / "warm_ood_loop.pt"
    shutil.copy2(args.warm, warm)
    # Blend: mostly OOD train, light Codex — use mix_ratio as UML/OOD fraction.
    ckpt = ab._train_leg(
        name="ood_train_loop",
        warm_ckpt=warm,
        steps=int(args.steps),
        batch_size=int(args.batch_size),
        lr=float(args.lr),
        mix_ratio=float(args.mix_ratio),
        device=device,
        tok=tok,
        codex_train=codex_train,
        uml_train=ood_train,
        seed=int(args.seed),
        log_every=int(args.log_every),
        prefer_cheap_boost=float(args.prefer_cheap_boost),
        rid_residual_weight=0.0,
        thermal_route_weight=0.0,
        plant_sn_gate=False,
        out_dir=OUT,
    )
    after = ab._metrics(
        ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=mix_val, batch_size=args.batch_size
    )

    # Auto Codex recover when hold would fail (common after OOD-heavy mix).
    d_codex_pre = after["codex_acc"] - start["codex_acc"]
    recovered = False
    if d_codex_pre < -float(args.codex_hold_tol):
        print(
            f"OOD_LOOP_2b_CODEX_RECOVER d_codex={d_codex_pre:+.4f} → +1000 mix=0",
            flush=True,
        )
        warm_r = OUT / "warm_codex_recover.pt"
        shutil.copy2(ckpt, warm_r)
        ckpt = ab._train_leg(
            name="ood_codex_recover",
            warm_ckpt=warm_r,
            steps=1000,
            batch_size=int(args.batch_size),
            lr=float(args.lr),
            mix_ratio=0.0,
            device=device,
            tok=tok,
            codex_train=codex_train,
            uml_train=codex_train,
            seed=int(args.seed) + 7,
            log_every=int(args.log_every),
            prefer_cheap_boost=1.0,
            rid_residual_weight=0.0,
            thermal_route_weight=0.0,
            plant_sn_gate=False,
            out_dir=OUT,
        )
        after = ab._metrics(
            ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=mix_val, batch_size=args.batch_size
        )
        recovered = True

    print("OOD_LOOP_3_REPROBE_A", flush=True)
    # Rebuild A with same seed so surfaces match baseline SHA when possible.
    post_a = _run_probe(
        ckpt=ckpt,
        seed=int(args.seed_a),
        n_surfaces=int(args.n_surfaces),
        tag="A_after",
        device=str(args.device),
        hard=bool(args.hard),
    )
    print("OOD_LOOP_4_FRESH_B", flush=True)
    post_b = _run_probe(
        ckpt=ckpt,
        seed=int(args.seed_b),
        n_surfaces=int(args.n_surfaces),
        tag="B_fresh",
        device=str(args.device),
        hard=bool(args.hard),
    )

    d_codex = after["codex_acc"] - start["codex_acc"]
    hold = d_codex >= -float(args.codex_hold_tol)
    a0 = float(base_a["ood_metrics"]["uml_acc"])
    a1 = float(post_a["ood_metrics"]["uml_acc"])
    b1 = float(post_b["ood_metrics"]["uml_acc"])
    match_a = float(post_a["ood_speak"]["match_rate"])
    match_b = float(post_b["ood_speak"]["match_rate"])
    sha_a0 = base_a["artifacts"]["surfaces_sha256"]
    sha_a1 = post_a["artifacts"]["surfaces_sha256"]
    same_a = sha_a0 == sha_a1

    if not hold or match_a < 0.9 or match_b < 0.9:
        objective = "FAIL_HOLD_OR_MATCH"
    elif (a1 - a0) >= 0.10 and b1 >= a0 + 0.05:
        objective = "PASS_OOD_GENERALIZE"
    elif (a1 - a0) >= 0.10 and b1 < a0 + 0.05:
        objective = "PASS_OOD_FIT_A_ONLY"
    elif (a1 - a0) > 0.02:
        objective = "PASS_OOD_MILD_LIFT"
    else:
        objective = "TIE_NO_OOD_LIFT"

    if args.commit_survivor and objective.startswith("PASS") and hold:
        shutil.copy2(ckpt, SURVIVOR)

    receipt = {
        "schema_version": "uml_ood_train_loop_v1",
        "experiment_id": "uml_ood_train_loop_v1",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "objective": objective,
        "hypothesis": (
            "Training on never-seen OOD set A raises OOD UML acc; "
            "fresh set B tells fit vs generalize. Speak match + Codex must hold."
        ),
        "config": {
            "steps": int(args.steps),
            "mix_ratio": float(args.mix_ratio),
            "prefer_cheap_boost": float(args.prefer_cheap_boost),
            "n_surfaces": int(args.n_surfaces),
            "seed_a": int(args.seed_a),
            "seed_b": int(args.seed_b),
            "hard": bool(args.hard),
            "warm": str(args.warm).replace("\\", "/"),
        },
        "codex_hold": hold,
        "codex_recovered": recovered,
        "set_a_surfaces_match": same_a,
        "start_id_metrics": start,
        "after_id_metrics": after,
        "delta_id": {
            "codex_acc": d_codex,
            "uml_acc": after["uml_acc"] - start["uml_acc"],
        },
        "baseline_A": _slice(base_a),
        "after_A": _slice(post_a),
        "fresh_B": _slice(post_b),
        "delta_ood": {
            "A_uml_acc": a1 - a0,
            "B_uml_acc_vs_A_baseline": b1 - a0,
            "A_speak_match": match_a - float(base_a["ood_speak"]["match_rate"]),
        },
        "artifacts": {
            "ckpt": str(ckpt).replace("\\", "/"),
            "out_dir": str(OUT).replace("\\", "/"),
            "survivor_committed": bool(
                args.commit_survivor and objective.startswith("PASS") and hold
            ),
        },
    }
    text = json.dumps(receipt, indent=2, sort_keys=True)
    (OUT / "ood_train_loop_latest.json").write_text(text + "\n", encoding="utf-8")
    (SANDBOX / "runs" / "uml_ood_train_loop_latest.json").write_text(text + "\n", encoding="utf-8")

    md = "\n".join(
        [
            "# OOD train loop",
            "",
            f"**Objective:** `{objective}`",
            "",
            "| Stage | UML OOD acc | Speak match | Cheap |",
            "|-------|------------:|------------:|------:|",
            f"| A baseline | {a0:.3f} | {base_a['ood_speak']['match_rate']:.3f} | {base_a['ood_speak']['cheap_rate']:.3f} |",
            f"| A after train | {a1:.3f} | {match_a:.3f} | {post_a['ood_speak']['cheap_rate']:.3f} |",
            f"| B fresh | {b1:.3f} | {match_b:.3f} | {post_b['ood_speak']['cheap_rate']:.3f} |",
            "",
            f"- Codex hold: {hold} (Δ {d_codex:+.4f})",
            f"- Set A surface SHA stable: {same_a}",
            f"- Survivor committed: {receipt['artifacts']['survivor_committed']}",
            "",
        ]
    )
    (OUT / "ood_train_loop_latest.md").write_text(md, encoding="utf-8")
    (SANDBOX / "runs" / "uml_ood_train_loop_latest.md").write_text(md, encoding="utf-8")
    print(
        f"OOD_LOOP_{objective} A {a0:.3f}->{a1:.3f} B={b1:.3f} "
        f"matchA={match_a:.3f} matchB={match_b:.3f} hold={hold} d_codex={d_codex:+.4f}",
        flush=True,
    )
    return 0 if objective != "FAIL_HOLD_OR_MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
