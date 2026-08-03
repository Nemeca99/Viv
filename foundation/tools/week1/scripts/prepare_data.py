#!/usr/bin/env python3
"""Prepare raw speech rows into a normalized JSON dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

WEEK1_ROOT = Path(__file__).resolve().parents[1]


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else WEEK1_ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare week1 raw speech rows.")
    parser.add_argument(
        "--input",
        default="data/raw_samples.jsonl",
        help="Input JSONL with raw samples",
    )
    parser.add_argument(
        "--output",
        default="artifacts/week1/prepared/prepared_samples.json",
        help="Output normalized JSON file",
    )
    args = parser.parse_args()

    input_path = _resolve_path(args.input)
    output_path = _resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    with input_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            rows.append(
                {
                    "utterance_id": str(payload["utterance_id"]),
                    "audio_path": str(payload["audio_path"]),
                    "transcript": str(payload["transcript"]).strip(),
                }
            )

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump({"schema_version": "week1.v1", "samples": rows}, handle, indent=2)
        handle.write("\n")

    print(f"prepared_rows={len(rows)}")
    print(f"output={output_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
