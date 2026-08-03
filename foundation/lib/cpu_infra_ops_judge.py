"""Deterministic CPU operations judge for infra health and rollback planning.

It evaluates evidence and produces a recommendation only. It never deploys,
rolls back, starts services, invokes stress tests, or changes authority.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from lib.foundation_health import evaluate_foundation_gate
from lib.paths import VIV_ROOT

BASELINE_SOURCE = "F:/AIOS_Clean/infra_core/ops/baseline.yaml"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def evaluate_slos(metrics: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    """Compare measured metrics to explicit thresholds; missing data fails closed."""
    checks: dict[str, bool] = {}
    missing: list[str] = []
    comparisons = (
        ("pass_rate", "pass_rate_min", lambda actual, limit: actual >= limit),
        ("p95_latency_ms", "p95_latency_max_ms", lambda actual, limit: actual <= limit),
        ("mean_latency_ms", "mean_latency_max_ms", lambda actual, limit: actual <= limit),
        ("boundary_drift", "boundary_drift_max", lambda actual, limit: abs(actual) <= limit),
        ("recall_at_5", "recall_at_5_min", lambda actual, limit: actual >= limit),
        ("error_rate", "error_rate_max", lambda actual, limit: actual <= limit),
    )
    for metric_key, threshold_key, predicate in comparisons:
        actual = _number(metrics.get(metric_key))
        limit = _number(thresholds.get(threshold_key))
        if actual is None or limit is None:
            missing.append(metric_key)
            continue
        checks[metric_key] = bool(predicate(actual, limit))
    failed = sorted(key for key, passed in checks.items() if not passed)
    state = "PASS" if not missing and not failed else "ROLLBACK_RECOMMENDED" if failed else "INCONCLUSIVE"
    return {"state": state, "checks": checks, "failed": failed, "missing": sorted(missing), "deployment_changed": False, "rollback_performed": False}


def build_probe(payload: dict[str, Any]) -> dict[str, Any]:
    """Return health and optional canary evidence with no effect authority."""
    gate = evaluate_foundation_gate(include_stress=False)
    result: dict[str, Any] = {
        "ok": True,
        "state": "VERIFIED_READ_ONLY",
        "health_gate": gate,
        "baseline_source": BASELINE_SOURCE,
        "viv_root": str(VIV_ROOT).replace("\\", "/"),
        "deployment_changed": False,
        "rollback_performed": False,
        "writes": False,
        "llm": False,
    }
    metrics = payload.get("metrics")
    thresholds = payload.get("thresholds")
    if metrics is not None or thresholds is not None:
        if not isinstance(metrics, dict) or not isinstance(thresholds, dict):
            return {**result, "ok": False, "state": "INCONCLUSIVE", "reason": "metrics_and_thresholds_must_be_objects"}
        result["slo_verdict"] = evaluate_slos(metrics, thresholds)
    return result
