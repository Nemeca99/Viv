"""Compatibility entry point for the canonical campaign preflight."""
from __future__ import annotations

from pathlib import Path
import runpy


CANONICAL = (
    Path(__file__).resolve().parents[1]
    / "models"
    / "Training"
    / "current"
    / "viv_slm"
    / "tests"
    / "test_run_viv_slm_layer_campaign.py"
)

if __name__ == "__main__":
    runpy.run_path(str(CANONICAL), run_name="__main__")
else:
    globals().update(runpy.run_path(str(CANONICAL), run_name=__name__))
