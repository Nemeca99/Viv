#!/usr/bin/env python3
"""Regression checks for the closed overnight schedule contract."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from validate_mouth_training_schedule_v1 import DEFAULT_CAMPAIGN, validate_schedule  # noqa: E402


def main() -> int:
    source = json.loads((FOUNDATION / "scripts/mouth_training_schedule_v1.json").read_text(encoding="utf-8"))
    good = validate_schedule(source, DEFAULT_CAMPAIGN)
    assert good["status"] == "SCHEDULE_VALIDATION_PASS_AUTH_CLOSED"
    assert good["findings"] == []
    bad = copy.deepcopy(source)
    bad["runs"][0]["checkpoint_steps"] = [128, 64]
    assert validate_schedule(bad, DEFAULT_CAMPAIGN)["status"] == "SCHEDULE_VALIDATION_FAIL"
    bad = copy.deepcopy(source)
    bad["runs"][0]["authorization_file"] = "L:/outside/authorization.json"
    assert validate_schedule(bad, DEFAULT_CAMPAIGN)["status"] == "SCHEDULE_VALIDATION_FAIL"
    bad = copy.deepcopy(source)
    bad["automatic_retry"] = True
    assert validate_schedule(bad, DEFAULT_CAMPAIGN)["status"] == "SCHEDULE_VALIDATION_FAIL"
    print("ok: schedule schema, checkpoint, authorization-path, and no-retry gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
