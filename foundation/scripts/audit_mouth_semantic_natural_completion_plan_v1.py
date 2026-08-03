#!/usr/bin/env python3
"""Record the evidence-based completion contract for the natural SFT corpus."""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v22_42"
CAMPAIGNS = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
SOURCES = [
    CAMPAIGNS / "mouth_semantic_refinement_v22_42/semantic_refinement_96_hold.jsonl",
    CAMPAIGNS / "mouth_semantic_natural_expansion_v1/semantic_natural_expansion_hold.jsonl",
]
OUT = ROOT / "SEMANTIC_NATURAL_COMPLETION_PLAN_V1.json"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    loaded = [row for path in SOURCES for row in rows(path)]
    current_axes = Counter(row["axis"] for row in loaded)
    final_targets = {
        "identity_humanization": 52,
        "architecture_cpu_gpu_role": 51,
        "memory_ownership_and_service_attribution": 51,
        "indirect_tool_agency": 51,
        "entity_we_boundary": 51,
    }
    additions = {axis: final_targets[axis] - current_axes[axis] for axis in final_targets}
    report = {
        "schema_version": "mouth_semantic_natural_completion_plan_v1",
        "status": "NATURAL_COMPLETION_PLAN_HOLD_ONLY",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "current_rows": len(loaded),
        "target_rows": 256,
        "additional_rows_required": sum(additions.values()),
        "current_axis_counts": dict(sorted(current_axes.items())),
        "target_axis_counts": final_targets,
        "additional_rows_by_axis": additions,
        "style_requirements_for_additions": {
            "declarative": 20,
            "imperative": 20,
            "colloquial": 20,
            "conditional": 20,
            "contrast": 20,
            "indirect_or_adversarial": 20,
        },
        "quality_contract": {
            "natural_unique_asks": True,
            "natural_unique_targets": True,
            "response_tokens_at_most": 45,
            "sentences_between": [1, 3],
            "response_only_supervision": True,
            "every_row_replays_pass": True,
            "all_judge_only_rows_excluded": True,
        },
        "sources": [str(path).replace("\\", "/") for path in SOURCES],
        "optimizer_eligible": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
        "next_action": "build_additional_natural_rows_under_this_contract",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "status": report["status"], "current_rows": len(loaded), "target_rows": 256, "additional_rows": report["additional_rows_required"], "output": str(OUT)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
