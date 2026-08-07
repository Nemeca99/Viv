#!/usr/bin/env python3
"""Thin entrypoint: consciousness plan-only automation (delegates to cognitive cores runner).

    L:\\Continue\\.venv\\Scripts\\python.exe foundation\\scripts\\run_consciousness_automation_v1.py --plan-only
"""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from run_cognitive_cores_automation_v1 import main as _main  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if "--profile" not in args:
        args = ["--profile", "consciousness", *args]
    if "--plan-only" not in args and "--execute" not in args and "--list" not in args:
        args = [*args, "--plan-only"]
    return _main(args)


if __name__ == "__main__":
    raise SystemExit(main())
