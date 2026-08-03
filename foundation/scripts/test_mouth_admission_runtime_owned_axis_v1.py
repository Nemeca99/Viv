#!/usr/bin/env python3
"""Regression tests for keeping CPU-owned role refinements hold-only."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from scripts.admit_mouth_recovery_v3_campaign_v1 import reject_runtime_owned_axes  # noqa: E402


def main() -> int:
    reject_runtime_owned_axes([{"axis": "memory_ownership_and_service_attribution"}])
    try:
        reject_runtime_owned_axes([{"axis": "architecture_cpu_gpu_role"}])
    except ValueError as exc:
        assert str(exc) == "runtime_owned_axis_must_remain_hold_only:architecture_cpu_gpu_role"
    else:
        raise AssertionError("runtime-owned axis was admitted into optimizer path")
    print("RUNTIME_OWNED_AXIS_GUARD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
