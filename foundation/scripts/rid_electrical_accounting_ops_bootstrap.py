#!/usr/bin/env python3
"""Bootstrap promote to production_accounting_operations.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_accounting_ops_bootstrap.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_accounting_ops import promote_ops_status  # noqa: E402


def main() -> int:
    result = promote_ops_status()
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "all_gates_pass": (result.get("bootstrap") or {}).get("all_gates_pass"),
                "gates": {
                    k: {"pass": v.get("pass")}
                    for k, v in ((result.get("bootstrap") or {}).get("gates") or {}).items()
                },
                "ops_review_required": result.get("ops_review_required"),
                "review_reason": result.get("review_reason"),
                "artifact": (result.get("artifacts") or {}).get("ops_status"),
            },
            indent=2,
        )
    )
    return 0 if result.get("status") == "production_accounting_operations" else 2


if __name__ == "__main__":
    raise SystemExit(main())
