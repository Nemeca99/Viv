#!/usr/bin/env python3
"""Benchmark the canonical UML and source-faithful knowledge lanes.

This is a read-only capability benchmark.  It does not claim that a factual
retrieval query and a calculation are interchangeable; instead it measures
each lane on the problem family it is authoritative for, records correctness
and latency, and leaves routing policy to a later evidence-based decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.knowledge_external_adapters import query_legacy_wikipedia  # noqa: E402
from lib.uml_engine import evaluate, verify  # noqa: E402


MATH_CASES = (
    {"case_id": "math_01", "expr": "[3,4]", "expected": 7.0},
    {"case_id": "math_02", "expr": "{10,3}", "expected": 7.0},
    {"case_id": "math_03", "expr": ">6,7<", "expected": 42.0},
    {"case_id": "math_04", "expr": "<{8,2},3>", "expected": 2.0},
    {"case_id": "math_05", "expr": "^3[2]", "expected": 8.0},
    {"case_id": "math_06", "expr": "![5]", "expected": 120.0},
    {"case_id": "math_07", "expr": "%[17,5]", "expected": 2.0},
    {"case_id": "math_08", "expr": "[pi,pi]", "expected": 6.283185307179586},
)

SOURCE_CASES = (
    {"case_id": "source_01", "query": "Albert Einstein", "expected_title": "Albert Einstein"},
    {"case_id": "source_02", "query": "Photosynthesis", "expected_title": "Photosynthesis"},
    {"case_id": "source_03", "query": "Evolution", "expected_title": "Evolution"},
    {"case_id": "source_04", "query": "Ada Lovelace", "expected_title": "Ada Lovelace"},
    {"case_id": "source_05", "query": "Economy of Angola", "expected_title": "Economy of Angola"},
    {"case_id": "source_06", "query": "Apple Inc", "expected_title": "Apple Inc."},
    {"case_id": "source_07", "query": "Asparagales", "expected_title": "Asparagales"},
    {"case_id": "source_08", "query": "Autism", "expected_title": "Autism"},
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def close_enough(actual: object, expected: float) -> bool:
    try:
        return abs(float(actual) - expected) <= max(1e-9, abs(expected) * 1e-9)
    except (TypeError, ValueError):
        return False


def run_math() -> list[dict[str, object]]:
    rows = []
    for case in MATH_CASES:
        started = time.perf_counter_ns()
        checked_report = None
        try:
            value, _node, notation, trace = evaluate(case["expr"])
            checked_ok, checked_report = verify(case["expr"])
            ok = close_enough(value, float(case["expected"])) and bool(checked_ok)
            error = None
            result = value
        except Exception as exc:  # noqa: BLE001 — receipt records a failed case
            ok = False
            error = f"{type(exc).__name__}:{exc}"
            result = None
            notation = None
            trace = []
        rows.append(
            {
                **case,
                "lane": "uml",
                "status": "VERIFIED" if ok else "INCONCLUSIVE",
                "correct": ok,
                "result": result,
                "notation": notation,
                "trace_events": len(trace or []),
                "verification_report": checked_report if 'checked_report' in locals() else None,
                "elapsed_ms": (time.perf_counter_ns() - started) / 1_000_000,
                "error": error,
            }
        )
    return rows


def run_source() -> list[dict[str, object]]:
    rows = []
    for case in SOURCE_CASES:
        started = time.perf_counter_ns()
        try:
            result = query_legacy_wikipedia(
                case["query"], limit=3, max_chars=12000, resolve_redirects=True
            )
            facts = result.get("facts") or []
            expected = str(case["expected_title"]).casefold()
            matching = [
                fact for fact in facts
                if expected == str(fact.get("claim", "")).split(":", 1)[-1].casefold()
            ]
            ok = result.get("state") == "VERIFIED" and bool(matching)
            error = None
        except Exception as exc:  # noqa: BLE001 — receipt records a failed case
            result = {}
            facts = []
            matching = []
            ok = False
            error = f"{type(exc).__name__}:{exc}"
        rows.append(
            {
                **case,
                "lane": "source_retrieval",
                "status": "VERIFIED" if ok else "INCONCLUSIVE",
                "correct": ok,
                "fact_count": len(facts),
                "matching_fact_count": len(matching),
                "retrieval_mode": result.get("mode"),
                "elapsed_ms": (time.perf_counter_ns() - started) / 1_000_000,
                "error": error,
            }
        )
    return rows


def summarize(rows: list[dict[str, object]], lane: str) -> dict[str, object]:
    selected = [row for row in rows if row["lane"] == lane]
    verified = sum(bool(row["correct"]) for row in selected)
    latencies = [float(row["elapsed_ms"]) for row in selected]
    return {
        "lane": lane,
        "cases": len(selected),
        "verified": verified,
        "verification_rate": verified / len(selected) if selected else 0.0,
        "mean_elapsed_ms": sum(latencies) / len(latencies) if latencies else None,
        "min_elapsed_ms": min(latencies) if latencies else None,
        "max_elapsed_ms": max(latencies) if latencies else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(
            FOUNDATION
            / "artifacts"
            / "auto"
            / "knowledge"
            / f"uml_source_efficiency_benchmark_v1_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        ),
    )
    args = parser.parse_args()
    rows = run_math() + run_source()
    receipt = {
        "schema": "uml_source_efficiency_benchmark_v1",
        "created_utc": utc_now(),
        "authority": {
            "read_only": True,
            "training_authorized": False,
            "run_authorized": False,
            "persistent_index_written": False,
            "carma_admission": False,
            "live_mutation": False,
        },
        "interpretation": "Capability-family benchmark; latency is not compared across non-equivalent problem families.",
        "summaries": [summarize(rows, "uml"), summarize(rows, "source_retrieval")],
        "rows": rows,
    }
    payload = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    print(json.dumps({"status": "PASS" if all(row["correct"] for row in rows) else "HOLD", "output": str(output), "sha256": digest, "summaries": receipt["summaries"]}, indent=2))
    return 0 if all(row["correct"] for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
