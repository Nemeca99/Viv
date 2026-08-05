#!/usr/bin/env python3
"""Preflight checks for the governed V32 lower-update-magnitude trainer."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for path in (FOUNDATION, FOUNDATION / "scripts", VIV_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from train_viv_slm_v32_balanced_low_lr import (  # noqa: E402
    INPUT_MANIFEST_SHA256,
    INPUT_ROOT,
    LEARNING_RATE,
    PARENT_CHECKPOINT,
    PARENT_CHECKPOINT_SHA256,
    STEP_INCREMENT,
    TENSOR_MANIFEST_SHA256,
    VOCAB_SHA256,
    _sha256,
    train,
)


def main() -> int:
    assert STEP_INCREMENT == 250
    assert LEARNING_RATE == 0.0001
    assert INPUT_ROOT.joinpath("INPUT_MANIFEST.json").is_file()
    assert _sha256(INPUT_ROOT / "INPUT_MANIFEST.json").casefold() == INPUT_MANIFEST_SHA256.casefold()
    assert _sha256(INPUT_ROOT / "VOCAB.json").casefold() == VOCAB_SHA256.casefold()
    assert _sha256(INPUT_ROOT / "tensor_dataset" / "MANIFEST.json").casefold() == TENSOR_MANIFEST_SHA256.casefold()
    assert PARENT_CHECKPOINT.is_file()
    assert _sha256(PARENT_CHECKPOINT).casefold() == PARENT_CHECKPOINT_SHA256.casefold()
    with tempfile.TemporaryDirectory(prefix="viv_slm_v32_training_preflight_") as temp_dir:
        try:
            train(output_dir=Path(temp_dir) / "should_not_run", authorize=False, device_name="cpu")
        except PermissionError as error:
            assert "explicit_authorize" in str(error)
        else:
            raise AssertionError("V32 trainer accepted a run without --authorize")
    print(
        "VIV_SLM_V32_BALANCED_LOW_LR_TRAINER_PREFLIGHT_PASS "
        "parent_hash=true input_hashes=true step_increment=250 learning_rate=0.0001 "
        "explicit_authorize_required=true promotion_closed=true deployment_closed=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
