#!/usr/bin/env python3
"""Prove UML pressure on speak_viv_sandwich (deep mouth)."""
from __future__ import annotations

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
from plant_checkpoint import load_plant_state_dict  # noqa: E402
from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import IDENTITY_MODEL_CFG, resolve_codex_dataset  # noqa: E402
from sandbox_paths import DEEP_CKPT, EFFICIENT_CKPT  # noqa: E402
from speak_lanes import speak_viv, speak_viv_sandwich  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402

PILOT = SANDBOX / "runs" / "uml_equation_ab_v2" / "pilot_uml_mix_masked.pt"
RECEIPT = SANDBOX / "runs" / "uml_speak_sandwich_pressure_latest.json"


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


def _suffix(text: str, prompt: str) -> str:
    if text.startswith(prompt):
        text = text[len(prompt) :]
    return text.split("\n")[0].replace("<END>", "").strip()


def main() -> int:
    _, vocab_path, _ = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    configure_plant_runtime(device="cpu")
    deep_ckpt = PILOT if PILOT.is_file() else DEEP_CKPT
    model_e = _load(EFFICIENT_CKPT, tok, torch.device("cpu"))
    model_d = _load(deep_ckpt, tok, torch.device("cuda" if torch.cuda.is_available() else "cpu"))

    target = "H"
    prompt = f"User: UML equivalent for {target}\nViv: "
    ids = torch.tensor([tok.encode(prompt)], dtype=torch.long)
    pressure = {
        "stoi": tok.stoi,
        "itos": tok.itos,
        "prompt_len": int(ids.shape[1]),
        "target_char": target,
        "scale": 6.0,
        "hard_mask": True,
    }

    plain = speak_viv(
        model_d,
        ids,
        lane="deep",
        max_new_tokens=24,
        temperature=0.8,
        decode_fn=tok.decode,
        stop_sequences=["\n", "<END>"],
        stamp_master_rid=False,
    )
    pressed = speak_viv(
        model_d,
        ids,
        lane="deep",
        max_new_tokens=24,
        temperature=0.8,
        decode_fn=tok.decode,
        stop_sequences=["\n", "<END>"],
        uml_pressure=pressure,
        stamp_master_rid=False,
    )
    sandwich = speak_viv_sandwich(
        model_e,
        model_d,
        ids,
        front_max=8,
        deep_max=24,
        verify_max=16,
        decode_fn=tok.decode,
        stop_sequences=["\n", "<END>"],
        uml_pressure=pressure,
        uml_pressure_on="deep",
        stamp_master_rid=False,
    )

    from lib.uml_equation_registry import UMLEquationRegistry, SANDBOX96_ARTIFACT

    # Ensure foundation import
    FOUNDATION = MODEL.parents[4]
    if str(FOUNDATION) not in sys.path:
        sys.path.insert(0, str(FOUNDATION))
    from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402

    from lib.uml_equation_registry import UMLEquationRegistry, SANDBOX96_ARTIFACT

    # Ensure foundation import
    FOUNDATION = MODEL.parents[4]
    if str(FOUNDATION) not in sys.path:
        sys.path.insert(0, str(FOUNDATION))
    from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402

    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)

    def judge(expr: str) -> dict[str, object]:
        try:
            ch = reg.decode_eq(expr)
            return {"expr": expr, "char": ch, "match": ch == target, "valid": True}
        except Exception as exc:
            return {"expr": expr, "valid": False, "error": repr(exc)}

    plain_s = _suffix(str(plain.get("text") or ""), prompt)
    pressed_s = _suffix(str(pressed.get("text") or ""), prompt)
    sand_s = _suffix(str(sandwich.get("text") or ""), prompt)

    receipt = {
        "schema_version": "uml_speak_sandwich_pressure_v1",
        "status": "PASS",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "target_char": target,
        "prompt": prompt,
        "deep_plain": {
            **judge(plain_s),
            "path": plain["receipt"].get("path"),
            "logits_bias_fn": plain["receipt"].get("logits_bias_fn"),
        },
        "deep_pressure": {
            **judge(pressed_s),
            "path": pressed["receipt"].get("path"),
            "logits_bias_fn": pressed["receipt"].get("logits_bias_fn"),
            "uml_pressure": pressed["receipt"].get("uml_pressure"),
        },
        "sandwich": {
            **judge(sand_s),
            "path": sandwich["receipt"].get("path"),
            "uml_pressure_on": sandwich["receipt"].get("uml_pressure_on"),
            "accepted_prefix_len": sandwich["receipt"].get("accepted_prefix_len"),
            "deep_path": sandwich["receipt"].get("deep_path"),
            "uml_pressure": sandwich["receipt"].get("uml_pressure"),
        },
        "checkpoints": {
            "efficient": str(EFFICIENT_CKPT).replace("\\", "/"),
            "deep": str(deep_ckpt).replace("\\", "/"),
        },
    }
    # Soft gate: pressure path should be valid for target more often than claiming hard fail.
    if not receipt["deep_pressure"].get("match"):
        receipt["status"] = "FAIL"
        receipt["fail_reason"] = "deep_pressure_mismatch"
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    print(
        f"UML_SPEAK_SANDWICH_PRESSURE_{receipt['status']} "
        f"plain={plain_s!r} pressed={pressed_s!r} sandwich={sand_s!r}"
    )
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
