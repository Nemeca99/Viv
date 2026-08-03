#!/usr/bin/env python3
"""AIOS foundation health gate — bedrock checks before stacking upward."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.foundation_health import run_checks


def main() -> int:
    report = run_checks(include_stress=True)
    print(f"Foundation root: {report['foundation_root']}")
    print(f"RID artifacts: {report['rid_artifacts']}")
    print("-" * 60)
    for item in report["checks"]:
        tag = "PASS" if item["ok"] else "FAIL"
        print(f"[{tag}] {item['name']}: {item['detail']}")
    print("-" * 60)
    if report["ok"]:
        print("Foundation health: OK")
        return 0
    print(f"Foundation health: FAIL ({len(report['failed'])} check(s))")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
