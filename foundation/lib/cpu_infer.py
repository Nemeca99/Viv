"""llama.cpp CPU inference helpers."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


def llama_cpp_installed() -> bool:
    return importlib.util.find_spec("llama_cpp") is not None


def resolve_gguf(cfg: dict[str, Any]) -> Path:
    p = Path(cfg["cpu"]["gguf_path"])
    return p


def smoke_generate(cfg: dict[str, Any], prompt: str, *, max_tokens: int = 64) -> str:
    if not llama_cpp_installed():
        raise RuntimeError("llama-cpp-python not installed (pip install llama-cpp-python)")
    from llama_cpp import Llama

    cpu = cfg["cpu"]
    path = resolve_gguf(cfg)
    if not path.is_file():
        raise FileNotFoundError(f"GGUF not found: {path}")
    llm = Llama(
        model_path=str(path),
        n_ctx=int(cpu.get("n_ctx", 4096)),
        n_gpu_layers=int(cpu.get("n_gpu_layers", 0)),
        n_threads=int(cpu.get("n_threads", 8)),
        verbose=False,
    )
    out = llm(prompt, max_tokens=max_tokens, temperature=0.7)
    return str(out["choices"][0]["text"])


def print_install_hint() -> None:
    print("CPU stack (llama.cpp):")
    print("  pip install llama-cpp-python")
    print("  Place base (non-RLHF) GGUF at model_config.json cpu.gguf_path")
    print("  python model_main.py smoke-cpu")
