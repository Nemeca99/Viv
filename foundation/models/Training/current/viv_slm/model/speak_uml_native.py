#!/usr/bin/env python3
"""Native UML speak: text → encode → plant sees math tokens → decode → text.

Emergent need P1: the plant must think in UML tokens, not English prompts.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Mapping

import torch
from torch import nn

MODEL = Path(__file__).resolve().parent
if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))

from uml_codec_io import (  # noqa: E402
    build_native_uml_prompt,
    continue_uml_response,
    load_registry,
)


def speak_uml_native(
    model: nn.Module,
    user_text: str,
    *,
    encode_fn: Callable[[str], list[int]],
    decode_fn: Callable[[list[int]], str],
    max_new_tokens: int = 64,
    prefer_efficient: bool = True,
    temperature: float = 0.0,
    uml_pressure: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Exclusive UML I/O shell around one dense plant generate call.

    Outside: ``user_text``.
    Inside: ``UML:<eq>,...\\nViv: `` then model continuation in equation tokens.
    Outside again: decoded surface text.
    """
    from speak_lanes import speak_viv

    reg = load_registry()
    native = build_native_uml_prompt(
        user_text, registry=reg, prefer_efficient=prefer_efficient
    )
    prompt = native["model_prompt"]
    ids = torch.tensor([encode_fn(prompt)], dtype=torch.long)
    pressure = None
    if uml_pressure is not None:
        pressure = dict(uml_pressure)
        pressure.setdefault("prompt_len", int(ids.shape[1]))
        pressure.setdefault("prompt_text", prompt)
        # Seal to first char of user text when single-char / prefer path.
        if user_text and "target_char" not in pressure and "target_value" not in pressure:
            pressure["target_char"] = user_text[0]
            pressure["auto_target"] = False

    out = speak_viv(
        model,
        ids,
        max_new_tokens=max_new_tokens,
        temperature=float(temperature),
        decode_fn=decode_fn,
        stop_sequences=("\n", "<END>"),
        uml_pressure=pressure,
    )
    full = str(out.get("text") or "")
    suffix = full[len(prompt) :] if full.startswith(prompt) else full
    cont = continue_uml_response(
        suffix,
        registry=reg,
        n_expected=len(user_text),
        prefer_efficient=prefer_efficient,
    )
    receipt = {
        "schema_version": "speak_uml_native_v1",
        "path": "text_encode_uml_generate_decode",
        "user_text": user_text,
        "model_prompt": prompt,
        "encode": native["encode"],
        "generate": out.get("receipt"),
        "continue": cont,
        "surface_out": cont.get("surface"),
        "roundtrip_ok": cont.get("status") == "PASS" and cont.get("surface") == user_text,
    }
    return {
        "user_text": user_text,
        "model_prompt": prompt,
        "raw_generation": full,
        "surface": cont.get("surface"),
        "equations": cont.get("equations_final"),
        "receipt": receipt,
        "generate": out,
    }


__all__ = ["speak_uml_native"]
