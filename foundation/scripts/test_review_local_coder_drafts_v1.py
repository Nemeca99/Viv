#!/usr/bin/env python3
"""Regression checks for static local-coder draft review."""
from __future__ import annotations

import tempfile
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from review_local_coder_drafts_v1 import review_root  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="draft-review-") as raw:
        root = Path(raw)
        (root / "good.txt").write_text("```python\ndef f():\n    return 1\n```\n", encoding="utf-8")
        (root / "bad.txt").write_text("```python\nimport subprocess\nsubprocess.run(['x'])\n```\n", encoding="utf-8")
        report = review_root(root)
        assert report["draft_count"] == 2
        assert report["syntax_failures"] == 0
        assert report["risk_cases"] == 1
        assert report["semantic_review_required"] is True
        assert report["integration_allowed"] is False
    print("ok: draft extraction, syntax review, risk flagging, and non-integration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
