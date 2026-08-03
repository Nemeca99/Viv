#!/usr/bin/env python3
"""Create a fresh immutable campaign from the corrected v4 corpus definition."""
from __future__ import annotations

from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_mouth_relationship_repair_micro_v4 as source  # noqa: E402

source.ROOT = FOUNDATION / (
    "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/"
    "campaigns/mouth_relationship_repair_micro_v4_1"
)

if __name__ == "__main__":
    raise SystemExit(source.main())
