#!/usr/bin/env python3
"""F: Speak-path A/B — equation hygiene + cheap-route rate across checkpoints."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
for p in (FOUNDATION, MODEL, SANDBOX):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402
from lib.uml_route_governor import route_efficiency_error  # noqa: E402
from plant_checkpoint import load_plant_state_dict  # noqa: E402
from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import IDENTITY_MODEL_CFG, resolve_codex_dataset  # noqa: E402
from sandbox_paths import EFFICIENT_CKPT  # noqa: E402
from speak_lanes import speak_viv_sandwich  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402

RECEIPT = SANDBOX / "runs" / "uml_speak_ab_f_latest.json"

PROMPTS = [
    ("H", "User: Prefer efficient UML for H\nViv: "),
    ("Z", "User: Rank UML routes for Z\nBest: 90\nViv: "),
    ("A", "User: Is this UML valid for A?\nCandidate: 9\nViv: "),
    ("V", "What is the UML for 'V'?\nViv: "),
    ("Q", "UML for Q\nViv: "),
    ("B", "char='B'\nViv: "),
    ("X", "character X please\nViv: "),
]


def _load(path: Path, tok: CharacterTokenizer, device: torch.device) -> TransformerLanguageModel:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    model = TransformerLanguageModel(tok.vocab_size, **IDENTITY_MODEL_CFG).to(device)
    load_plant_state_dict(
        model,
        payload["model_state_dict"],
        strict=False,
        config=dict(payload.get("config") or IDENTITY_MODEL_CFG),
    )
    model.eval()
    return model


def _eval_ckpt(
    *,
    name: str,
    deep_path: Path,
    model_e: TransformerLanguageModel,
    tok: CharacterTokenizer,
    reg: UMLEquationRegistry,
    device: torch.device,
) -> dict[str, Any]:
    model_d = _load(deep_path, tok, device)
    rows: list[dict[str, Any]] = []
    match_n = 0
    cheap_n = 0
    valid_n = 0
    dirty_n = 0
    err_sum = 0.0
    for ch, prompt in PROMPTS:
        ids = torch.tensor([tok.encode(prompt)], dtype=torch.long)
        pressure = {
            "stoi": tok.stoi,
            "itos": tok.itos,
            "prompt_len": int(ids.shape[1]),
            "hard_mask": True,
            "scale": 6.0,
        }
        sandwich = speak_viv_sandwich(
            model_e,
            model_d,
            ids,
            deep_max=24,
            verify_max=16,
            decode_fn=tok.decode,
            uml_pressure=pressure,
            uml_pressure_on="deep",
            stamp_master_rid=False,
        )
        eq = str(sandwich.get("equation_text") or "").strip()
        dirty = (not eq) or ("\n" in eq) or eq.startswith("Vi")
        if dirty:
            dirty_n += 1
        match = False
        try:
            back = reg.decode_eq(eq) if eq and not dirty else None
            match = back == ch
        except Exception:
            match = False
        if match:
            match_n += 1
        info = route_efficiency_error(reg, proposed=eq if eq else "???", target_char=ch)
        if info.get("valid"):
            valid_n += 1
        if info.get("kind") == "valid_efficient":
            cheap_n += 1
        err_sum += float(info.get("error") or 1.0)
        rows.append(
            {
                "target": ch,
                "equation": eq,
                "match": match,
                "dirty": dirty,
                "kind": info.get("kind"),
                "error": info.get("error"),
                "cost": info.get("proposed_cost"),
                "cheapest": info.get("cheapest"),
            }
        )
    n = len(PROMPTS)
    return {
        "name": name,
        "ckpt": str(deep_path).replace("\\", "/"),
        "n": n,
        "match_rate": match_n / n,
        "valid_rate": valid_n / n,
        "cheap_rate": cheap_n / n,
        "dirty_rate": dirty_n / n,
        "mean_route_error": err_sum / n,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ckpt",
        action="append",
        nargs=2,
        metavar=("NAME", "PATH"),
        help="Named checkpoint to compare (repeatable).",
    )
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    runs = SANDBOX / "runs"
    defaults = [
        ("b3", runs / "uml_equation_ab_v2_b3_10000" / "pilot_uml_mix_masked.pt"),
        ("g_boost2", runs / "uml_equation_ab_v2_g_boost2" / "pilot_uml_mix_masked.pt"),
    ]
    # Optional later legs if present.
    for name, path in (
        ("i_best", runs / "uml_prefer_cheap_boost_sweep" / "_best_pointer.json"),
        ("j_rid", runs / "uml_rid_residual_train_j" / "pilot_boost_with_rid.pt"),
    ):
        if name == "i_best" and path.is_file():
            meta = json.loads(path.read_text(encoding="utf-8"))
            ck = Path(meta["ckpt"])
            if ck.is_file():
                defaults.append(("i_best", ck))
        elif path.is_file():
            defaults.append((name, path))

    pairs = [(n, Path(p)) for n, p in (args.ckpt or [])] or [
        (n, p) for n, p in defaults if Path(p).is_file()
    ]
    if len(pairs) < 2:
        raise FileNotFoundError(f"speak_ab_need_ge_2_ckpts:{pairs}")

    _, vocab_path, _ = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    if str(device).startswith("cuda") and not torch.cuda.is_available():
        device = torch.device("cpu")
    configure_plant_runtime(device=str(device))
    model_e = _load(EFFICIENT_CKPT, tok, torch.device("cpu"))

    results = [
        _eval_ckpt(name=n, deep_path=p, model_e=model_e, tok=tok, reg=reg, device=device)
        for n, p in pairs
    ]

    # Rank: higher cheap_rate, then match_rate, then lower mean_route_error.
    ranked = sorted(
        results,
        key=lambda r: (-r["cheap_rate"], -r["match_rate"], r["mean_route_error"], r["dirty_rate"]),
    )
    best = ranked[0]
    receipt = {
        "schema_version": "uml_speak_ab_f_v1",
        "status": "PASS",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "Later UML pilots improve speak-path match + cheap-route rate vs earlier pilots.",
        "prompts": len(PROMPTS),
        "results": results,
        "best": {"name": best["name"], "cheap_rate": best["cheap_rate"], "match_rate": best["match_rate"]},
        "ranking": [r["name"] for r in ranked],
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"UML_SPEAK_AB_F_PASS best={best['name']} "
        f"cheap={best['cheap_rate']:.3f} match={best['match_rate']:.3f} "
        f"rank={receipt['ranking']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
