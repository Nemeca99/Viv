#!/usr/bin/env python3
"""Compatibility shim — implementation moved to legacy/analyze_val_errors.py."""
from __future__ import annotations

import runpy
from pathlib import Path

_LEGACY = Path(__file__).resolve().parent / "legacy" / "analyze_val_errors.py"
runpy.run_path(str(_LEGACY), run_name="__main__")
