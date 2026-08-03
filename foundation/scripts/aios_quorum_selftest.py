#!/usr/bin/env python3
"""Bounded self-test for the local CPU quorum gate."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))
from lib.aios_quorum_gate import evaluate_quorum, load_policy


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="viv_quorum_") as raw:
        root = Path(raw)
        trigger = root / "trigger.json"
        trigger.write_text(json.dumps({"status": "verified"}), encoding="utf-8")
        policy_path = root / "policy.json"
        policy_path.write_text(json.dumps({"lanes": {"test": {"providers": [{"type": "trigger_file", "path": str(trigger), "expected_status": "verified", "max_age_seconds": 60}]}}}), encoding="utf-8")
        allowed = evaluate_quorum("run", load_policy(policy_path))
        assert allowed.allow and allowed.valid_count == allowed.required == 1
        trigger.write_text(json.dumps({"status": "absent"}), encoding="utf-8")
        denied = evaluate_quorum("run", load_policy(policy_path))
        assert not denied.allow and denied.valid_count == 0
    print("AIOS_QUORUM_SELFTEST_PASS cases=2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
