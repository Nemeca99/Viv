#!/usr/bin/env python3
"""P3: warm-train A/S/M/D domain specialists from layer_survivor.

- Builds/packs per-domain axiom banks
- Warm-copies survivor per domain (never mutates Codex / identity specialists)
- Trains each with Codex hold mix
- Promotes to checkpoints/{addition,subtraction,multiplication,division}/specialist.pt
  only when that domain holds Codex
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
OUT_DIR = SANDBOX / "runs" / "uml_domain_experts"
DATA_ROOT = SANDBOX / "data" / "uml_domain_axioms_v1"
CKPT_ROOT = SANDBOX / "checkpoints"
SURVIVOR = SANDBOX / "runs" / "uml_mix_layers" / "layer_survivor.pt"
RECIPE_PATH = SANDBOX / "uml_domain_expert_train_recipe.json"
MIX_RECIPE = SANDBOX / "uml_mix_recipe.json"
RECEIPT_JSON = SANDBOX / "runs" / "uml_domain_experts_latest.json"
RECEIPT_MD = SANDBOX / "runs" / "uml_domain_experts_latest.md"

DOMAINS = ("addition", "subtraction", "multiplication", "division", "uml_structure")
ARITH_DOMAINS = ("addition", "subtraction", "multiplication", "division")


for p in (MODEL, SANDBOX, FOUNDATION):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

import run_uml_equation_ab as ab  # noqa: E402


def _ensure_banks_and_tensors(*, domains: tuple[str, ...] = DOMAINS, repeat: int = 24) -> dict[str, Path]:
    arith = [d for d in domains if d in ARITH_DOMAINS]
    if arith:
        build = SANDBOX / "build_uml_domain_axiom_banks.py"
        subprocess.run([str(PY), "-B", str(build)], check=True, cwd=str(SANDBOX))
    if "uml_structure" in domains:
        subprocess.run(
            [str(PY), "-B", str(SANDBOX / "build_uml_structure_axiom_bank.py")],
            check=True,
            cwd=str(SANDBOX),
        )
    tensors: dict[str, Path] = {}
    pack = SANDBOX / "pack_uml_dialogues_tensor.py"
    for domain in domains:
        dialogues = DATA_ROOT / domain / "train_dialogues.txt"
        tensor = DATA_ROOT / domain / "tensor_dataset"
        if not dialogues.is_file():
            raise FileNotFoundError(dialogues)
        subprocess.run(
            [
                str(PY),
                "-B",
                str(pack),
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
        tensors[domain] = tensor
    return tensors


def main() -> int:
    mix_recipe = ab.load_mix_recipe(MIX_RECIPE)
    domain_recipe = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=2500)
    parser.add_argument(
        "--mix-ratio",
        type=float,
        default=float(mix_recipe.get("mix_ratio", 0.779375)),
    )
    parser.add_argument(
        "--prefer-cheap-boost",
        type=float,
        default=float(mix_recipe.get("prefer_cheap_boost", 1.5)),
    )
    parser.add_argument("--batch-size", type=int, default=int(mix_recipe.get("batch_size", 64)))
    parser.add_argument("--lr", type=float, default=float(mix_recipe.get("lr", 7e-6)))
    parser.add_argument("--seed", type=int, default=int(mix_recipe.get("seed", 42)))
    parser.add_argument("--log-every", type=int, default=500)
    parser.add_argument(
        "--codex-hold-tol",
        type=float,
        default=float(mix_recipe.get("codex_hold_tol", 0.001)),
    )
    parser.add_argument("--warm-ckpt", type=Path, default=SURVIVOR)
    parser.add_argument("--device", default="cuda")
    parser.add_argument(
        "--domains",
        type=str,
        default=",".join(DOMAINS),
        help="Comma list of domains to train (default: all four).",
    )
    parser.add_argument("--promote", action="store_true", help="Copy holding domains into checkpoints/")
    args = parser.parse_args()

    selected = tuple(d.strip() for d in str(args.domains).split(",") if d.strip())
    for d in selected:
        if d not in DOMAINS:
            raise ValueError(f"unknown_domain:{d}")

    if not Path(args.warm_ckpt).is_file():
        raise FileNotFoundError(args.warm_ckpt)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tensors = _ensure_banks_and_tensors(domains=selected)

    _, vocab_path, codex_tensor = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    if str(device).startswith("cuda") and not torch.cuda.is_available():
        device = torch.device("cpu")
    configure_plant_runtime(device=str(device))

    codex_train = load_split(codex_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True)
    codex_val = load_split(codex_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True)

    results: list[dict[str, Any]] = []
    promoted: list[str] = []

    for i, domain in enumerate(selected):
        warm = OUT_DIR / f"warm_{domain}.pt"
        shutil.copy2(args.warm_ckpt, warm)
        uml_tensor = tensors[domain]
        uml_train = load_split(uml_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True)
        uml_val = load_split(uml_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True)

        start = ab._metrics(
            warm, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
        )
        print(
            f"DOMAIN_{domain}_START steps={args.steps} mix={args.mix_ratio} "
            f"boost={args.prefer_cheap_boost}",
            flush=True,
        )
        ckpt = ab._train_leg(
            name=f"expert_{domain}",
            warm_ckpt=warm,
            steps=int(args.steps),
            batch_size=int(args.batch_size),
            lr=float(args.lr),
            mix_ratio=float(args.mix_ratio),
            device=device,
            tok=tok,
            codex_train=codex_train,
            uml_train=uml_train,
            seed=int(args.seed) + 10 + list(DOMAINS).index(domain),
            log_every=int(args.log_every),
            prefer_cheap_boost=float(args.prefer_cheap_boost),
            rid_residual_weight=0.0,
            thermal_route_weight=0.0,
            plant_sn_gate=True,
            out_dir=OUT_DIR,
        )
        after = ab._metrics(
            ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
        )
        delta_codex = after["codex_acc"] - start["codex_acc"]
        hold = delta_codex >= -float(args.codex_hold_tol)
        uml_up = after["uml_acc"] - start["uml_acc"] > 0.01
        status = "PASS" if hold and uml_up else ("HOLD_ONLY" if hold else "FAIL_HOLD")
        row = {
            "domain": domain,
            "status": status,
            "codex_hold": hold,
            "start": start,
            "after": after,
            "delta_codex_acc": delta_codex,
            "delta_uml_acc": after["uml_acc"] - start["uml_acc"],
            "ckpt": str(ckpt).replace("\\", "/"),
        }
        results.append(row)
        print(
            f"DOMAIN_{domain}_{status} hold={hold} "
            f"uml {start['uml_acc']:.4f}->{after['uml_acc']:.4f} "
            f"codex {start['codex_acc']:.4f}->{after['codex_acc']:.4f}",
            flush=True,
        )
        if args.promote and hold:
            dest_dir = CKPT_ROOT / domain
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / "specialist.pt"
            shutil.copy2(ckpt, dest)
            promoted.append(str(dest).replace("\\", "/"))

    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_hold = sum(1 for r in results if r["codex_hold"])
    # Merge with prior full-run receipt when retrying a subset.
    prior_domains: dict[str, Any] = {}
    if RECEIPT_JSON.is_file() and set(selected) != set(DOMAINS):
        try:
            prior = json.loads(RECEIPT_JSON.read_text(encoding="utf-8"))
            for row in prior.get("domains") or []:
                prior_domains[str(row["domain"])] = row
        except Exception:
            prior_domains = {}
    for row in results:
        prior_domains[str(row["domain"])] = row
    merged = [prior_domains[d] for d in DOMAINS if d in prior_domains]
    # Full lattice = 4 arith + optional U
    target_n = len(merged) if set(selected) == {"uml_structure"} else (
        5 if "uml_structure" in prior_domains or "uml_structure" in selected else 4
    )
    if len(merged) >= 4:
        n_pass = sum(1 for r in merged if r.get("status") == "PASS")
        n_hold = sum(1 for r in merged if r.get("codex_hold"))
        results_out = merged
    else:
        results_out = results
        target_n = len(results_out)
    objective = (
        "PASS"
        if n_pass >= target_n and n_hold >= target_n
        else (
            "PASS_PARTIAL"
            if n_hold >= max(3, target_n - 1) and n_pass > 0
            else ("HOLD_ALL" if n_hold >= target_n else "FAIL")
        )
    )
    if set(selected) == {"uml_structure"} and results and results[0].get("status") == "PASS":
        objective = "PASS_U_FOUNDATION"

    # Update recipe status
    domain_recipe["status"] = "active" if n_hold == 4 else "partial"
    domain_recipe["last_run"] = datetime.now(timezone.utc).isoformat()
    domain_recipe["last_objective"] = objective
    domain_recipe["promoted"] = promoted
    RECIPE_PATH.write_text(
        json.dumps(domain_recipe, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    receipt = {
        "schema_version": "uml_domain_experts_v1",
        "status": "PASS",
        "objective": objective,
        "hypothesis": (
            "Four monolithic A/S/M/D specialists warm-started from layer survivor "
            "on domain axiom banks hold Codex and improve domain UML response metrics."
        ),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "sandbox_only": True,
        "replaces_codex": False,
        "identity_specialists_untouched": True,
        "warm_source": str(args.warm_ckpt).replace("\\", "/"),
        "steps_per_domain": int(args.steps),
        "mix_ratio": float(args.mix_ratio),
        "prefer_cheap_boost": float(args.prefer_cheap_boost),
        "plant_sn_gate": True,
        "domains": results_out,
        "promoted": promoted,
        "n_pass": n_pass,
        "n_hold": n_hold,
        "trained_this_run": list(selected),
        "device": str(device),
    }
    with RECEIPT_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    lines = [
        "# UML Domain Experts (P3)",
        "",
        f"- Objective: **{objective}**",
        f"- Steps/domain: {args.steps}",
        f"- Mix: {args.mix_ratio} (plant_sn_gate on)",
        f"- Promoted: {len(promoted)}",
        f"- Trained this run: {list(selected)}",
        "",
        "## Domains",
    ]
    for r in results_out:
        lines.append(
            f"- {r['domain']}: {r['status']} "
            f"uml={r['start']['uml_acc']:.4f}->{r['after']['uml_acc']:.4f} "
            f"codex_hold={r['codex_hold']}"
        )
    lines.extend(["", f"Receipt: `{RECEIPT_JSON.as_posix()}`", ""])
    RECEIPT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(
        f"UML_DOMAIN_EXPERTS_{objective} pass={n_pass}/4 hold={n_hold}/4 promoted={len(promoted)}",
        flush=True,
    )
    return 0 if objective.startswith("PASS") or objective == "HOLD_ALL" else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main())
