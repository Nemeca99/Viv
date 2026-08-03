"""Deterministic reversible shadow for a normalized RID triad.

This is an integrity/heartbeat primitive, not a stability predictor.  It does
not read or mutate Master S_n, RID telemetry, leases, or model state.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

State = tuple[float, float, float]
EPSILON = 1e-12


@dataclass(frozen=True)
class ShadowResult:
    ok: bool
    status: str
    original: State | None
    transformed: State | None
    reconstructed: State | None
    magnitude: float | None
    phase: str | None
    expected_phase: str | None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "original": self.original,
            "transformed": self.transformed,
            "reconstructed": self.reconstructed,
            "magnitude": self.magnitude,
            "phase": self.phase,
            "expected_phase": self.expected_phase,
            "reason": self.reason,
        }


def _state(values: Any) -> State:
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError("triad_must_have_three_values")
    result = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in result):
        raise ValueError("triad_must_be_finite")
    if any(value <= 0.0 for value in result):
        raise ValueError("triad_axes_must_be_positive")
    return result  # type: ignore[return-value]


def normalize(values: Any) -> tuple[State, float]:
    raw = _state(values)
    magnitude = sum(raw)
    if magnitude <= EPSILON or not math.isfinite(magnitude):
        raise ValueError("triad_magnitude_invalid")
    return tuple(value / magnitude for value in raw), magnitude  # type: ignore[return-value]


def transform(normalized: Any) -> State:
    x, y, z = _state(normalized)
    total = (y * z) + (x * z) + (x * y)
    if total <= EPSILON or not math.isfinite(total):
        raise ValueError("pairwise_product_normalization_invalid")
    return (y * z / total, x * z / total, x * y / total)


def _close(left: State, right: State, tolerance: float) -> bool:
    return all(math.isclose(a, b, rel_tol=tolerance, abs_tol=tolerance) for a, b in zip(left, right))


def expected_phase(tick: int) -> str:
    if not isinstance(tick, int) or tick < 0:
        raise ValueError("tick_must_be_nonnegative_integer")
    return "A" if tick % 2 == 0 else "B"


def verify(
    values: Any,
    *,
    tick: int | None = None,
    phase: str | None = None,
    tolerance: float = 1e-10,
) -> ShadowResult:
    """Verify involution and optional two-phase heartbeat without side effects."""
    try:
        original, magnitude = normalize(values)
        transformed = transform(original)
        reconstructed = transform(transformed)
    except (TypeError, ValueError, OverflowError) as exc:
        return ShadowResult(False, "DENIED", None, None, None, None, phase, None, str(exc))
    if tolerance < 0 or not math.isfinite(tolerance):
        return ShadowResult(False, "DENIED", original, transformed, reconstructed, magnitude, phase, None, "tolerance_invalid")
    expected = expected_phase(tick) if tick is not None else None
    if phase is not None and phase not in {"A", "B"}:
        return ShadowResult(False, "DENIED", original, transformed, reconstructed, magnitude, phase, expected, "phase_invalid")
    if expected is not None and phase != expected:
        return ShadowResult(False, "DENIED", original, transformed, reconstructed, magnitude, phase, expected, "unexpected_phase")
    if not _close(original, reconstructed, tolerance):
        return ShadowResult(False, "DENIED", original, transformed, reconstructed, magnitude, phase, expected, "involution_mismatch")
    return ShadowResult(True, "VERIFIED", original, transformed, reconstructed, magnitude, phase, expected)


def probe(payload: dict[str, Any]) -> dict[str, Any]:
    """Task-facing read-only probe; payload contains only a fixture triad."""
    result = verify(payload.get("triad"), tick=payload.get("tick"), phase=payload.get("phase"))
    out = result.to_dict()
    out.update({"kind": "rid_recursive_shadow", "writes": False, "llm": False, "master_rid_mutated": False})
    return out
