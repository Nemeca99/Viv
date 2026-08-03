#!/usr/bin/env python3
"""Read-only final rescore after the tool-boundary contract expansion."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_cross_axis_micro_v1"
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402


def main() -> int:
    source_path = ROOT / "FULL_96_EVALUATION.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    cases = []
    counts: dict[str, int] = {}
    axes: dict[str, dict[str, int]] = {}
    for item in source["report"]["cases"]:
        result = judge(item["generated"], axis=item["axis"], ask=item.get("ask", ""))
        case = dict(item)
        case.update(status=result["status"], reason=result.get("deterministic", {}).get("reason"))
        cases.append(case)
        counts[case["status"]] = counts.get(case["status"], 0) + 1
        axes.setdefault(case["axis"], {})
        axes[case["axis"]][case["status"]] = axes[case["axis"]].get(case["status"], 0) + 1
    output = {
        "schema_version": "mouth_cross_axis_micro_full96_rescore_v3_0",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": str(source_path).replace("\\", "/"),
        "counts": counts,
        "by_axis": axes,
        "toolbleed": sum(case.get("toolbleed", 0) for case in cases),
        "cases": cases,
        "promotion_allowed": False,
        "deployment_changed": False,
        "run_authorized": False,
        "training_authorized": False,
    }
    target = ROOT / "FULL_96_RESCORE_V3_0.json"
    if target.exists():
        raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(target), "counts": counts, "by_axis": axes, "toolbleed": output["toolbleed"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
