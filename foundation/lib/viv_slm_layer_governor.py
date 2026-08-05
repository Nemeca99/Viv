"""Compatibility import for the canonical Training/Viv-SLM governor."""
from __future__ import annotations

from pathlib import Path
import runpy


CANONICAL = (
    Path(__file__).resolve().parents[1]
    / "models"
    / "Training"
    / "current"
    / "viv_slm"
    / "viv_slm_layer_governor.py"
)

globals().update(runpy.run_path(str(CANONICAL), run_name="viv_slm_layer_governor_canonical"))
