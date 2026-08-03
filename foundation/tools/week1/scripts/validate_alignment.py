#!/usr/bin/env python3
"""Run schema and expectation checks for aligned speech labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from alignment_manifest_validator import validate_manifest

WEEK1_ROOT = Path(__file__).resolve().parents[1]


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else WEEK1_ROOT / path


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def run_expectations(manifest: dict, suite: dict) -> list[str]:
    errors: list[str] = []
    utterances = manifest.get("utterances", [])
    expectation_config = suite.get("expectations", [])

    for item in expectation_config:
        etype = item.get("expectation_type")
        kwargs = item.get("kwargs", {})
        column = kwargs.get("column")
        if not column:
            continue

        values = [row.get(column) for row in utterances]
        if etype == "expect_column_values_to_not_be_null":
            if any(value is None for value in values):
                errors.append(f"{column}: null value present")
        elif etype == "expect_column_values_to_be_between":
            minimum = kwargs.get("min_value")
            maximum = kwargs.get("max_value")
            for value in values:
                if value is None or value < minimum or value > maximum:
                    errors.append(f"{column}: value {value} outside [{minimum}, {maximum}]")
        elif etype == "expect_column_values_to_be_in_set":
            allowed = set(kwargs.get("value_set", []))
            for value in values:
                if value not in allowed:
                    errors.append(f"{column}: value {value} not in {sorted(allowed)}")
        elif etype == "expect_column_pair_values_A_to_be_less_than_B":
            column_b = kwargs.get("column_B")
            for row in utterances:
                value_a = row.get(column)
                value_b = row.get(column_b)
                if value_a is None or value_b is None or value_a >= value_b:
                    errors.append(f"{column} must be < {column_b}, got {value_a} >= {value_b}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate week1 alignment output.")
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
    parser.add_argument(
        "--suite",
        default="great_expectations/expectations/aligned_speech_labels_suite.json",
        help="Path to expectation suite JSON",
    )
    parser.add_argument(
        "--report",
        default="artifacts/week1/validation/validation_report.json",
        help="Path to validation report JSON",
    )
    args = parser.parse_args()

    manifest = load_json(_resolve_path(args.manifest))
    schema = load_json(_resolve_path(args.schema))
    suite = load_json(_resolve_path(args.suite))

    schema_errors = validate_manifest(manifest=manifest, schema=schema)
    expectation_errors = run_expectations(manifest=manifest, suite=suite)

    all_errors = schema_errors + expectation_errors
    status = "pass" if not all_errors else "fail"
    report = {
        "status": status,
        "schema_error_count": len(schema_errors),
        "expectation_error_count": len(expectation_errors),
        "errors": all_errors,
        "utterance_count": len(manifest.get("utterances", [])),
    }

    report_path = _resolve_path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"status={status}")
    print(f"report={report_path.as_posix()}")
    if all_errors:
        for err in all_errors:
            print(f"- {err}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
