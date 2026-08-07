#!/usr/bin/env python3
"""Compatibility shim — implementation moved to legacy/run_rid_adapter_ab.py."""
from __future__ import annotations

import runpy
from pathlib import Path

_LEGACY = Path(__file__).resolve().parent / "legacy" / "run_rid_adapter_ab.py"
runpy.run_path(str(_LEGACY), run_name="__main__")
