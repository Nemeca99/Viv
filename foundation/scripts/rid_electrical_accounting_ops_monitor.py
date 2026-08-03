#!/usr/bin/env python3
"""Passive production accounting ops monitor (drift + mismatch + aggregates).

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_accounting_ops_monitor.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_accounting_ops import run_passive_monitor  # noqa: E402


def main() -> int:
    result = run_passive_monitor(apply_ops_status=True)
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "ops_review_required": result.get("ops_review_required"),
                "review_reason": result.get("review_reason"),
                "n_receipts_window": result.get("n_receipts_window"),
                "config_mismatch_count": result.get("config_mismatch_count"),
                "drift_v1": result.get("drift_v1"),
                "drift_v2": result.get("drift_v2"),
                "artifacts": result.get("artifacts"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
