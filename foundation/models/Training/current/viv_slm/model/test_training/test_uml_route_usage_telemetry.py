#!/usr/bin/env python3
"""Selftest for schema-locked aggregate UML route telemetry."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from uml_route_usage_telemetry import (
    EVENT,
    SCHEMA_VERSION,
    append_route_usage_window,
    build_route_usage_window,
)


def _must_raise(callable_obj, *args, **kwargs) -> None:
    try:
        callable_obj(*args, **kwargs)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    window = build_route_usage_window(
        source="test",
        experiment_id="telemetry_selftest_v1",
        actor="test_uml_route_usage_telemetry",
        started_at=started,
        total_requests=100,
        federation_counts={"U+AM": 80, "U_AS": 20},
        duration_ns=50_000,
        errors=0,
        stalls=0,
        heartbeat_progressed=True,
    )
    assert window.schema_version == SCHEMA_VERSION
    assert window.event == EVENT
    assert window.federation_counts == {"U_AM": 80, "U_AS": 20}

    with tempfile.TemporaryDirectory(prefix="uml_route_usage_") as tmp:
        target = Path(tmp) / "usage.jsonl"
        append_route_usage_window(target, window)
        rows = [
            json.loads(line)
            for line in target.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == 1
        assert rows[0]["source"] == "test"
        assert rows[0]["total_requests"] == 100
        assert rows[0]["federation_counts"]["U_AM"] == 80

    common = {
        "experiment_id": "telemetry_selftest_v1",
        "actor": "selftest",
        "started_at": started,
        "total_requests": 10,
        "federation_counts": {"U_AM": 10},
        "duration_ns": 1,
    }
    _must_raise(build_route_usage_window, source="synthetic_as_production", **common)
    _must_raise(
        build_route_usage_window,
        source="test",
        **{**common, "federation_counts": {"U_UNKNOWN": 10}},
    )
    _must_raise(
        build_route_usage_window,
        source="test",
        **{
            **common,
            "federation_counts": {"U_AM": 11},
        },
    )
    print("UML_ROUTE_USAGE_TELEMETRY_SELFTEST_PASS rows=1 production_rows=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
