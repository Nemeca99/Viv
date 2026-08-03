"""vLLM OpenAI-compatible server launcher (GPU / AWQ)."""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def vllm_installed() -> bool:
    return importlib.util.find_spec("vllm") is not None


def resolve_awq_model(cfg: dict[str, Any]) -> str:
    voice = cfg.get("voice") or cfg.get("gpu") or {}
    local = Path(str(voice.get("awq_model", "")))
    if local.is_dir() and any(local.glob("*.safetensors")) or (local / "config.json").is_file():
        return str(local)
    return str(voice.get("awq_hf") or voice.get("base_hf") or "")


def build_vllm_cmd(cfg: dict[str, Any], *, model: str | None = None) -> list[str]:
    voice = cfg.get("voice") or cfg.get("gpu") or {}
    model_id = model or resolve_awq_model(cfg)
    util = float(voice.get("gpu_memory_utilization", 0.85))
    max_len = int(voice.get("max_model_len", 4096))
    quant = str(voice.get("quantization", "awq"))
    host = str(voice.get("host", "127.0.0.1"))
    port = int(voice.get("port", 8000))
    served = str(voice.get("served_name", "viv-voice"))
    cmd = [
        sys.executable,
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        model_id,
        "--host",
        host,
        "--port",
        str(port),
        "--served-model-name",
        served,
        "--gpu-memory-utilization",
        str(util),
        "--max-model-len",
        str(max_len),
    ]
    if quant:
        cmd.extend(["--quantization", quant])
    return cmd


def launch_vllm(cfg: dict[str, Any], *, model: str | None = None) -> int:
    if not vllm_installed():
        print(
            "vLLM not installed. On this RTX 3060 Ti box:\n"
            "  pip install vllm\n"
            "Then place AWQ weights at model_config.json gpu.awq_model or set HF fallback.",
            file=sys.stderr,
        )
        return 2
    cmd = build_vllm_cmd(cfg, model=model)
    print("Launching:", " ".join(cmd))
    return subprocess.call(cmd)


def print_install_hint() -> None:
    print("Optional GPU voice (vLLM + AWQ base, no RLHF):")
    print("  pip install vllm")
    print("  Place AWQ base weights at model_config.json voice.awq_model")
    print("  python model_main.py voice-serve")
    print("  Viv runs without GPU — voice is silent, CPU reasoning continues.")
