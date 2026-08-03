#!/usr/bin/env python3
"""Growth strain under moderate plant pressure (GovernedFleet — not full blast).

Prefer: growth_main.py run-pressured
This script remains as a thin wrapper for audit paths.
"""
from __future__ import annotations

import multiprocessing
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PY = Path(r"L:\Continue\.venv\Scripts\python.exe")


def main() -> int:
    multiprocessing.freeze_support()
    cmd = [
        str(_PY if _PY.is_file() else sys.executable),
        str(_ROOT / "growth_main.py"),
        "run-pressured",
        "--seconds",
        "90",
        "--warm",
        "25",
        "--duty",
        "0.30",
    ]
    return int(subprocess.call(cmd, cwd=str(_ROOT)))


if __name__ == "__main__":
    raise SystemExit(main())
