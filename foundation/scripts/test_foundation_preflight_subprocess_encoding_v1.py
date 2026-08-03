#!/usr/bin/env python3
"""Regression for UTF-8 subprocess output and absent stderr handling."""
from __future__ import annotations

import sys

from run_foundation_preflight import _run_check


def main() -> int:
    result = _run_check(
        [
            sys.executable,
            "-X",
            "utf8",
            "-c",
            "print('utf8-check: ✓')",
        ]
    )
    assert result["returncode"] == 0, result
    assert "utf8-check" in result["stdout_tail"], result
    assert result["stderr_tail"] == "", result
    print({"ok": True, "stdout_contains_utf8_check": "utf8-check" in result["stdout_tail"], "stderr_tail": result["stderr_tail"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
