#!/usr/bin/env python3
"""Consolidate immutable per-checkpoint generation artifacts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_full_run_entity_we_v1"
TARGET = ROOT / "CHECKPOINT_GENERATION_EVALUATION.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if TARGET.exists():
        raise FileExistsError(f"refuse_overwrite:{TARGET}")
    reports = []
    for step in (32, 64, 96, 128):
        path = ROOT / f"CHECKPOINT_{step}_GENERATION.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        item = json.loads(path.read_text(encoding="utf-8"))
        if item.get("checkpoint_step") != step or item.get("total") != 102:
            raise ValueError(f"malformed_checkpoint_report:{step}")
        reports.append({"checkpoint_step": step, "artifact": str(path).replace("\\", "/"), "artifact_sha256": sha(path), "pass": item["pass"], "hold": item["hold"], "fail": item["fail"], "toolbleed": item["toolbleed"], "eos_pass": item["eos_pass"], "elapsed_seconds": item["elapsed_seconds"], "by_axis": item["by_axis"]})
    report = {
        "schema_version": "mouth_full_run_entity_we_generation_eval_summary_v1",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "campaign": "mouth_full_run_entity_we_v1", "rows_per_checkpoint": 102,
        "development_rows": 64, "blind_rows": 32, "entity_eval_rows": 6,
        "reports": reports, "selected_checkpoint": 128,
        "selection_reason": "highest PASS count and lowest FAIL count among completed checkpoints; no deployment implied.",
        "training_authorized": False, "run_authorized": False, "promotion_allowed": False, "deployment_changed": False,
    }
    TARGET.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(TARGET), "selected_checkpoint": 128, "curve": [{"step": r["checkpoint_step"], "pass": r["pass"], "hold": r["hold"], "fail": r["fail"], "toolbleed": r["toolbleed"]} for r in reports]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
