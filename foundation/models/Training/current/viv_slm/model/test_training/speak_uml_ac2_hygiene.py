#!/usr/bin/env python3
"""Prove A (sandwich hygiene) + C2 (expanded auto-target)."""
from __future__ import annotations

import json
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

from lib.uml_equation_registry import UMLEquationRegistry, SANDBOX96_ARTIFACT  # noqa: E402
from plant_checkpoint import load_plant_state_dict  # noqa: E402
from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import IDENTITY_MODEL_CFG, resolve_codex_dataset  # noqa: E402
from sandbox_paths import DEEP_CKPT, EFFICIENT_CKPT  # noqa: E402
from speak_lanes import speak_viv_sandwich  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402
from uml_speak_pressure import infer_uml_target_from_prompt  # noqa: E402

PILOT = SANDBOX / "runs" / "uml_equation_ab_v2" / "pilot_uml_mix_masked.pt"
RECEIPT = SANDBOX / "runs" / "uml_ac2_hygiene_latest.json"


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
    failures: list[str] = []
    _, vocab_path, _ = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)

    # C2 patterns
    c2_cases = [
        ("User: Prefer efficient UML for H\nViv: ", "H"),
        ("User: Rank UML routes for Z\nBest: 90\nViv: ", "Z"),
        ("User: Is this UML valid for A?\nCandidate: 9\nViv: ", "A"),
        ("What is the UML for 'V'?\nViv: ", "V"),
        ("UML for Q\nViv: ", "Q"),
        ("char='B'\nViv: ", "B"),
        ("character X please\nViv: ", "X"),
        ("User: UML encode\nSurface: Hello\nViv: ", "H"),
    ]
    for prompt, want in c2_cases:
        got = infer_uml_target_from_prompt(prompt, vocab=tok.vocab)
        if not got.get("matched") or got.get("target_char") != want:
            failures.append(f"c2:{prompt!r}->{got} want={want}")

    configure_plant_runtime(device="cpu")
    deep_ckpt = PILOT if PILOT.is_file() else DEEP_CKPT
    model_e = _load(EFFICIENT_CKPT, tok, torch.device("cpu"))
    model_d = _load(deep_ckpt, tok, torch.device("cuda" if torch.cuda.is_available() else "cpu"))

    target = "H"
    prompt = f"User: Prefer efficient UML for {target}\nViv: "
    ids = torch.tensor([tok.encode(prompt)], dtype=torch.long)
    # Auto-target only (C2) — no explicit target_char.
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
    eq = str(sandwich.get("equation_text") or "")
    inferred = (sandwich["receipt"].get("uml_pressure") or {}).get("inferred") or {}
    if not sandwich["receipt"].get("uml_equation_mode"):
        failures.append("equation_mode_off")
    if inferred.get("target_char") != target:
        failures.append(f"auto_infer:{inferred}")
    if not eq or "\n" in eq or eq.startswith("Vi"):
        failures.append(f"dirty_equation:{eq!r}")
    try:
        back = reg.decode_eq(eq)
        if back != target:
            failures.append(f"equation_mismatch:{eq!r}->{back!r}")
        match = back == target
    except Exception as exc:
        failures.append(f"equation_decode:{eq!r}:{exc!r}")
        match = False

    status = "PASS" if not failures else "FAIL"
    receipt = {
        "schema_version": "uml_ac2_hygiene_v1",
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "failures": failures,
        "c2_cases": len(c2_cases),
        "equation_text": eq,
        "equation_match": match,
        "equation_source": sandwich["receipt"].get("equation_source"),
        "uml_equation_mode": sandwich["receipt"].get("uml_equation_mode"),
        "inferred": inferred,
        "deep_path": sandwich["receipt"].get("deep_path"),
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    # Also refresh legacy sandwich receipt pointer.
    legacy = SANDBOX / "runs" / "uml_speak_sandwich_pressure_latest.json"
    with legacy.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"UML_AC2_HYGIENE_{status} eq={eq!r} failures={len(failures)}")
    if failures:
        for item in failures[:20]:
            print("FAIL", item)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
