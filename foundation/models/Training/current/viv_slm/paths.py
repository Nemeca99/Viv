"""Canonical paths for the self-contained Viv-SLM training package.

The runtime model, tokenizer, governor, supervisor, and campaign engine live
under ``foundation/models/Training``.  Historical checkpoints, input manifests,
and AIOS authority records remain in their existing governed locations and are
resolved explicitly from this single path module.
"""
from __future__ import annotations

from pathlib import Path


VIV_SLM_ROOT = Path(__file__).resolve().parent
TRAINING_ROOT = VIV_SLM_ROOT.parents[1]
FOUNDATION = TRAINING_ROOT.parents[1]
VIV_ROOT = FOUNDATION.parent
MODEL_ROOT = VIV_SLM_ROOT / "model"
CURRENT_ROOT = TRAINING_ROOT / "current"
RUN_ROOT = TRAINING_ROOT / "runs" / "viv_slm"
CHECKPOINT_ROOT = TRAINING_ROOT / "checkpoints" / "viv_slm"
EVIDENCE_ROOT = TRAINING_ROOT / "evidence" / "viv_slm"
KNOB_REGISTRY = CURRENT_ROOT / "TRAINING_KNOBS.json"
CANONICAL_PYTHON = Path(r"L:\Continue\.venv\Scripts\python.exe")


def viv_path(value: str | Path) -> Path:
    """Resolve a repository-relative path against the Viv root."""

    path = Path(str(value))
    return path if path.is_absolute() else VIV_ROOT / path


__all__ = [
    "CANONICAL_PYTHON",
    "CHECKPOINT_ROOT",
    "CURRENT_ROOT",
    "EVIDENCE_ROOT",
    "FOUNDATION",
    "KNOB_REGISTRY",
    "MODEL_ROOT",
    "RUN_ROOT",
    "TRAINING_ROOT",
    "VIV_ROOT",
    "VIV_SLM_ROOT",
    "viv_path",
]
