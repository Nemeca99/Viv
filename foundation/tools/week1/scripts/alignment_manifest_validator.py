#!/usr/bin/env python3
"""Validate week1 alignment manifests against a local JSON schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

WEEK1_ROOT = Path(__file__).resolve().parents[1]


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else WEEK1_ROOT / path


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_manifest(manifest: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_top = schema.get("required", [])
    for key in required_top:
        if key not in manifest:
            errors.append(f"missing top-level field: {key}")

    utterances = manifest.get("utterances")
    if not isinstance(utterances, list) or not utterances:
        errors.append("utterances must be a non-empty list")
        return errors

    allowed_labels = set(
        schema.get("properties", {})
        .get("utterances", {})
        .get("items", {})
        .get("properties", {})
        .get("label", {})
        .get("enum", [])
    )

    for idx, item in enumerate(utterances):
        if not isinstance(item, dict):
            errors.append(f"utterances[{idx}] must be an object")
            continue

        for field in ("utterance_id", "audio_path", "start_ms", "end_ms", "label", "confidence"):
            if field not in item:
                errors.append(f"utterances[{idx}] missing field: {field}")

        start_ms = item.get("start_ms")
        end_ms = item.get("end_ms")
        confidence = item.get("confidence")
        label = item.get("label")

        if isinstance(start_ms, int) and start_ms < 0:
            errors.append(f"utterances[{idx}] start_ms must be >= 0")
        if isinstance(end_ms, int) and end_ms <= 0:
            errors.append(f"utterances[{idx}] end_ms must be > 0")
        if isinstance(start_ms, int) and isinstance(end_ms, int) and end_ms <= start_ms:
            errors.append(f"utterances[{idx}] end_ms must be > start_ms")
        if not isinstance(confidence, (float, int)) or not 0.0 <= float(confidence) <= 1.0:
            errors.append(f"utterances[{idx}] confidence must be in [0.0, 1.0]")
        if allowed_labels and label not in allowed_labels:
            errors.append(f"utterances[{idx}] label '{label}' not in allowed label set")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an alignment manifest using local schema rules."
    )
    parser.add_argument(
        "--manifest",
        default="artifacts/week1/aligned/alignment_manifest.json",
        help="Path to alignment manifest JSON",
    )
    parser.add_argument(
        "--schema",
        default="schema/alignment_manifest.schema.json",
        help="Path to schema JSON",
    )
    args = parser.parse_args()

    manifest_path = _resolve_path(args.manifest)
    schema_path = _resolve_path(args.schema)
    manifest = _load_json(manifest_path)
    schema = _load_json(schema_path)

    errors = validate_manifest(manifest=manifest, schema=schema)
    if errors:
        print("validation=fail")
        for err in errors:
            print(f"- {err}")
        return 1

    print("validation=pass")
    print(f"utterance_count={len(manifest['utterances'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
