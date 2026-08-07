#!/usr/bin/env python3
"""Compatibility shim — implementation moved to legacy/mint_specialists.py.

WARNING: running this CLI overwrites checkpoints/efficient|deep with a tiny
vocab=26 mint. Prefer train_specialist / run_campaign for real specialists.
Pass --execute to actually mint (bare invocation prints this warning and exits).
"""
from __future__ import annotations

import sys
from pathlib import Path

_SANDBOX = Path(__file__).resolve().parent
if str(_SANDBOX) not in sys.path:
    sys.path.insert(0, str(_SANDBOX))

from legacy.mint_specialists import main  # noqa: E402

__all__ = ["main"]


if __name__ == "__main__":
    if "--execute" not in sys.argv[1:]:
        print(
            "mint_specialists shim: implementation in legacy/mint_specialists.py\n"
            "Refusing bare CLI run (overwrites efficient/deep specialists).\n"
            "Re-run with --execute only if you intentionally want the tiny mint.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    raise SystemExit(main())
