#!/usr/bin/env python3
"""Evaluate local week1 adapter artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

WEEK1_ROOT = Path(__file__).resolve().parents[1]


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else WEEK1_ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate local week1 mouth alignment adapter.")
    parser.add_argument(
        "--manifest",
        default="artifacts/week1/aligned/alignment_manifest.json",
        help="Path to aligned manifest JSON",
    )
    parser.add_argument(
        "--model",
        default="artifacts/week1/model/adapter_model.json",
        help="Path to adapter model JSON",
    )
    parser.add_argument(
        "--output",
        default="artifacts/week1/eval/eval_report.json",
        help="Path to evaluation report JSON",
    )
    args = parser.parse_args()

    manifest = json.loads(_resolve_path(args.manifest).read_text(encoding="utf-8"))
    model = json.loads(_resolve_path(args.model).read_text(encoding="utf-8"))
    utterances = manifest.get("utterances", [])

    mean_confidence = model.get("mean_confidence", 0.0)
    coverage = len([u for u in utterances if u.get("label") in model.get("label_distribution", {})])
    coverage_ratio = coverage / max(len(utterances), 1)

    report = {
        "status": "pass" if mean_confidence >= 0.6 and coverage_ratio >= 0.95 else "inconclusive",
        "mean_confidence": mean_confidence,
        "label_coverage_ratio": round(coverage_ratio, 4),
        "utterance_count": len(utterances),
    }

    output_path = _resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"status={report['status']}")
    print(f"output={output_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
