"""Read-only behavioral evaluation for the repaired v2 full-run checkpoints."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
for candidate in (FOUNDATION, FOUNDATION.parent, Path(__file__).resolve().parent):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts import evaluate_mouth_full_run_entity_we_v1 as governed  # noqa: E402

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
governed.ROOT = TREE / "mouth_full_run_entity_we_v2"
governed.RUN = FOUNDATION / "models/Training/runs/mouth_full_run_entity_we_v2"
governed.REPORT = governed.ROOT / "CHECKPOINT_GENERATION_EVALUATION.json"


if __name__ == "__main__":
    raise SystemExit(governed.main())
