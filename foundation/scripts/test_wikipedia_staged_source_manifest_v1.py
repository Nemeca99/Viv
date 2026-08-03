#!/usr/bin/env python3
"""Contract checks for the bounded source-manifest builder."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_wikipedia_staged_source_manifest_v1 import build  # noqa: E402


def main() -> int:
    result = build(offset=0, limit=1)
    assert result["state"] == "VERIFIED", result
    assert result["selection"]["selected"] == 1
    assert result["authority"]["vectors_written"] is False
    assert result["authority"]["training_authorized"] is False
    row = result["rows"][0]
    assert row["contained"] and row["exists"]
    assert len(row["source_sha256"]) == 64
    assert row["indexed_bytes"] == row["observed_bytes"]
    assert row["title"]
    print(json.dumps({"ok": True, "state": result["state"], "rows": len(result["rows"]), "authority_closed": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
