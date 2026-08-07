#!/usr/bin/env python3
"""Sandbox demo: UML efficiency pressure sampling on generate logits.

Does not mutate Codex or specialist checkpoints. Optional --resume loads a
sandbox A/B pilot for equation-flavored prompts; otherwise uses efficient ckpt.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))
if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))
if str(SANDBOX) not in sys.path:
    sys.path.insert(0, str(SANDBOX))

from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402
from lib.uml_route_governor import (  # noqa: E402
    decide_route,
    make_generate_logits_bias_fn,
    sample_route,
)
from plant_checkpoint import load_plant_state_dict  # noqa: E402
from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import IDENTITY_MODEL_CFG, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402

EFF = SANDBOX / "checkpoints" / "efficient" / "specialist.pt"
PILOT = SANDBOX / "runs" / "uml_equation_ab_v2" / "pilot_uml_mix_masked.pt"
RECEIPT = SANDBOX / "runs" / "uml_pressure_sampling_latest.json"


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--char", default="H", help="Fixed answer character.")
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--route-temperature", type=float, default=0.7)
    parser.add_argument("--pressure-scale", type=float, default=6.0)
    parser.add_argument("--hard-mask", action="store_true")
    parser.add_argument("--max-new-tokens", type=int, default=24)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--ckpt", default="", help="Override checkpoint path.")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    ch = str(args.char)
    if ch not in reg.entries:
        raise SystemExit(f"uml_pressure_char_not_in_vocab:{ch!r}")

    _, vocab_path, _ = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    if str(device).startswith("cuda") and not torch.cuda.is_available():
        device = torch.device("cpu")
    configure_plant_runtime(device=str(device))

    ckpt = Path(args.ckpt) if args.ckpt else (PILOT if PILOT.is_file() else EFF)
    model = _load(ckpt, tok, device)
    torch.manual_seed(int(args.seed))
    gen = torch.Generator(device="cpu")
    gen.manual_seed(int(args.seed))

    # Route-level pressure sample (among valid equations).
    sampled = sample_route(
        reg,
        target_char=ch,
        temperature=float(args.route_temperature),
        generator=gen,
    )
    cheapest = decide_route(reg, target_char=ch)

    prompt = f"User: UML equivalent for {ch}\nViv: "
    prompt_ids = tok.encode(prompt)
    context = torch.tensor([prompt_ids], dtype=torch.long, device=device)
    bias_fn = make_generate_logits_bias_fn(
        pressure_weights=cheapest.pressure_weights,
        stoi=tok.stoi,
        itos=tok.itos,
        prompt_len=len(prompt_ids),
        scale=float(args.pressure_scale),
        hard_mask=bool(args.hard_mask),
        complete_char="\n",
    )

    with torch.no_grad():
        out_pressure = model.generate(
            context,
            max_new_tokens=int(args.max_new_tokens),
            temperature=float(args.temperature),
            top_p=0.95,
            stop_sequences=["\n", "<END>"],
            decode_fn=lambda ids: tok.decode(ids),
            logits_bias_fn=bias_fn,
        )
        pressure_policy = dict(model._last_generate_policy or {})
        out_plain = model.generate(
            context,
            max_new_tokens=int(args.max_new_tokens),
            temperature=float(args.temperature),
            top_p=0.95,
            stop_sequences=["\n", "<END>"],
            decode_fn=lambda ids: tok.decode(ids),
            logits_bias_fn=None,
        )

    def suffix(ids: torch.Tensor) -> str:
        row = ids[0].tolist()
        return tok.decode(row[len(prompt_ids) :])

    text_p = suffix(out_pressure).split("\n")[0].replace("<END>", "").strip()
    text_0 = suffix(out_plain).split("\n")[0].replace("<END>", "").strip()

    def try_decode(expr: str) -> dict[str, object]:
        try:
            back = reg.decode_eq(expr)
            return {"expr": expr, "valid_decode": True, "char": back, "match": back == ch}
        except Exception as exc:
            return {"expr": expr, "valid_decode": False, "error": repr(exc)}

    receipt = {
        "schema_version": "uml_pressure_sampling_v1",
        "status": "PASS",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "sandbox_only": True,
        "checkpoint": str(ckpt).replace("\\", "/"),
        "target_char": ch,
        "target_value": int(reg.entries[ch]["value"]),
        "route_sample": {
            "selected": sampled.selected,
            "selected_cost": sampled.selected_cost,
            "reason": sampled.reason,
            "cheapest": cheapest.selected,
            "cheapest_cost": cheapest.selected_cost,
        },
        "prompt": prompt,
        "generate_pressure": try_decode(text_p),
        "generate_plain": try_decode(text_0),
        "policy": pressure_policy,
        "pressure_scale": float(args.pressure_scale),
        "hard_mask": bool(args.hard_mask),
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    print(
        f"UML_PRESSURE_SAMPLING_PASS "
        f"route={sampled.selected} gen_p={text_p!r} gen_0={text_0!r}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
