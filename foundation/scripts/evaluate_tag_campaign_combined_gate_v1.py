#!/usr/bin/env python3
"""Apply the combined lexical, semantic, containment, and authority gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def gate(candidate: dict, baseline: dict, semantic: dict, *, min_semantic_pass_rate: float = 0.5) -> dict:
    summary = candidate["summary"]
    baseline_summary = baseline["summary"]
    semantic_report = semantic["report"]
    total = int(semantic_report["total"])
    semantic_pass_rate = int(semantic_report["pass"]) / max(1, total)
    lexical_nonempty = int(summary["nonempty"]) == int(summary["rows"])
    containment_clean = int(summary["leakage"]) == 0 and int(semantic_report["toolbleed"]) == 0
    semantic_clean = int(semantic_report["fail"]) == 0 and semantic_pass_rate >= min_semantic_pass_rate
    lexical_improved = float(summary["mean_word_recall"]) > float(baseline_summary["mean_word_recall"])
    authority_closed = candidate.get("training_authorized") is False and candidate.get("run_authorized") is False and candidate.get("promotion_allowed") is False and candidate.get("deployment_changed") is False
    passed = all((lexical_nonempty, containment_clean, semantic_clean, lexical_improved, authority_closed))
    return {"schema_version": "aios_tag_campaign_combined_gate_v1", "status": "PASS" if passed else "HOLD", "checks": {"lexical_nonempty": lexical_nonempty, "containment_clean": containment_clean, "semantic_clean": semantic_clean, "lexical_improved_over_baseline": lexical_improved, "authority_closed": authority_closed}, "candidate_mean_word_recall": summary["mean_word_recall"], "baseline_mean_word_recall": baseline_summary["mean_word_recall"], "semantic_pass_rate": semantic_pass_rate, "semantic_pass": semantic_report["pass"], "semantic_hold": semantic_report["hold"], "semantic_fail": semantic_report["fail"], "candidate_eval": candidate.get("adapter"), "promotion_allowed": False, "deployment_changed": False, "reason": "promotion remains separately governed; this is an evaluation gate only."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--semantic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = gate(load(args.candidate), load(args.baseline), load(args.semantic))
    if args.output.exists():
        raise FileExistsError(f"refuse_to_overwrite:{args.output}")
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
