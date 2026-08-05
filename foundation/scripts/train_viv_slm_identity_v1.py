"""Compatibility entry point for the canonical Training/Viv-SLM trainer."""
from __future__ import annotations

from pathlib import Path
import runpy


CANONICAL = (
    Path(__file__).resolve().parents[1]
    / "models"
    / "Training"
    / "current"
    / "viv_slm"
    / "train_viv_slm_identity_v1.py"
)

if __name__ == "__main__":
    runpy.run_path(str(CANONICAL), run_name="__main__")
else:
    globals().update(runpy.run_path(str(CANONICAL), run_name=__name__))
