"""Compare UML symbolic cost with the local OpenAster tokenizer."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.uml_engine import encode_word, uml_cost, word_encoding_options  # noqa: E402

DEFAULT_TOKENIZER = ROOT / "models" / "gpu" / "OpenAster1-128k-base-hf" / "tokenizer.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("words", nargs="*", default=["A", "CAT", "Viv", "Intellexi", "physics"])
    parser.add_argument("--tokenizer", default=str(DEFAULT_TOKENIZER))
    args = parser.parse_args()
    try:
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(args.tokenizer)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"tokenizer_unavailable:{exc}"}))
        return 1

    rows = []
    for word in args.words:
        options = word_encoding_options(word)
        row = {"word": word, "standard": {"chars": len(word)}}
        standard = tokenizer.encode(word)
        row["standard"]["tokens"] = len(standard.ids)
        row["standard"]["token_strings"] = standard.tokens
        row["uml"] = {}
        for label, info in options.items():
            expr = str(info["uml"])
            encoded = tokenizer.encode(expr)
            row["uml"][label] = {
                **uml_cost(expr),
                "tokenizer_tokens": len(encoded.ids),
                "tokenizer_token_strings": encoded.tokens,
            }
        rows.append(row)
    print(json.dumps({"ok": True, "tokenizer": args.tokenizer, "rows": rows}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
