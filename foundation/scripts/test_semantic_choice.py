"""Test personality-shaped choice within a verified equivalence class."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.semantic_choice import ExpressionCandidate, choose_equivalent  # noqa: E402


def main() -> int:
    candidates = [
        ExpressionCandidate("I can verify the facts.", "verify_facts", 4.0, clarity=0.95, warmth=0.75),
        ExpressionCandidate("I verify facts.", "verify_facts", 3.0, clarity=0.85, warmth=0.35),
        ExpressionCandidate("Facts verified.", "verify_facts", 2.0, clarity=0.65, warmth=0.1),
    ]
    result = choose_equivalent(candidates, s_n=0.55)
    assert result["ok"] is True
    assert result["chosen"]["semantic_key"] == "verify_facts"
    assert len(result["ranked"]) == 3
    try:
        choose_equivalent(candidates + [ExpressionCandidate("Unknown", "other", 1.0)])
    except ValueError:
        pass
    else:
        raise AssertionError("mixed semantic classes must be rejected")
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
