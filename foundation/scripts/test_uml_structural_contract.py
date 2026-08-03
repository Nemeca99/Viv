"""Bounded regression checks for UML value + structural verification."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.uml_engine import (  # noqa: E402
    decode_word,
    encode_word,
    evaluate,
    structural_signature,
    verify,
    word_encoding_options,
)


CASES = ("A", "CAT", "[C,A,T]", "[1,>2,3<]", "<10,0>")


def main() -> int:
    rows = []
    for expr in CASES:
        value, node, _notation, _trace = evaluate(expr)
        ok, report = verify(expr)
        row = {
            "expr": expr,
            "value": str(value),
            "verify_ok": bool(ok),
            "report": report,
            "signature": repr(structural_signature(node)),
        }
        rows.append(row)
        if not ok:
            raise AssertionError(json.dumps(row, ensure_ascii=False))
    packed = encode_word("Viv", mode="packed")
    expanded = encode_word("Viv", mode="sum")
    assert packed == "Viv"
    assert decode_word(packed) == "Viv"
    assert expanded == "[V,i,v]"
    options = word_encoding_options("Viv")
    assert options["packed"]["chars"] < options["expanded_sum"]["chars"]
    rows.append({"word": "Viv", "packed": packed, "expanded": expanded, "options": options})
    print(json.dumps({"ok": True, "cases": rows}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
