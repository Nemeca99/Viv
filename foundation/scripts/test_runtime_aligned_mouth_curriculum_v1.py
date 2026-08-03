#!/usr/bin/env python3
"""Verify runtime-aligned curriculum rows and authority closure."""
from __future__ import annotations

import json
import argparse
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
sys.path.insert(0, str(REPO))
from voice_core.acronym_registry import validate_acronym_usage  # noqa: E402

DEFAULT_ROOT = FOUNDATION / "artifacts/auto/agentic/tag_prompt_datasets_20260802T035146Z/output_runtime_aligned_v3"
TAGS = ("identity", "knowledge", "telemetry", "user_request", "allowed_actions", "unknowns", "rendering_rules")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    root = parser.parse_args().root
    manifest = json.loads((root / "TAG_DATASETS_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["training_authorized"] is False and manifest["run_authorized"] is False
    total = 0
    for tag in TAGS:
        rows = [json.loads(line) for line in (root / f"{tag}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        assert {row["split"] for row in rows} == {"train", "development", "holdout"}
        for row in rows:
            assert "Prompt-Version:" in row["prompt"]
            assert "Semantic-Class:" in row["prompt"]
            assert row["text"] == row["prompt"] + row["response"] + row["response_eos_token"]
            assert row["response_start_char"] == len(row["prompt"])
            assert row["response_end_char"] == len(row["prompt"]) + len(row["response"])
            assert not validate_acronym_usage(row["response"])
            total += 1
    print(f"RUNTIME_ALIGNED_CURRICULUM_PASS rows={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
