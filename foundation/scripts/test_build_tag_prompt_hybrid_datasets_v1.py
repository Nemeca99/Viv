#!/usr/bin/env python3
"""Validate the hybrid v3 plus governed-mouth bridge curriculum."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION / "scripts"))
from build_tag_prompt_datasets_v1 import TAGS, validate_row  # noqa: E402


def main() -> int:
    root = FOUNDATION / "artifacts/auto/agentic/tag_prompt_datasets_20260802T035146Z/output_hybrid_v1"
    manifest = json.loads((root / "TAG_DATASETS_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["row_total"] == 434
    assert manifest["bridge_source_rows"] == 308
    seen: set[str] = set()
    totals = Counter()
    for tag in TAGS:
        path = root / f"{tag}.jsonl"
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == manifest["datasets"][tag]["sha256"]
        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line]
        assert dict(Counter(row["split"] for row in rows))["train"] >= 12
        for row in rows:
            assert validate_row(row, tag) == []
            assert row["pair_hash"] not in seen
            seen.add(row["pair_hash"])
            totals[row["split"]] += 1
    assert len(seen) == 434
    assert totals["development"] == 21 and totals["holdout"] == 21
    assert totals["train"] == 392
    assert manifest["training_authorized"] is False and manifest["run_authorized"] is False
    print(json.dumps({"status": "PASS", "datasets": 7, "rows": len(seen), "counts_by_split": dict(totals)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
