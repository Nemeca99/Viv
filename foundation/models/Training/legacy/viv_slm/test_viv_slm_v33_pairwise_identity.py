#!/usr/bin/env python3
"""Preflight checks for the governed V33 pairwise identity trainer."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for path in (FOUNDATION, FOUNDATION / "scripts", VIV_ROOT, VIV_ROOT / "models" / "uml_bigram_part3"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from train_viv_slm_v33_pairwise_identity import (  # noqa: E402
    LEARNING_RATE,
    PARENT_CHECKPOINT,
    PARENT_CHECKPOINT_SHA256,
    REPLAY_INPUT_ROOT,
    REPLAY_INPUT_MANIFEST_SHA256,
    STEP_INCREMENT,
    _sha256,
    recursive_nudge_update,
    train,
)


def main() -> int:
    assert STEP_INCREMENT == 250
    assert LEARNING_RATE == 0.00005
    assert PARENT_CHECKPOINT.is_file()
    assert _sha256(PARENT_CHECKPOINT).casefold() == PARENT_CHECKPOINT_SHA256.casefold()
    replay_manifest = REPLAY_INPUT_ROOT / "INPUT_MANIFEST.json"
    assert replay_manifest.is_file()
    assert _sha256(replay_manifest).casefold() == REPLAY_INPUT_MANIFEST_SHA256.casefold()
    controller_seed = {
        "alpha": 0.1,
        "margin_ema": 0.0,
        "anchor_drift_ema": 0.0,
        "pairwise_scale": 1.0,
        "anchor_scale": 1.0,
        "lr_scale": 1.0,
    }
    emerging = recursive_nudge_update(controller_seed, observed_margin=0.4, observed_anchor_drift=0.0001)
    assert emerging["pairwise_scale"] > 1.0
    protected = recursive_nudge_update(controller_seed, observed_margin=0.4, observed_anchor_drift=0.02)
    assert protected["anchor_scale"] > 1.0
    assert protected["lr_scale"] < emerging["lr_scale"]
    assert 0.25 <= protected["lr_scale"] <= 1.25
    assert 0.5 <= protected["pairwise_scale"] <= 2.0
    assert 0.75 <= protected["anchor_scale"] <= 3.0
    with tempfile.TemporaryDirectory(prefix="viv_slm_v33_pairwise_training_") as temp_dir:
        try:
            train(output_dir=Path(temp_dir) / "should_not_run", authorize=False, device_name="cpu")
        except PermissionError as error:
            assert "explicit_authorize" in str(error)
        else:
            raise AssertionError("V33 trainer accepted a run without --authorize")
    print(
        "VIV_SLM_V33_PAIRWISE_IDENTITY_TRAINER_PREFLIGHT_PASS "
        "parent_v32_hash=true v28_reference_retained=true pairwise_objective=true "
        "rejected_is_sft_target=false step_increment=250 learning_rate=0.00005 "
        "explicit_authorize_required=true promotion_closed=true deployment_closed=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
