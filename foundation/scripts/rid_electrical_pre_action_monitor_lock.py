#!/usr/bin/env python3
"""Reconcile ops status and write pre-action training readiness monitor lock."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_pre_action_monitor_lock import (  # noqa: E402
    verify_monitor_lock_consistency,
    write_monitor_lock,
)


def main() -> int:
    lock = write_monitor_lock(reconcile=True, regression_check=True)
    verify = verify_monitor_lock_consistency()
    out = {"lock": lock, "verify": verify}
    print(json.dumps(out, indent=2))
    return 0 if lock.get("ok") and verify.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
