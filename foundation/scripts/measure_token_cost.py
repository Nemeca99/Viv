"""Measure local tokenizer and Ollama GPU cost for standard vs UML forms."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.model_config import load_config  # noqa: E402
from lib.uml_engine import encode_word  # noqa: E402

TOKENIZER_PATH = ROOT / "models" / "gpu" / "OpenAster1-128k-base-hf" / "tokenizer.json"


def gpu_power_watts() -> float | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return float(out.strip().splitlines()[0].strip())
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        return None


def measure_tokenizer(tokenizer, text: str, repeats: int) -> dict[str, object]:
    start = time.perf_counter_ns()
    encoded = None
    for _ in range(repeats):
        encoded = tokenizer.encode(text)
    elapsed_ns = time.perf_counter_ns() - start
    return {
        "text": text,
        "tokens": len(encoded.ids if encoded else []),
        "token_strings": encoded.tokens if encoded else [],
        "repeats": repeats,
        "total_ms": round(elapsed_ns / 1e6, 4),
        "mean_us": round(elapsed_ns / repeats / 1e3, 4),
    }


def measure_generation(prompt: str, *, cfg: dict, max_tokens: int, repeats: int = 1) -> dict[str, object]:
    voice = dict(cfg.get("voice") or {})
    host = voice.get("host", "127.0.0.1")
    port = int(voice.get("port", 11434))
    model = voice.get("served_name") or "viv-voice-qwen"
    url = f"http://{host}:{port}/api/generate"
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": max_tokens, "num_ctx": 512},
        }
    ).encode("utf-8")
    samples: list[tuple[float, float]] = []
    stop = threading.Event()

    def poll() -> None:
        while not stop.is_set():
            power = gpu_power_watts()
            if power is not None:
                samples.append((time.perf_counter(), power))
            stop.wait(0.1)

    thread = threading.Thread(target=poll, daemon=True)
    thread.start()
    start = time.perf_counter()
    error = None
    text = ""
    for _ in range(max(1, repeats)):
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = str(data.get("response") or "")
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            break
    elapsed = time.perf_counter() - start
    stop.set()
    thread.join(timeout=2)
    watts = [p for _, p in samples]
    avg_w = sum(watts) / len(watts) if watts else None
    joules = avg_w * elapsed if avg_w is not None else None
    return {
        "prompt": prompt,
        "repeats": max(1, repeats),
        "model": model,
        "ok": error is None,
        "error": error,
        "elapsed_s": round(elapsed, 4),
        "gpu_samples": len(watts),
        "gpu_power_avg_w": round(avg_w, 3) if avg_w is not None else None,
        "gpu_power_min_w": round(min(watts), 3) if watts else None,
        "gpu_power_max_w": round(max(watts), 3) if watts else None,
        "gpu_energy_j_estimate": round(joules, 4) if joules is not None else None,
        "response_chars": len(text),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("word", nargs="?", default="Viv")
    parser.add_argument("--repeats", type=int, default=1000)
    parser.add_argument("--generation-repeats", type=int, default=5)
    parser.add_argument("--max-tokens", type=int, default=8)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    try:
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(str(TOKENIZER_PATH))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"tokenizer_unavailable:{exc}"}))
        return 1
    cfg = load_config()
    forms = {
        "standard": args.word,
        "uml_packed": encode_word(args.word, mode="packed"),
        "uml_expanded": encode_word(args.word, mode="sum"),
    }
    tokenization = {label: measure_tokenizer(tokenizer, text, max(1, args.repeats)) for label, text in forms.items()}
    # Warm Ollama once so the comparison excludes model-load startup cost.
    warmup = measure_generation(" ", cfg=cfg, max_tokens=1)
    generation = {
        label: measure_generation(
            text,
            cfg=cfg,
            max_tokens=max(1, args.max_tokens),
            repeats=max(1, args.generation_repeats),
        )
        for label, text in forms.items()
    }
    report = {"ok": True, "at": datetime.now(timezone.utc).isoformat(), "word": args.word, "tokenizer": str(TOKENIZER_PATH), "warmup": warmup, "tokenization": tokenization, "generation": generation}
    out = Path(args.out) if args.out else ROOT / "artifacts" / "auto" / "uml_token_measurements" / f"measure_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({**report, "report_path": str(out).replace("\\", "/")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
