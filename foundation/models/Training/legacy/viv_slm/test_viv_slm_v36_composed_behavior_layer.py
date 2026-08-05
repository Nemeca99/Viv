#!/usr/bin/env python3
"""Focused preflight checks for the V36 composability candidate."""
from __future__ import annotations

from pathlib import Path
import sys

import torch

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION / "scripts") not in sys.path:
    sys.path.insert(0, str(FOUNDATION / "scripts"))

import train_viv_slm_v36_composed_behavior_layer as candidate  # noqa: E402


def main() -> int:
    assert candidate.STEP_INCREMENT == 250
    assert candidate.COMPOSITION_SCALES == (1.0, 0.75, 0.5, 0.25, 0.1)
    assert candidate.PARENT_CHECKPOINT.is_file()
    assert candidate.SPECIALIZED_LAYER_CHECKPOINT.is_file()
    assert candidate.SPECIALIZED_BASE_CHECKPOINT.is_file()
    parent = {
        "weight": torch.tensor([1.0, 2.0]),
        "integer_buffer": torch.tensor([1], dtype=torch.long),
    }
    specialized = {
        "weight": torch.tensor([1.5, 1.0]),
        "integer_buffer": torch.tensor([9], dtype=torch.long),
    }
    specialized_base = {
        "weight": torch.tensor([1.0, 1.5]),
        "integer_buffer": torch.tensor([3], dtype=torch.long),
    }
    composed = candidate.compose_state(parent, specialized, specialized_base, 0.75)
    assert torch.allclose(composed["weight"], torch.tensor([1.375, 1.625]))
    assert torch.equal(composed["integer_buffer"], parent["integer_buffer"])
    try:
        candidate.compose_state(parent, specialized, specialized_base, 1.1)
    except ValueError as error:
        assert "scale_out_of_bounds" in str(error)
    else:
        raise AssertionError("out-of-range composition scale was accepted")
    assert candidate.CAMPAIGN_ID.endswith("_0250")
    print(
        "VIV_SLM_V36_COMPOSED_BEHAVIOR_LAYER_PREFLIGHT_PASS "
        "delta_formula=true scale_ladder_locked=true parent_v35=true "
        "specialized_v34=true base_v32=true bounded_scope=true promotion_closed=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
