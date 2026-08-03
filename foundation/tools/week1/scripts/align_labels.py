#!/usr/bin/env python3
"""Generate a deterministic local alignment manifest for week1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

WEEK1_ROOT = Path(__file__).resolve().parents[1]


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else WEEK1_ROOT / path


def infer_label(transcript: str) -> str:
    lowered = transcript.lower()
    if any(c in lowered for c in ("a", "e", "i", "o", "u")):
        return "vowel-heavy"
    return "consonant-heavy"


def main() -> int:
    parser = argparse.ArgumentParser(description="Align labels from prepared speech rows.")
    parser.add_argument(
        "--input",
        default="artifacts/week1/prepared/prepared_samples.json",
        help="Input prepared samples JSON",
    )
    parser.add_argument(
        "--output",
        default="artifacts/week1/aligned/alignment_manifest.json",
        help="Output alignment manifest JSON",
    )
    args = parser.parse_args()

    input_path = _resolve_path(args.input)
    output_path = _resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    prepared = json.loads(input_path.read_text(encoding="utf-8"))
    utterances = []
    for idx, sample in enumerate(prepared.get("samples", [])):
        transcript = sample["transcript"]
        duration_ms = max(200, min(3500, len(transcript) * 55))
        utterances.append(
            {
                "utterance_id": sample["utterance_id"],
                "audio_path": sample["audio_path"],
                "start_ms": 0,
                "end_ms": duration_ms,
                "label": infer_label(transcript),
                "confidence": 0.9 if len(transcript.split()) >= 2 else 0.75,
                "transcript": transcript,
                "alignment_engine": "week1-local-rule",
                "sequence_idx": idx,
            }
        )

    payload = {
        "schema_version": "week1.v1",
        "created_by": "foundation.tools.week1.align_labels",
        "utterances": utterances,
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"aligned_utterances={len(utterances)}")
    print(f"output={output_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
