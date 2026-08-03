"""First-time GPU voice setup: HF login, download base AWQ, install vLLM."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _run(cmd: list[str], *, check: bool = True) -> int:
    print("$", " ".join(cmd))
    proc = subprocess.run(cmd)
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")
    return int(proc.returncode)


def print_hf_steps() -> None:
    print(
        """
=== Hugging Face (one-time, ~5 minutes) ===
1. Create free account: https://huggingface.co/join
2. Open https://huggingface.co/meta-llama/Meta-Llama-3.1-8B
   Click "Agree and access repository" (Meta license — required for base Llama).
3. Create a token: https://huggingface.co/settings/tokens (Read access is enough).
4. In this terminal run:
     python -m pip install -U huggingface_hub
     python -c "from huggingface_hub import login; login()"
   Paste your token when prompted.
"""
    )


def vllm_supported_here() -> tuple[bool, str]:
    if sys.platform == "win32":
        return False, "Official vLLM targets Linux/WSL2; native Windows needs a community build or WSL2."
    ver = sys.version_info
    if ver >= (3, 14):
        return False, f"Python {ver.major}.{ver.minor} is ahead of vLLM's tested range (3.10–3.13); use 3.12 in WSL2."
    return True, ""


def install_packages(*, install_vllm: bool) -> None:
    _run([sys.executable, "-m", "pip", "install", "-U", "huggingface_hub"])
    if install_vllm:
        ok, reason = vllm_supported_here()
        if not ok:
            print(f"Skipping vLLM install: {reason}")
            return
        print("Installing vLLM (may take several minutes)...")
        _run([sys.executable, "-m", "pip", "install", "-U", "vllm"])


def download_awq(cfg: dict[str, Any]) -> Path:
    voice = cfg["voice"]
    local = Path(voice["awq_model"])
    repo = voice["awq_hf"]
    local.mkdir(parents=True, exist_ok=True)
    if (local / "config.json").is_file():
        print(f"AWQ already present: {local}")
        return local
    print(f"Downloading {repo} → {local}")
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=repo, local_dir=str(local))
    return local


def bootstrap(cfg: dict[str, Any], *, install_vllm: bool = True, download: bool = True) -> dict[str, Any]:
    report: dict[str, Any] = {"steps": []}

    print_hf_steps()
    report["steps"].append("printed_hf_instructions")

    try:
        install_packages(install_vllm=install_vllm)
        report["steps"].append("pip_install_ok")
    except RuntimeError as ex:
        report["pip_error"] = str(ex)
        report["steps"].append("pip_install_failed")
        return report

    if download:
        try:
            path = download_awq(cfg)
            report["awq_path"] = str(path)
            report["steps"].append("awq_download_ok")
        except RuntimeError as ex:
            report["download_error"] = str(ex)
            report["steps"].append("awq_download_failed — run HF login first")
            return report

    report["next"] = (
        f"python {_voice_main_hint()} voice-serve"
        if vllm_supported_here()[0]
        else "HF login + AWQ download done; install vLLM in WSL2 (Python 3.12) before voice-serve"
    )
    return report


def _voice_main_hint() -> str:
    p = Path(__file__).resolve().parents[1] / "model_main.py"
    return str(p)
