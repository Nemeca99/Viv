#!/usr/bin/env python3
"""Train/eval on real held-out English mined from Codex, absent from mix bank."""
from __future__ import annotations

import json
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
for p in (FOUNDATION, MODEL, SANDBOX):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402
from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
import build_uml_equation_mix_dataset as mix_build  # noqa: E402
import run_uml_equation_ab as ab  # noqa: E402
import run_uml_ood_probe as ood  # noqa: E402

SURVIVOR = SANDBOX / "runs" / "uml_mix_layers" / "layer_survivor.pt"
BANK_SURFACES = SANDBOX / "data" / "uml_equation_mix_v1" / "surfaces.json"
OUT = SANDBOX / "runs" / "uml_real_heldout"
DATA = SANDBOX / "data" / "uml_real_heldout_v1"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    bank = set(json.loads(BANK_SURFACES.read_text(encoding="utf-8")).get("surfaces") or [])
    tok = CharacterTokenizer.from_manifest(resolve_codex_dataset("v61")[1])
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)

    # Mine many Codex phrases, keep those not in bank.
    mined = mix_build._mine_codex_phrases(
        tok, max_examples_per_split=20000, min_len=12, max_len=120
    )
    held = [s for s in mined if s not in bank and "oodprobe" not in s.lower()]
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n", type=int, default=256)
    ap.add_argument("--steps", type=int, default=4000)
    ns, _unknown = ap.parse_known_args()
    rng = random.Random(int(ns.seed))
    rng.shuffle(held)
    if len(held) < int(ns.n) * 2:
        raise RuntimeError(f"real_heldout_too_few:{len(held)}")
    n = int(ns.n)
    set_a = held[:n]
    set_b = held[n : n * 2]
    steps = int(ns.steps)
    (DATA / "set_a.json").write_text(
        json.dumps({"count": len(set_a), "surfaces": set_a}, indent=2) + "\n", encoding="utf-8"
    )
    (DATA / "set_b.json").write_text(
        json.dumps({"count": len(set_b), "surfaces": set_b}, indent=2) + "\n", encoding="utf-8"
    )
    print(f"REAL_HELDOUT mined={len(mined)} unused={len(held)} A={len(set_a)} B={len(set_b)}", flush=True)

    def pack_and_score(surfaces: list[str], ckpt: Path, tag: str) -> dict:
        seal = ood._surface_seal(reg, surfaces)
        dialogues = ood._ood_dialogues(reg, surfaces, hard=True)
        tensor = ood._pack_ood_tensor(tok, dialogues, DATA / f"tensor_{tag}")
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        configure_plant_runtime(device=str(device))
        _, _, codex_tensor = resolve_codex_dataset("v61")
        codex_val = load_split(
            codex_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True
        )
        held_val = load_split(
            tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True
        )
        metrics = ab._metrics(
            ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=held_val, batch_size=64
        )
        return {
            "tag": tag,
            "n": len(surfaces),
            "seal_rate": seal["rate"],
            "uml_acc": metrics["uml_acc"],
            "uml_nll": metrics["uml_nll"],
            "codex_acc": metrics["codex_acc"],
            "tensor": str(tensor).replace("\\", "/"),
        }

    base_a = pack_and_score(set_a, SURVIVOR, "A_base")
    print(f"BASE_A uml={base_a['uml_acc']:.3f} seal={base_a['seal_rate']:.3f}", flush=True)

    # Train on A
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    configure_plant_runtime(device=str(device))
    _, vocab_path, codex_tensor = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    codex_train = load_split(
        codex_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True
    )
    codex_val = load_split(
        codex_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True
    )
    mix_val = load_split(
        ab._ensure_mix_dataset(), "validation", vocab_size=tok.vocab_size, response_only_loss=True
    )
    uml_train = load_split(
        Path(base_a["tensor"]), "train", vocab_size=tok.vocab_size, response_only_loss=True
    )
    start = ab._metrics(
        SURVIVOR, tok=tok, device=device, codex_val=codex_val, uml_val=mix_val, batch_size=64
    )
    warm = OUT / "warm.pt"
    shutil.copy2(SURVIVOR, warm)
    ckpt = ab._train_leg(
        name="real_heldout",
        warm_ckpt=warm,
        steps=steps,
        batch_size=64,
        lr=7e-6,
        mix_ratio=0.42,
        device=device,
        tok=tok,
        codex_train=codex_train,
        uml_train=uml_train,
        seed=201,
        log_every=500,
        prefer_cheap_boost=1.5,
        rid_residual_weight=0.0,
        thermal_route_weight=0.0,
        plant_sn_gate=False,
        out_dir=OUT,
    )
    after = ab._metrics(
        ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=mix_val, batch_size=64
    )
    d_codex = after["codex_acc"] - start["codex_acc"]
    if d_codex < -0.001:
        print(f"CODEX_RECOVER d={d_codex:+.4f}", flush=True)
        warm_r = OUT / "warm_recover.pt"
        shutil.copy2(ckpt, warm_r)
        ckpt = ab._train_leg(
            name="real_heldout_recover",
            warm_ckpt=warm_r,
            steps=1000,
            batch_size=64,
            lr=7e-6,
            mix_ratio=0.0,
            device=device,
            tok=tok,
            codex_train=codex_train,
            uml_train=codex_train,
            seed=202,
            log_every=500,
            prefer_cheap_boost=1.0,
            rid_residual_weight=0.0,
            thermal_route_weight=0.0,
            plant_sn_gate=False,
            out_dir=OUT,
        )
        after = ab._metrics(
            ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=mix_val, batch_size=64
        )
        d_codex = after["codex_acc"] - start["codex_acc"]

    post_a = pack_and_score(set_a, ckpt, "A_after")
    post_b = pack_and_score(set_b, ckpt, "B_fresh")
    hold = d_codex >= -0.001
    lift_a = post_a["uml_acc"] - base_a["uml_acc"]
    if hold and lift_a >= 0.10 and post_b["uml_acc"] >= base_a["uml_acc"] + 0.05:
        objective = "PASS_REAL_HELDOUT_GENERALIZE"
    elif hold and lift_a >= 0.05:
        objective = "PASS_REAL_HELDOUT_LIFT"
    elif hold:
        objective = "TIE_REAL_HELDOUT"
    else:
        objective = "FAIL_HOLD"

    committed = False
    if objective.startswith("PASS") and hold:
        shutil.copy2(ckpt, SURVIVOR)
        committed = True

    receipt = {
        "schema_version": "uml_real_heldout_v1",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "objective": objective,
        "bank_surfaces": len(bank),
        "heldout_pool": len(held),
        "codex_hold": hold,
        "delta_codex": d_codex,
        "start_id": start,
        "after_id": after,
        "baseline_A": base_a,
        "after_A": post_a,
        "fresh_B": post_b,
        "delta_uml_A": lift_a,
        "delta_uml_B_vs_Abase": post_b["uml_acc"] - base_a["uml_acc"],
        "survivor_committed": committed,
        "ckpt": str(ckpt).replace("\\", "/"),
    }
    text = json.dumps(receipt, indent=2, sort_keys=True)
    (OUT / "real_heldout_latest.json").write_text(text + "\n", encoding="utf-8")
    (SANDBOX / "runs" / "uml_real_heldout_latest.json").write_text(text + "\n", encoding="utf-8")
    print(
        f"REAL_HELDOUT_{objective} A {base_a['uml_acc']:.3f}->{post_a['uml_acc']:.3f} "
        f"B={post_b['uml_acc']:.3f} hold={hold} d_codex={d_codex:+.4f} committed={committed}",
        flush=True,
    )
    return 0 if objective != "FAIL_HOLD" else 1


if __name__ == "__main__":
    raise SystemExit(main())
