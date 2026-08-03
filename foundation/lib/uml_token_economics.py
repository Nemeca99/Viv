"""Measured cost and semantic-efficiency equations for UML tokens."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TokenEconomics:
    """Inputs to the token-cost contract.

    ``joules`` is optional until hardware telemetry is available. A missing
    value never gets replaced with a guessed energy figure.
    """

    symbolic_nodes: int
    neural_tokens: int
    dependency_depth: int
    verified_value: float
    risk_penalty: float = 0.0
    joules: float | None = None

    def calculate(
        self,
        *,
        w_symbolic: float = 1.0,
        w_neural: float = 1.0,
        w_depth: float = 1.0,
        w_energy: float = 1.0,
        joules_reference: float = 1.0,
        risk_lambda: float = 1.0,
    ) -> dict[str, Any]:
        if self.symbolic_nodes < 1 or self.neural_tokens < 1 or self.dependency_depth < 1:
            raise ValueError("token dimensions must be positive")
        if self.verified_value < 0 or not 0.0 <= self.risk_penalty <= 1.0:
            raise ValueError("verified_value must be non-negative and risk_penalty must be in [0,1]")
        if joules_reference <= 0:
            raise ValueError("joules_reference must be positive")
        if self.joules is not None and self.joules < 0:
            raise ValueError("joules must be non-negative")

        energy_term = 0.0 if self.joules is None else w_energy * (self.joules / joules_reference)
        processing_cost = (
            w_symbolic * self.symbolic_nodes
            + w_neural * self.neural_tokens
            + w_depth * self.dependency_depth
            + energy_term
        )
        tariff_cost = processing_cost * (1.0 + risk_lambda * self.risk_penalty)
        return {
            **asdict(self),
            "energy_observed": self.joules is not None,
            "energy_term": round(energy_term, 8),
            "processing_cost": round(processing_cost, 8),
            "tariff_cost": round(tariff_cost, 8),
            "semantic_efficiency": round(self.verified_value / processing_cost, 8)
            if processing_cost > 0
            else 0.0,
            "energy_per_neural_token": round(self.joules / self.neural_tokens, 8)
            if self.joules is not None
            else None,
        }
