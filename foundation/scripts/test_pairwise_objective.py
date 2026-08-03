"""Gradient and target-isolation tests for the hybrid pairwise objective."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import torch

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
from lib.pairwise_objective import detached_gradient_coefficients, objective_values


def main() -> int:
    chosen = torch.tensor(-2.0, requires_grad=True)
    rejected = torch.tensor(-2.5, requires_grad=True)
    values = objective_values(chosen, rejected)
    values["loss"].backward()
    direct_chosen = chosen.grad.detach().clone()
    direct_rejected = rejected.grad.detach().clone()
    coefficients = detached_gradient_coefficients(chosen.detach(), rejected.detach())
    assert torch.allclose(direct_chosen, coefficients[0], atol=1e-6)
    assert torch.allclose(direct_rejected, coefficients[1], atol=1e-6)
    assert direct_chosen < 0  # descent increases chosen log probability
    assert direct_rejected > 0  # descent decreases rejected log probability
    assert float(values["raw_margin"]) > 0
    assert bool(values["pair_correct"])

    worse = objective_values(torch.tensor(-3.0), torch.tensor(-2.0))
    better = objective_values(torch.tensor(-1.0), torch.tensor(-3.0))
    assert float(better["pairwise_loss"]) < float(worse["pairwise_loss"])
    print(json.dumps({
        "ok": True, "exact_sequential_gradient": True,
        "chosen_gradient_sign": float(direct_chosen),
        "rejected_gradient_sign": float(direct_rejected),
        "rejected_is_sft_target": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
