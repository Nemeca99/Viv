#!/usr/bin/env python3
"""Validate preparation-only per-tag prompt datasets."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from build_tag_prompt_datasets_v1 import EOS, PACKET_SCHEMA, SCHEMA_VERSION, TAGS, validate_row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.output_dir / "TAG_DATASETS_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["packet_schema"] == PACKET_SCHEMA
    assert manifest["dataset_tags"] == list(TAGS)
    assert manifest["row_total"] == 42
    assert manifest["target_type"] == "response_only_next_token"
    for key in ("training_authorized", "run_authorized", "lease_opened", "authorization_changed", "deployment_changed"):
        assert manifest[key] is False, key

    seen_pairs: set[str] = set()
    counts: dict[str, dict[str, int]] = {}
    escaped_injection_seen = False
    row_total = 0
    for tag in TAGS:
        path = args.output_dir / f"{tag}.jsonl"
        raw = path.read_bytes()
        info = manifest["datasets"][tag]
        assert hashlib.sha256(raw).hexdigest() == info["sha256"]
        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line]
        assert len(rows) == 6
        counts[tag] = dict(Counter(row["split"] for row in rows))
        assert counts[tag] == {"train": 4, "development": 1, "holdout": 1}
        for row in rows:
            assert row["schema_version"] == SCHEMA_VERSION
            assert row["dataset_tag"] == tag
            assert row["response_eos_token"] == EOS
            assert validate_row(row, tag) == []
            assert row["pair_hash"] not in seen_pairs
            seen_pairs.add(row["pair_hash"])
            assert row["text"] == row["prompt"] + row["response"] + EOS
            if tag == "user_request" and "&lt;telemetry&gt;" in row["prompt"]:
                escaped_injection_seen = True
            row_total += 1
    assert row_total == manifest["row_total"] == 42
    assert len(seen_pairs) == 42
    assert escaped_injection_seen
    print(json.dumps({"status": "PASS", "rows": row_total, "datasets": len(TAGS), "counts_by_tag": counts}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
