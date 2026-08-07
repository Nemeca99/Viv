#!/usr/bin/env python3
"""Compatibility shim — implementation moved to legacy/run_rid_metric_sweep_4200.py."""
from __future__ import annotations

import runpy
from pathlib import Path

_LEGACY = Path(__file__).resolve().parent / "legacy" / "run_rid_metric_sweep_4200.py"
runpy.run_path(str(_LEGACY), run_name="__main__")
