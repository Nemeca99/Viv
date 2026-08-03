#!/usr/bin/env python3
"""Regression checks for the V3 runner's closed-by-default boundary."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from mouth_training_recovery_v3_runner import CAMPAIGN, run_experiment, validate_campaign  # noqa: E402


def main() -> int:
    report = validate_campaign(CAMPAIGN)
    assert report["status"] == "VALIDATION_PASS_AUTH_CLOSED"
    assert report["findings"] == []
    assert report["training_authorized"] is False
    assert report["run_authorized"] is False
    assert report["gpu_steps"] == 0
    try:
        run_experiment(root=CAMPAIGN)
    except PermissionError as exc:
        assert "run_authorized_false" in str(exc)
    else:
        raise AssertionError("closed_campaign_execution_not_refused")
    print("ok: runner validation pass; closed execution refused pre-security/pre-lease")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
