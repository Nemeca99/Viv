#!/usr/bin/env python3
"""Validate the 126-row v3 tagged-packet curriculum."""
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
    root = FOUNDATION / "artifacts/auto/agentic/tag_prompt_datasets_20260802T035146Z/output_v4_expanded"
    manifest = json.loads((root / "TAG_DATASETS_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["row_total"] == 126
    assert manifest["split_policy"] == {"train": 12, "development": 3, "holdout": 3, "cross_tag_pair_overlap": 0}
    seen: set[str] = set()
    for tag in TAGS:
        path = root / f"{tag}.jsonl"
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == manifest["datasets"][tag]["sha256"]
        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line]
        assert len(rows) == 18
        assert dict(Counter(row["split"] for row in rows)) == {"train": 12, "development": 3, "holdout": 3}
        for row in rows:
            assert validate_row(row, tag) == []
            assert row["pair_hash"] not in seen
            seen.add(row["pair_hash"])
    assert len(seen) == 126
    assert manifest["training_authorized"] is False and manifest["run_authorized"] is False
    print(json.dumps({"status": "PASS", "datasets": 7, "rows": 126, "unique_pair_hashes": len(seen)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
