#!/usr/bin/env python3
"""Compile identity-claim patterns from an immutable staged ledger."""
from __future__ import annotations

import collections
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_recovery_staged_identity_ledger_v1_1"
OUT = ROOT / "IDENTITY_PATTERN_REPORT.json"


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_overwrite:{OUT}")
    by_step = {}
    phrase_counts = collections.Counter()
    category_counts = collections.Counter()
    examples = {}
    for path in sorted(ROOT.glob("checkpoint_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        step = payload["step"]
        step_categories = collections.Counter()
        step_phrases = collections.Counter()
        for case in payload["result"]["cases"]:
            for claim in case.get("identity_claims", []):
                category = claim["category"]
                phrase = claim["match"]
                category_counts[category] += 1
                phrase_counts[phrase] += 1
                step_categories[category] += 1
                step_phrases[phrase] += 1
                examples.setdefault(phrase, {
                    "step": step,
                    "category": category,
                    "status": case["status"],
                    "reason": case.get("reason"),
                    "axis": case["axis"],
                    "ask": case["ask"],
                    "generated": case["generated"],
                    "context": claim["context"],
                })
        by_step[str(step)] = {"categories": dict(step_categories), "phrases": dict(step_phrases)}
    report = {
        "schema_version": "mouth_identity_pattern_report_v1",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_ledger": str(ROOT).replace("\\", "/"),
        "by_step": by_step,
        "category_counts": dict(category_counts),
        "phrase_counts": dict(phrase_counts),
        "examples": examples,
        "interpretation": {
            "invented_compounds": "Unsupported compound AIOS names remain FAIL when asserted; they are logged for pattern analysis.",
            "human_like_language": "Human-like or natural communication is allowed; literal human identity remains disallowed.",
            "holds": "Incomplete but non-contradictory identity/role answers remain HOLD until they state the required relationship explicitly.",
        },
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(OUT).replace("\\", "/"), "category_counts": report["category_counts"], "phrase_counts": report["phrase_counts"]}, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
