"""GGUF voice backend via llama-cpp-python — speak-only peripheral.

CPU remains the mind. GPU layers only accelerate voice render.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_LLM = None
_LOADED_PATH: str | None = None


def _voice_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    if cfg is None:
        from lib.model_config import load_config

        cfg = load_config()
    return dict(cfg.get("voice") or {})


def gguf_path(cfg: dict[str, Any] | None = None) -> Path:
    voice = _voice_cfg(cfg)
    raw = voice.get("gguf_path") or ""
    return Path(str(raw))


def gguf_ready(cfg: dict[str, Any] | None = None) -> bool:
    p = gguf_path(cfg)
    return p.is_file() and p.stat().st_size > 1_000_000


def llama_cpp_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("llama_cpp") is not None


def unload() -> None:
    global _LLM, _LOADED_PATH
    with _LOCK:
        _LLM = None
        _LOADED_PATH = None


def _get_llm(cfg: dict[str, Any] | None = None) -> Any:
    global _LLM, _LOADED_PATH
    if not llama_cpp_available():
        raise RuntimeError("llama-cpp-python not installed")
    from llama_cpp import Llama

    voice = _voice_cfg(cfg)
    path = gguf_path(cfg)
    if not path.is_file():
        raise FileNotFoundError(f"voice GGUF missing: {path}")
    key = str(path.resolve())
    with _LOCK:
        if _LLM is not None and _LOADED_PATH == key:
            return _LLM
        n_gpu = int(voice.get("n_gpu_layers", 33))
        n_ctx = int(voice.get("n_ctx", 2048))
        n_threads = int(voice.get("n_threads", 8))
        _LLM = Llama(
            model_path=str(path),
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu,
            n_threads=n_threads,
            verbose=False,
            chat_format=str(voice.get("chat_format") or "chatml"),
        )
        _LOADED_PATH = key
        return _LLM


def generate(
    prompt: str,
    *,
    max_tokens: int = 96,
    temperature: float = 0.35,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Completion-style generate from packet prompt."""
    if not gguf_ready(cfg):
        return {"ok": True, "silent": True, "text": None, "error": "gguf_missing", "mode": "llama_cpp"}
    if not llama_cpp_available():
        return {
            "ok": True,
            "silent": True,
            "text": None,
            "error": "llama_cpp_missing",
            "mode": "llama_cpp",
        }
    try:
        llm = _get_llm(cfg)
        voice = _voice_cfg(cfg)
        stop = voice.get("stop") or ["</s>", "<|im_end|>", "<|endoftext|>"]
        out = llm(
            prompt,
            max_tokens=max(8, int(max_tokens)),
            temperature=float(temperature),
            stop=list(stop),
            echo=False,
        )
        text = str((out.get("choices") or [{}])[0].get("text") or "").strip()
        return {
            "ok": True,
            "silent": False,
            "text": text,
            "model": str(gguf_path(cfg).name),
            "mode": "llama_cpp",
            "n_gpu_layers": int(voice.get("n_gpu_layers", 33)),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "silent": True,
            "text": None,
            "error": str(exc),
            "mode": "llama_cpp",
        }


def chat(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 96,
    temperature: float = 0.35,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Chat-completions path (preferred for Instruct GGUFs)."""
    if not gguf_ready(cfg):
        return {"ok": True, "silent": True, "text": None, "error": "gguf_missing", "mode": "llama_cpp"}
    if not llama_cpp_available():
        return {
            "ok": True,
            "silent": True,
            "text": None,
            "error": "llama_cpp_missing",
            "mode": "llama_cpp",
        }
    try:
        llm = _get_llm(cfg)
        voice = _voice_cfg(cfg)
        out = llm.create_chat_completion(
            messages=messages,
            max_tokens=max(8, int(max_tokens)),
            temperature=float(temperature),
            stop=list(voice.get("stop") or ["</s>", "<|im_end|>"]),
        )
        msg = ((out.get("choices") or [{}])[0].get("message") or {})
        text = str(msg.get("content") or "").strip()
        return {
            "ok": True,
            "silent": False,
            "text": text,
            "model": str(gguf_path(cfg).name),
            "mode": "llama_cpp",
            "n_gpu_layers": int(voice.get("n_gpu_layers", 33)),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "silent": True,
            "text": None,
            "error": str(exc),
            "mode": "llama_cpp",
        }


def status(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    path = gguf_path(cfg)
    return {
        "backend": "llama_cpp",
        "gguf_path": str(path).replace("\\", "/"),
        "gguf_ready": gguf_ready(cfg),
        "llama_cpp_installed": llama_cpp_available(),
        "loaded": _LOADED_PATH is not None,
        "size_mb": round(path.stat().st_size / (1024 * 1024), 1) if path.is_file() else None,
    }
