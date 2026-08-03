#!/usr/bin/env python3
"""Shim → models/Training/code/validate_judge_adapter.py"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "models" / "Training" / "code" / "validate_judge_adapter.py"
raise SystemExit(subprocess.call([sys.executable, str(TARGET), *sys.argv[1:]]))
