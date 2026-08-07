#!/usr/bin/env python3
"""Train temporary U+<arith> federations from live foundation checkpoints.

Warm-start from U (mandatory substrate). Write under runs/uml_temp_federations/
only — do NOT promote to persistent composites until frequency+cost+Codex+authority.
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
OUT_DIR = SANDBOX / "runs" / "uml_temp_federations"
DATA_ROOT = SANDBOX / "data" / "uml_temp_federations_v1"
U_CKPT = SANDBOX / "checkpoints" / "uml_structure" / "specialist.pt"
MIX_RECIPE = SANDBOX / "uml_mix_recipe.json"
LATTICE = SANDBOX / "uml_domain_expert_lattice.json"
RECIPE = SANDBOX / "uml_domain_expert_train_recipe.json"

PAIRS = ("AS", "AM", "AD", "SM", "SD", "MD")
TRIPLES = ("ASM", "ASD", "AMD", "SMD")
ASMD = ("ASMD",)
ALL_LABELS = set(PAIRS) | set(TRIPLES) | set(ASMD)

for p in (MODEL, SANDBOX, FOUNDATION):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

import run_uml_equation_ab as ab  # noqa: E402


def _tier_of(label: str) -> str:
    if label in PAIRS:
        return "pair"
    if label in TRIPLES:
        return "triple"
    if label in ASMD:
        return "all_four"
    raise ValueError(label)


def _receipt_paths(tier: str) -> tuple[Path, Path]:
    if tier == "triple":
        return (
            SANDBOX / "runs" / "uml_temp_triple_federations_latest.json",
            SANDBOX / "runs" / "uml_temp_triple_federations_latest.md",
        )
    if tier == "all_four":
        return (
            SANDBOX / "runs" / "uml_temp_asmd_federation_latest.json",
            SANDBOX / "runs" / "uml_temp_asmd_federation_latest.md",
        )
    return (
        SANDBOX / "runs" / "uml_temp_federations_latest.json",
        SANDBOX / "runs" / "uml_temp_federations_latest.md",
    )


def _ensure(labels: tuple[str, ...], *, repeat: int = 20) -> dict[str, Path]:
    unique_tiers = {_tier_of(x) for x in labels}
    build = SANDBOX / "build_uml_temp_federation_banks.py"
    if unique_tiers == {"pair"}:
        tier_arg = "pairs"
    elif unique_tiers == {"triple"}:
        tier_arg = "triples"
    elif unique_tiers == {"all_four"}:
        tier_arg = "asmd"
    else:
        tier_arg = "all"
    subprocess.run(
        [str(PY), "-B", str(build), "--tier", tier_arg, "--labels", ",".join(labels)],
        check=True,
        cwd=str(SANDBOX),
    )
    tensors: dict[str, Path] = {}
    pack = SANDBOX / "pack_uml_dialogues_tensor.py"
    for label in labels:
        dialogues = DATA_ROOT / f"U_{label}" / "train_dialogues.txt"
        tensor = DATA_ROOT / f"U_{label}" / "tensor_dataset"
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
        tensors[label] = tensor
    return tensors


def main() -> int:
    mix_recipe = ab.load_mix_recipe(MIX_RECIPE)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=1500)
    parser.add_argument("--mix-ratio", type=float, default=0.5)
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
    parser.add_argument(
        "--labels",
        type=str,
        default="",
        help="Comma list of federation labels (e.g. ASM,ASD,AMD,SMD).",
    )
    parser.add_argument(
        "--pairs",
        type=str,
        default="",
        help="Deprecated alias for --labels (pair tier).",
    )
    parser.add_argument(
        "--tier",
        choices=("pairs", "triples", "asmd"),
        default="",
        help="Preset label set when --labels/--pairs omitted.",
    )
    parser.add_argument("--warm-ckpt", type=Path, default=U_CKPT)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    raw = (args.labels or args.pairs or "").strip()
    if raw:
        selected = tuple(p.strip() for p in raw.split(",") if p.strip())
    elif args.tier == "triples":
        selected = TRIPLES
    elif args.tier == "asmd":
        selected = ASMD
    elif args.tier == "pairs":
        selected = PAIRS
    else:
        selected = ("AM", "AS", "MD")

    for lab in selected:
        if lab not in ALL_LABELS:
            raise ValueError(f"unknown_federation:{lab}")
    tiers = {_tier_of(x) for x in selected}
    if len(tiers) != 1:
        raise ValueError(f"mixed_tiers_not_allowed:{sorted(tiers)}")
    tier = next(iter(tiers))
    receipt_json, receipt_md = _receipt_paths(tier)

    if not Path(args.warm_ckpt).is_file():
        raise FileNotFoundError(args.warm_ckpt)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tensors = _ensure(selected)

    _, vocab_path, codex_tensor = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    if str(device).startswith("cuda") and not torch.cuda.is_available():
        device = torch.device("cpu")
    configure_plant_runtime(device=str(device))

    codex_train = load_split(codex_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True)
    codex_val = load_split(codex_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True)

    results: list[dict[str, Any]] = []
    for i, label in enumerate(selected):
        fed = f"U_{label}"
        warm = OUT_DIR / f"warm_{fed}.pt"
        shutil.copy2(args.warm_ckpt, warm)
        uml_train = load_split(
            tensors[label], "train", vocab_size=tok.vocab_size, response_only_loss=True
        )
        uml_val = load_split(
            tensors[label], "validation", vocab_size=tok.vocab_size, response_only_loss=True
        )
        start = ab._metrics(
            warm, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
        )
        print(
            f"FED_{fed}_START tier={tier} steps={args.steps} mix={args.mix_ratio} warm=U",
            flush=True,
        )
        ckpt = ab._train_leg(
            name=f"temp_{fed}",
            warm_ckpt=warm,
            steps=int(args.steps),
            batch_size=int(args.batch_size),
            lr=float(args.lr),
            mix_ratio=float(args.mix_ratio),
            device=device,
            tok=tok,
            codex_train=codex_train,
            uml_train=uml_train,
            seed=int(args.seed) + 40 + i,
            log_every=int(args.log_every),
            prefer_cheap_boost=float(args.prefer_cheap_boost),
            plant_sn_gate=True,
            out_dir=OUT_DIR,
        )
        after = ab._metrics(
            ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
        )
        hold = (after["codex_acc"] - start["codex_acc"]) >= -float(args.codex_hold_tol)
        uml_up = after["uml_acc"] - start["uml_acc"] > 0.01
        status = "PASS" if hold and uml_up else ("HOLD_ONLY" if hold else "FAIL_HOLD")
        results.append(
            {
                "federation": fed,
                "label": label,
                "tier": tier,
                "temporary": True,
                "persistent": False,
                "status": status,
                "codex_hold": hold,
                "start": start,
                "after": after,
                "delta_uml_acc": after["uml_acc"] - start["uml_acc"],
                "delta_codex_acc": after["codex_acc"] - start["codex_acc"],
                "ckpt": str(ckpt).replace("\\", "/"),
                "member_experts": ["U", *list(label)],
            }
        )
        print(
            f"FED_{fed}_{status} hold={hold} "
            f"uml {start['uml_acc']:.4f}->{after['uml_acc']:.4f} "
            f"codex {start['codex_acc']:.4f}->{after['codex_acc']:.4f}",
            flush=True,
        )

    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_hold = sum(1 for r in results if r["codex_hold"])
    objective = (
        "PASS"
        if n_pass == len(results)
        else ("PASS_PARTIAL" if n_hold == len(results) and n_pass > 0 else "FAIL")
    )
    finished = datetime.now(timezone.utc).isoformat()

    lattice = json.loads(LATTICE.read_text(encoding="utf-8"))
    key = {
        "pair": "temporary_federations",
        "triple": "temporary_triple_federations",
        "all_four": "temporary_asmd_federation",
    }[tier]
    lattice[key] = {
        "status": objective,
        "policy": "temporary_only",
        "warm_substrate": "U",
        "tier": tier,
        "admitted": [r["federation"] for r in results if r["codex_hold"]],
        "passed": [r["federation"] for r in results if r["status"] == "PASS"],
        "complete": n_pass == len(results),
        "runs_dir": str(OUT_DIR).replace("\\", "/"),
        "updated_at": finished,
    }
    LATTICE.write_text(
        json.dumps(lattice, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    if RECIPE.is_file():
        recipe = json.loads(RECIPE.read_text(encoding="utf-8"))
        recipe["last_run"] = finished
        recipe["last_objective"] = f"{tier.upper()}_{objective}"
        if tier == "triple":
            recipe["status"] = "generators_plus_temp_pair_and_triple_federations"
            recipe["next_action"] = (
                "Temporary U_ASMD (full arithmetic federation); "
                "promote composites only after frequency+cost+Codex+authority."
            )
            recipe["temporary_triple_federations"] = {
                "passed": lattice[key]["passed"],
                "mix_default": float(args.mix_ratio),
                "warm": "U",
            }
            recipe["binding_read"]["not_yet"] = (
                "Persistent composite federations — temporary only until promotion gates fire. "
                "U_ASMD not yet temporary-trained."
            )
        RECIPE.write_text(
            json.dumps(recipe, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    receipt = {
        "schema_version": "uml_temp_federations_v2",
        "status": "PASS",
        "objective": objective,
        "tier": tier,
        "temporary": True,
        "persistent_composites": False,
        "hypothesis": (
            f"Temporary U+{tier} federations warm-started from U learn mixed-domain "
            "routes while holding Codex; not promoted to persistent composites yet."
        ),
        "finished_at": finished,
        "warm_source": str(args.warm_ckpt).replace("\\", "/"),
        "steps": int(args.steps),
        "mix_ratio": float(args.mix_ratio),
        "federations": results,
        "n_pass": n_pass,
        "n_hold": n_hold,
        "device": str(device),
    }
    with receipt_json.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    lines = [
        f"# Temporary U+{tier} Federations",
        "",
        f"- Objective: **{objective}**",
        f"- PASS {n_pass}/{len(results)} hold {n_hold}/{len(results)}",
        "- Temporary only (no persistent composite promotion)",
        "- Warm substrate: U",
        f"- Steps: {args.steps}  mix: {args.mix_ratio}",
        "",
        "## Federations",
    ]
    for r in results:
        lines.append(
            f"- {r['federation']}: {r['status']} "
            f"uml={r['start']['uml_acc']:.4f}->{r['after']['uml_acc']:.4f} "
            f"hold={r['codex_hold']}"
        )
    lines.extend(["", f"Receipt: `{receipt_json.as_posix()}`", ""])
    receipt_md.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(
        f"UML_TEMP_{tier.upper()}_FEDERATIONS_{objective} "
        f"pass={n_pass}/{len(results)} hold={n_hold}/{len(results)}",
        flush=True,
    )
    return 0 if objective.startswith("PASS") else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main())
