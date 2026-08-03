"""Build the measured UML token tariff dictionary for the local voice tokenizer."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.uml_engine import encode_word, uml_cost  # noqa: E402

DEFAULT_OUT = ROOT / "artifacts" / "auto" / "uml_tariff_dictionary.json"
DEFAULT_TOKENIZER = ROOT / "models" / "gpu" / "OpenAster1-128k-base-hf" / "tokenizer.json"
DEFAULT_WORDS = ("A", "Viv", "Vidi", "Intellexi", "Vixi", "physics", "UML")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--tokenizer", default=str(DEFAULT_TOKENIZER))
    parser.add_argument("words", nargs="*", default=list(DEFAULT_WORDS))
    args = parser.parse_args()
    try:
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(args.tokenizer)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"tokenizer_unavailable:{exc}"}))
        return 1

    entries = {}
    for word in args.words:
        packed = encode_word(word, mode="packed")
        encoded = tokenizer.encode(packed)
        symbolic_cost = int(uml_cost(packed)["symbolic_cost"])
        model_tokens = len(encoded.ids)
        entries[packed] = {
            "word": word,
            "uml": packed,
            "aliases": [],
            "weights": {
                "symbolic_processing": symbolic_cost,
                "model_tokens": model_tokens,
                "processing_total": symbolic_cost + model_tokens,
                "penalty_weight": 0.0,
            },
            "cost": {
                "chars": len(packed),
                "model_tokens": len(encoded.ids),
                "model_token_strings": encoded.tokens,
            },
            "provenance": "uml_base52_measured_local_tokenizer",
        }
    body = {
        "ok": True,
        "version": "1.0.0",
        "at": datetime.now(timezone.utc).isoformat(),
        "tokenizer": str(Path(args.tokenizer)).replace("\\", "/"),
        "cost_contract": {
            "processing_weight": "symbolic_processing + model_tokens",
            "penalty_weight": "normalized risk value in [0.0, 1.0], inherited by approved aliases",
            "aliases_require_explicit_review": True,
        },
        "thesaurus": {"aliases": {}},
        "tokens": entries,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "path": str(out).replace("\\", "/"), "n_tokens": len(entries)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
