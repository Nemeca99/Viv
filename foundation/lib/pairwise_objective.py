"""Reference-free pairwise objective shared by tests and the LoRA preflight."""
from __future__ import annotations

from typing import Any


def objective_values(
    chosen_logp: Any,
    rejected_logp: Any,
    *,
    sft_weight: float = 1.0,
    pairwise_weight: float = 0.5,
    beta: float = 1.0,
    margin: float = 0.2,
) -> dict[str, Any]:
    """Return the exact scalar loss and diagnostics.

    Inputs are mean response-token log probabilities.  Rejected text contributes
    only to the preference term and is never interpreted as a language-model
    target.
    """
    import torch

    raw_margin = chosen_logp - rejected_logp
    preference_logit = beta * raw_margin - margin
    pairwise = torch.nn.functional.softplus(-preference_logit)
    chosen_nll = -chosen_logp
    total = sft_weight * chosen_nll + pairwise_weight * pairwise
    return {
        "loss": total,
        "chosen_nll": chosen_nll,
        "pairwise_loss": pairwise,
        "raw_margin": raw_margin,
        "preference_logit": preference_logit,
        "pair_correct": raw_margin > 0,
    }


def detached_gradient_coefficients(
    chosen_logp: Any,
    rejected_logp: Any,
    *,
    sft_weight: float = 1.0,
    pairwise_weight: float = 0.5,
    beta: float = 1.0,
    margin: float = 0.2,
) -> tuple[Any, Any]:
    """Exact local gradients d(loss)/d(chosen_logp,rejected_logp).

    The trainer uses these detached coefficients to perform chosen and rejected
    forwards sequentially.  That avoids retaining both activation graphs on an
    8 GB card while preserving the first-order gradient exactly.
    """
    import torch

    with torch.no_grad():
        pressure = torch.sigmoid(-(beta * (chosen_logp - rejected_logp) - margin))
        chosen_coefficient = -sft_weight - pairwise_weight * beta * pressure
        rejected_coefficient = pairwise_weight * beta * pressure
    return chosen_coefficient, rejected_coefficient

