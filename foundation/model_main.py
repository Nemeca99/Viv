#!/usr/bin/env python3
"""
Viv foundation — Model main.

ARCHITECTURE (see deepseekviv.md):
  CPU  = neuro-symbolic REASONING (required) — RID, UML, automation, Guardian, CARMA.
         No RLHF transformer mind. Retrieve, compute, verify. 1 Hz. Cannot hallucinate.
  GPU  = optional VOICE (peripheral) — stateless base transformer (no RLHF).
         Translates CPU output to natural language only. No memory, no decisions.
         If GPU is off, Viv still runs — she goes silent.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.model_config import CONFIG_PATH, load_config, models_root
from lib.reasoning_check import run_reasoning_smoke
from lib.vllm_launcher import (
    build_vllm_cmd,
    launch_vllm,
    print_install_hint as voice_hint,
    resolve_awq_model,
    vllm_installed,
)
from lib.voice_bootstrap import bootstrap, print_hf_steps
from lib.voice_corpus import build_voice_corpus

VERSION = "1.1.0"


def cmd_config(args: argparse.Namespace) -> int:
    cfg = load_config(Path(args.config) if args.config else None)
    if args.json:
        print(json.dumps(cfg, indent=2))
    else:
        print(f"reference: {cfg.get('reference', '')}")
        print(f"config: {CONFIG_PATH}")
        print("lane reasoning (CPU, required):", cfg["lanes"]["reasoning"]["role"])
        print("lane voice (GPU, optional):", cfg["lanes"]["voice"]["role"])
        print(f"voice AWQ: {resolve_awq_model(cfg)}")
        print(f"voice corpus: {cfg['training']['voice_corpus_out']}")
        print(f"policy.no_rlhf: {cfg['policy']['no_rlhf']}")
        print(f"policy.gpu_optional: {cfg['policy']['gpu_optional']}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    cfg = load_config()
    print("=== Viv model_main check ===")
    print(f"Python {sys.version.split()[0]}")
    print(f"models_root: {models_root(cfg)} (exists={models_root(cfg).is_dir()})")
    print()
    print("--- CPU reasoning lane (required) ---")
    smoke = run_reasoning_smoke(cfg)
    for name, row in smoke.items():
        if name == "all_ok" or not isinstance(row, dict):
            continue
        mark = "PASS" if row["ok"] else "FAIL"
        print(f"[{mark}] {name}: {row['detail'][:120]}")
    print(f"reasoning_all_ok: {smoke.get('all_ok')}")
    print()
    print("--- GPU voice lane (optional) ---")
    if vllm_installed():
        print("[PASS] vllm import")
    else:
        print("[SKIP] vllm not installed (OK if running silent)")
        voice_hint()
    # The current local voice contract uses Ollama/GGUF.  Older configs used
    # ``awq_model``; keep the voice lane optional without making a stale key
    # crash the required CPU reasoning check.
    voice_cfg = cfg.get("voice") or {}
    local = Path(voice_cfg.get("gguf_path") or voice_cfg.get("awq_model") or "")
    if local.is_dir() or local.is_file():
        print(f"[PASS] voice weights: {local}")
    else:
        print(f"[WARN] voice weights not on disk: {local}")
    return 0 if smoke.get("all_ok") else 1


def cmd_reasoning(_: argparse.Namespace) -> int:
    cfg = load_config()
    smoke = run_reasoning_smoke(cfg)
    print(json.dumps(smoke, indent=2))
    return 0 if smoke.get("all_ok") else 1


def cmd_voice_bootstrap(args: argparse.Namespace) -> int:
    cfg = load_config()
    if args.instructions_only:
        print_hf_steps()
        return 0
    report = bootstrap(cfg, install_vllm=not args.skip_vllm, download=not args.skip_download)
    print(json.dumps(report, indent=2))
    return 0 if "awq_download_ok" in report.get("steps", []) or args.skip_download else 1


def cmd_hf_login(_: argparse.Namespace) -> int:
    from huggingface_hub import login

    print("Paste your Hugging Face read token (from https://huggingface.co/settings/tokens)")
    login()
    print("Login complete.")
    return 0


def cmd_voice_corpus(_: argparse.Namespace) -> int:
    cfg = load_config()
    out = Path(cfg["training"]["voice_corpus_out"])
    counts = build_voice_corpus(out)
    print(f"wrote {out}")
    print(json.dumps(counts, indent=2))
    return 0 if counts.get("total", 0) > 0 else 1


def cmd_voice_serve(args: argparse.Namespace) -> int:
    return launch_vllm(load_config(), model=args.model)


def cmd_voice_dry(args: argparse.Namespace) -> int:
    cmd = build_vllm_cmd(load_config(), model=args.model)
    print(" ".join(cmd))
    return 0


def cmd_voice_smoke(args: argparse.Namespace) -> int:
    cfg = load_config()
    client = cfg["aios_client"]
    url = f"{client['vllm_base_url'].rstrip('/')}/chat/completions"
    body = json.dumps(
        {
            "model": client["vllm_model"],
            "messages": [
                {
                    "role": "system",
                    "content": "You are Viv's stateless voice. Translate only; do not decide or invent.",
                },
                {"role": "user", "content": args.prompt},
            ],
            "max_tokens": 96,
            "temperature": 0.7,
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        print(data["choices"][0]["message"]["content"])
        return 0
    except urllib.error.URLError as ex:
        print(f"Voice server not reachable: {ex}", file=sys.stderr)
        print("Optional: python model_main.py voice-serve", file=sys.stderr)
        print("Viv CPU reasoning does not require the GPU.", file=sys.stderr)
        return 2


def cmd_speak(args: argparse.Namespace) -> int:
    """Phase-1 speak via voice_core — soft-fail silent when no server."""
    from lib.voice_bridge import speak

    out = speak(args.prompt, memory_top=args.top, max_tokens=args.max_tokens)
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


def cmd_train_voice(args: argparse.Namespace) -> int:
    cfg = load_config()
    trainer = Path(cfg["training"]["trainer_script"])
    corpus = Path(args.data) if args.data else Path(cfg["training"]["voice_corpus_out"])
    if not corpus.is_file():
        print("Run: python model_main.py voice-corpus", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else Path(cfg["training"]["voice_adapter_out"])
    cmd = [
        sys.executable,
        str(trainer),
        "--data",
        str(corpus),
        "--out",
        str(out),
        "--identity",
        "Viv-Voice",
        "--generation",
        str(args.generation),
        "--max-steps",
        str(args.max_steps),
    ]
    print(f"Voice SFT on base (no RLHF): {cfg['training']['voice_base_hf']}")
    print(f"Update MODEL_PATH in generational_trainer.py to base weights before run.")
    print("Running:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(trainer.parent.parent))


def cmd_env(args: argparse.Namespace) -> int:
    cfg = load_config()
    c = cfg["aios_client"]
    print(f"set {c['env_voice_optional']}=1")
    print(f"set {c['env_silent_without_voice']}=1")
    print(f"set {c['env_voice_url']}={c['vllm_base_url']}")
    print(f"set AIOS_VLLM_MODEL={c['vllm_model']}")
    print("set AIOS_LLM_BASE_ONLY=1")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="model_main",
        description="Viv models — CPU reasoning (required) + GPU voice (optional).",
    )
    p.add_argument("--version", action="version", version=f"model_main {VERSION}")
    p.add_argument("--config", default="")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("config", help="Show lane roles and paths")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_config)

    sub.add_parser("check", help="Reasoning smoke + optional voice deps").set_defaults(func=cmd_check)
    sub.add_parser("reasoning", help="CPU neuro-symbolic stack smoke (JSON)").set_defaults(func=cmd_reasoning)

    vb = sub.add_parser("voice-bootstrap", help="First-time: pip install + download base AWQ")
    vb.add_argument("--instructions-only", action="store_true", help="Print HF steps only")
    vb.add_argument("--skip-vllm", action="store_true", help="Only install huggingface_hub + download")
    vb.add_argument("--skip-download", action="store_true", help="Only install packages")
    vb.set_defaults(func=cmd_voice_bootstrap)

    sub.add_parser("hf-login", help="Interactive Hugging Face token login").set_defaults(func=cmd_hf_login)
    sub.add_parser("voice-corpus", help="Build fluency corpus for GPU voice").set_defaults(func=cmd_voice_corpus)

    vs = sub.add_parser("voice-serve", help="Start optional vLLM AWQ voice server")
    vs.add_argument("--model", default=None)
    vs.set_defaults(func=cmd_voice_serve)

    vd = sub.add_parser("voice-dry", help="Print vLLM launch command")
    vd.add_argument("--model", default=None)
    vd.set_defaults(func=cmd_voice_dry)

    vm = sub.add_parser("voice-smoke", help="One completion against voice server")
    vm.add_argument("--prompt", default='State: {"S_n":0.71,"status":"ACTIVE"}. Speak this to the architect.')
    vm.set_defaults(func=cmd_voice_smoke)

    sk = sub.add_parser("speak", help="CPU intent packet → optional GPU/stub voice (soft-fail silent)")
    sk.add_argument("prompt", nargs="?", default="state summary")
    sk.add_argument("--top", type=int, default=3, help="CARMA memory top-k")
    sk.add_argument("--max-tokens", type=int, default=128)
    sk.set_defaults(func=cmd_speak)

    tv = sub.add_parser("train-voice", help="SFT LoRA on base for voice fluency only")
    tv.add_argument("--data", default="")
    tv.add_argument("--out", default="")
    tv.add_argument("--generation", type=int, default=1)
    tv.add_argument("--max-steps", type=int, default=200)
    tv.set_defaults(func=cmd_train_voice)

    sub.add_parser("env", help="Env vars for optional voice client wiring").set_defaults(func=cmd_env)

    # Back-compat aliases
    sub.add_parser("serve-gpu", help=argparse.SUPPRESS).set_defaults(func=cmd_voice_serve)
    sub.add_parser("serve-gpu-dry", help=argparse.SUPPRESS).set_defaults(func=cmd_voice_dry)
    sub.add_parser("smoke-gpu", help=argparse.SUPPRESS).set_defaults(func=cmd_voice_smoke)
    sub.add_parser("corpus", help=argparse.SUPPRESS).set_defaults(func=cmd_voice_corpus)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
