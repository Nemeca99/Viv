#!/usr/bin/env python3
"""Selftest U_AM shadow parity, aggregation, and single-writer control."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
for path in (FOUNDATION, MODEL, SANDBOX):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib import uml_engine
from uml_u_am_shadow import UAMShadowObserver, shadow_session


def main() -> int:
    assert not uml_engine.evaluation_observer_status()["active"]
    with tempfile.TemporaryDirectory(prefix="uml_u_am_shadow_") as tmp:
        telemetry = Path(tmp) / "usage.jsonl"
        with shadow_session(
            experiment_id="u_am_shadow_selftest_v1",
            source="test",
            telemetry_path=telemetry,
            flush_every=5,
        ) as observer:
            assert uml_engine.evaluate("(1+2)*3")[0] == 9
            assert uml_engine.evaluate("4*(5+6)")[0] == 44
            assert uml_engine.evaluate("(2*3)+4")[0] == 10
            assert uml_engine.evaluate("7+8")[0] == 15
            assert uml_engine.evaluate("(9-2)*3")[0] == 21
            assert observer.status()["window_total_requests"] == 0  # auto-flushed
            try:
                uml_engine.install_evaluation_observer(
                    lambda *_args: None,
                    experiment_id="competing_selftest",
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("competing observer was not rejected")

        assert not uml_engine.evaluation_observer_status()["active"]
        rows = [
            json.loads(line)
            for line in telemetry.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == 1
        row = rows[0]
        assert row["source"] == "test"
        assert row["total_requests"] == 5
        assert row["federation_counts"]["U_AM"] == 2
        assert row["federation_counts"]["U_SM"] == 1
        assert row["errors"] == 0
        assert row["outcome"] == "PASS"

        fail_path = Path(tmp) / "fail.jsonl"
        failing = UAMShadowObserver(
            experiment_id="u_am_shadow_fail_closed_selftest",
            source="test",
            telemetry_path=fail_path,
            flush_every=10,
        )
        failing._function = lambda _x, _y, _z: -999  # type: ignore[assignment]
        failing.start()
        try:
            uml_engine.evaluate("(1+2)*3")
        except RuntimeError:
            pass
        else:
            raise AssertionError("parity mismatch did not fail closed")
        finally:
            failing.stop()

    assert not uml_engine.evaluation_observer_status()["active"]
    print(
        "UML_U_AM_SHADOW_SELFTEST_PASS total=5 eligible=2 "
        "competing_writer=rejected production_rows=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
