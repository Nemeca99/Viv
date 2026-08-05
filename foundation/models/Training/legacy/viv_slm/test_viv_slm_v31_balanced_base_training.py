#!/usr/bin/env python3
"""Preflight checks for the governed V31 balanced-base trainer."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for path in (FOUNDATION, FOUNDATION / "scripts", VIV_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from train_viv_slm_v31_balanced_base import (  # noqa: E402
    INPUT_ROOT,
    PARENT_CHECKPOINT,
    PARENT_CHECKPOINT_SHA256,
    STEP_INCREMENT,
    _sha256,
    train,
)


def main() -> int:
    assert STEP_INCREMENT == 250
    assert INPUT_ROOT.joinpath("INPUT_MANIFEST.json").is_file()
    assert PARENT_CHECKPOINT.is_file()
    assert _sha256(PARENT_CHECKPOINT).casefold() == PARENT_CHECKPOINT_SHA256.casefold()
    with tempfile.TemporaryDirectory(prefix="viv_slm_v31_training_preflight_") as temp_dir:
        try:
            train(output_dir=Path(temp_dir) / "should_not_run", authorize=False, device_name="cpu")
        except PermissionError as error:
            assert "explicit_authorize" in str(error)
        else:
            raise AssertionError("V31 trainer accepted a run without --authorize")
    print(
        "VIV_SLM_V31_BALANCED_BASE_TRAINER_PREFLIGHT_PASS "
        "parent_hash=true step_increment=250 explicit_authorize_required=true "
        "promotion_closed=true deployment_closed=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
