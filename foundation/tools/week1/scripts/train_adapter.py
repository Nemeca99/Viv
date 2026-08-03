#!/usr/bin/env python3
"""Train a tiny local adapter artifact from aligned labels."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

WEEK1_ROOT = Path(__file__).resolve().parents[1]


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else WEEK1_ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description="Train local week1 mouth alignment adapter.")
    parser.add_argument(
        "--manifest",
        default="artifacts/week1/aligned/alignment_manifest.json",
        help="Path to aligned manifest JSON",
    )
    parser.add_argument(
        "--validation_report",
        default="artifacts/week1/validation/validation_report.json",
        help="Path to validation report JSON",
    )
    parser.add_argument(
        "--output",
        default="artifacts/week1/model/adapter_model.json",
        help="Path to adapter model JSON",
    )
    args = parser.parse_args()

    validation = json.loads(_resolve_path(args.validation_report).read_text(encoding="utf-8"))
    if validation.get("status") != "pass":
        raise SystemExit("validation report must be pass before training")

    manifest = json.loads(_resolve_path(args.manifest).read_text(encoding="utf-8"))
    utterances = manifest.get("utterances", [])
    label_counts = Counter(item["label"] for item in utterances)
    avg_conf = sum(float(item["confidence"]) for item in utterances) / max(len(utterances), 1)

    model = {
        "schema_version": "week1.v1",
        "adapter_type": "mouth-alignment-rule-adapter",
        "trained_on_utterances": len(utterances),
        "label_distribution": dict(label_counts),
        "mean_confidence": round(avg_conf, 4),
    }

    output_path = _resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")

    print(f"trained_on={len(utterances)}")
    print(f"output={output_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
