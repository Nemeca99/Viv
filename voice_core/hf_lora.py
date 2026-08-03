#!/usr/bin/env python3
"""Local HF+LoRA generate for Viv voice (replaces Ollama when adapter present)."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1] / "foundation"
BASE = FOUNDATION / "models" / "gpu" / "OpenAster1-128k-base-hf"
ADAPTER = FOUNDATION / "models" / "gpu" / "viv_voice_lora"

_lock = threading.Lock()
_bundle: dict[str, Any] | None = None


def adapter_ready(adapter_path: Path | str | None = None) -> bool:
    selected = Path(adapter_path) if adapter_path is not None else ADAPTER
    return (selected / "adapter_config.json").is_file() and (BASE / "config.json").is_file()


def unload() -> None:
    """Free GPU weights between PRT collect and train (same process)."""
    global _bundle
    with _lock:
        if _bundle is None:
            return
        try:
            import gc

            torch = _bundle.get("torch")
            _bundle["model"] = None
            _bundle["tok"] = None
            _bundle = None
            gc.collect()
            if torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            _bundle = None


def _load(adapter_path: Path):
    global _bundle
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(str(adapter_path), trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    # Avoid accelerate device_map path (WeightConverter kwargs clash on some builds)
    model = AutoModelForCausalLM.from_pretrained(
        str(BASE),
        torch_dtype=torch.float16,
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(model, str(adapter_path))
    model.to("cuda")
    model.eval()
    _bundle = {"tok": tok, "model": model, "torch": torch, "device": "cuda", "adapter_path": str(adapter_path.resolve())}
    return _bundle


def generate(
    prompt: str,
    *,
    max_new_tokens: int = 80,
    temperature: float = 0.5,
    adapter_path: Path | str | None = None,
) -> dict[str, Any]:
    global _bundle
    selected = Path(adapter_path) if adapter_path is not None else ADAPTER
    if not adapter_ready(selected):
        return {"ok": True, "silent": True, "text": None, "error": "adapter_missing", "mode": "hf_lora"}
    with _lock:
        try:
            selected_key = str(selected.resolve())
            if _bundle is not None and _bundle.get("adapter_path") != selected_key:
                _bundle = None
            b = _bundle or _load(selected)
            tok = b["tok"]
            model = b["model"]
            torch = b["torch"]
            device = b["device"]
            inputs = tok(prompt, return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            gen_kwargs: dict[str, Any] = {
                "max_new_tokens": min(int(max_new_tokens), 96),
                "pad_token_id": tok.eos_token_id,
                "eos_token_id": tok.eos_token_id,
                "no_repeat_ngram_size": 3,
                "repetition_penalty": 1.2,
            }
            # Greedy is more stable for short speak prompts on MoE base+LoRA
            if temperature <= 0.2:
                gen_kwargs["do_sample"] = False
            else:
                gen_kwargs["do_sample"] = True
                gen_kwargs["temperature"] = float(temperature)
                gen_kwargs["top_p"] = 0.9
            with torch.no_grad():
                out = model.generate(**inputs, **gen_kwargs)
            gen = out[0][inputs["input_ids"].shape[-1] :]
            text = tok.decode(gen, skip_special_tokens=True).strip()
            # Hard stop at first runaway clause for speak
            if " only only" in f" {text} ":
                text = text.split(" only only")[0].strip()
                if text and not text.endswith("."):
                    text = text + "."
            return {
                "ok": True,
                "silent": False,
                "text": text,
                "model": "viv-voice-lora",
                "mode": "hf_lora",
            }
        except Exception as ex:  # noqa: BLE001
            return {
                "ok": True,
                "silent": True,
                "text": None,
                "error": str(ex),
                "mode": "hf_lora",
            }
