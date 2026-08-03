"""Measure token/energy scaling across deterministic random word sizes."""
from __future__ import annotations

import argparse
import json
import random
import string
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.model_config import load_config  # noqa: E402
from lib.uml_engine import encode_word  # noqa: E402
from scripts.measure_token_cost import measure_generation, measure_tokenizer  # noqa: E402

TOKENIZER_PATH = ROOT / "models" / "gpu" / "OpenAster1-128k-base-hf" / "tokenizer.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-length", type=int, default=1)
    parser.add_argument("--max-length", type=int, default=12)
    parser.add_argument("--step", type=int, default=2)
    parser.add_argument("--samples-per-length", type=int, default=2)
    parser.add_argument("--tokenizer-repeats", type=int, default=300)
    parser.add_argument("--generation-repeats", type=int, default=2)
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--seed", type=int, default=52)
    args = parser.parse_args()
    if args.min_length < 1 or args.max_length < args.min_length:
        raise SystemExit("invalid length range")
    try:
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(str(TOKENIZER_PATH))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"tokenizer_unavailable:{exc}"}))
        return 1
    rng = random.Random(args.seed)
    cfg = load_config()
    # Warm model before collecting samples so first-load energy is separate.
    warmup = measure_generation(" ", cfg=cfg, max_tokens=1)
    rows = []
    for length in range(args.min_length, args.max_length + 1, max(1, args.step)):
        for sample_index in range(max(1, args.samples_per_length)):
            word = "".join(rng.choice(string.ascii_letters) for _ in range(length))
            forms = {
                "standard": word,
                "uml_packed": encode_word(word, mode="packed"),
                "uml_expanded": encode_word(word, mode="sum"),
            }
            tokenization = {
                label: measure_tokenizer(tokenizer, text, max(1, args.tokenizer_repeats))
                for label, text in forms.items()
            }
            generation = {
                label: measure_generation(
                    text,
                    cfg=cfg,
                    max_tokens=max(1, args.max_tokens),
                    repeats=max(1, args.generation_repeats),
                )
                for label, text in forms.items()
            }
            rows.append({"length": length, "sample": sample_index, "word": word, "tokenization": tokenization, "generation": generation})
    report = {
        "ok": True,
        "at": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "tokenizer": str(TOKENIZER_PATH).replace("\\", "/"),
        "config": vars(args),
        "warmup": warmup,
        "rows": rows,
    }
    out = ROOT / "artifacts" / "auto" / "uml_token_measurements" / f"scaling_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "rows": len(rows), "report_path": str(out).replace("\\", "/")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
