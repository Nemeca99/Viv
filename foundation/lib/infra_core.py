"""Effect-closed CPU planning for infrastructure, CI, and rollback."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

MODULE_ID = "infra_core"
VERSION = "v1"
MANUAL_SECTION = "3.18"
MANUAL_SOURCE = "F:/AIOS_Clean/infra_core"


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def evaluate_metrics(metrics: Mapping[str, Any], thresholds: Mapping[str, Any]) -> dict[str, Any]:
    """Compare supplied metrics to supplied SLO thresholds only."""
    if not isinstance(metrics, Mapping) or not isinstance(thresholds, Mapping):
        return {"ok": False, "state": "INCONCLUSIVE", "reason": "metrics_and_thresholds_must_be_mappings", "deployment_changed": False, "rollback_performed": False}
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
        else:
            checks[metric_key] = bool(predicate(actual, limit))
    failed = sorted(key for key, passed in checks.items() if not passed)
    state = "PASS" if not missing and not failed else "ROLLBACK_RECOMMENDED" if failed else "INCONCLUSIVE"
    return {"ok": state == "PASS", "state": state, "checks": checks, "failed": failed, "missing": sorted(missing), "deployment_changed": False, "rollback_performed": False, "llm_authority": False}


def plan_ci_pipeline(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate supplied CI stage results without running CI."""
    rows = list(results)[:64]
    failed = [str(row.get("stage") or "unknown") for row in rows if not bool(row.get("ok"))]
    missing = [str(index) for index, row in enumerate(rows) if not str(row.get("stage") or "").strip()]
    state = "PASS" if rows and not failed and not missing else "HOLD" if failed else "INCONCLUSIVE"
    return {"ok": state == "PASS", "state": state, "stages": len(rows), "failed_stages": sorted(failed), "malformed_rows": missing, "ci_executed": False, "deployment_changed": False, "writes_performed": False, "llm_authority": False}


def plan_deployment(target: str, *, health_ok: bool, slo: Mapping[str, Any] | None = None, ci: Mapping[str, Any] | None = None, architect_approved: bool = False) -> dict[str, Any]:
    """Prepare a deployment recommendation while keeping deployment closed."""
    checks = {"health_ok": bool(health_ok), "slo_pass": bool(slo and slo.get("state") == "PASS"), "ci_pass": bool(ci and ci.get("state") == "PASS"), "architect_approved": bool(architect_approved)}
    ready = all(checks.values())
    return {"ok": ready, "state": "PROPOSED" if ready else "HOLD", "target": str(target), "checks": checks, "deployment_authorized": False, "deployment_changed": False, "rollback_performed": False, "writes_performed": False, "llm_authority": False}


def plan_rollback(target: str, *, reason: str, baseline_available: bool, architect_approved: bool = False) -> dict[str, Any]:
    """Prepare a rollback handoff without invoking a rollback."""
    ready = bool(reason.strip()) and bool(baseline_available) and bool(architect_approved)
    return {"ok": ready, "state": "PROPOSED" if ready else "HOLD", "target": str(target), "reason": str(reason), "baseline_available": bool(baseline_available), "architect_approved": bool(architect_approved), "rollback_authorized": False, "rollback_performed": False, "writes_performed": False, "llm_authority": False}


def module_status() -> dict[str, Any]:
    return {"ok": True, "state": "READY", "module": MODULE_ID, "version": VERSION, "manual_section": MANUAL_SECTION, "read_only": True, "deployment_authorized": False, "rollback_authorized": False, "llm_authority": False}
