#!/usr/bin/env python3
"""Compatibility shim — implementation moved to legacy/rerank_continue_4450_phase_a.py."""
from __future__ import annotations

import runpy
from pathlib import Path

_LEGACY = Path(__file__).resolve().parent / "legacy" / "rerank_continue_4450_phase_a.py"
runpy.run_path(str(_LEGACY), run_name="__main__")
