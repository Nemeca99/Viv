"""Read-only adapter for infrastructure and CI planning."""
from __future__ import annotations

from typing import Any

from lib.infra_core import evaluate_metrics, module_status, plan_ci_pipeline, plan_deployment, plan_rollback


def status() -> dict[str, Any]:
    return module_status()


def cpu_plan(
    *,
    metrics: dict[str, Any] | None = None,
    thresholds: dict[str, Any] | None = None,
    ci_results: list[dict[str, Any]] | None = None,
    target: str = "local",
    architect_approved: bool = False,
    rollback_reason: str | None = None,
    baseline_available: bool = False,
) -> dict[str, Any]:
    slo = evaluate_metrics(metrics, thresholds) if metrics is not None or thresholds is not None else {"state": "INCONCLUSIVE", "ok": False}
    ci = plan_ci_pipeline(ci_results or [])
    result: dict[str, Any] = {
        "ok": True,
        "state": "VERIFIED",
        "slo": slo,
        "ci": ci,
        "deployment": plan_deployment(target, health_ok=True, slo=slo, ci=ci, architect_approved=architect_approved),
        "deployment_changed": False,
        "rollback_performed": False,
        "writes_performed": False,
        "llm_authority": False,
    }
    if rollback_reason is not None:
        result["rollback"] = plan_rollback(target, reason=rollback_reason, baseline_available=baseline_available, architect_approved=architect_approved)
    return result


def run_smoke() -> dict[str, Any]:
    result = cpu_plan(
        metrics={"pass_rate": 1.0, "p95_latency_ms": 20, "mean_latency_ms": 10, "boundary_drift": 0.0, "recall_at_5": 1.0, "error_rate": 0.0},
        thresholds={"pass_rate_min": 0.9, "p95_latency_max_ms": 50, "mean_latency_max_ms": 30, "boundary_drift_max": 0.01, "recall_at_5_min": 0.9, "error_rate_max": 0.05},
        ci_results=[{"stage": "syntax", "ok": True}, {"stage": "tests", "ok": True}],
        target="local",
        architect_approved=False,
        rollback_reason="canary failure",
        baseline_available=True,
    )
    return {"ok": bool(result["slo"]["state"] == "PASS" and result["ci"]["state"] == "PASS" and result["deployment"]["deployment_changed"] is False), "state": "PASS" if result["slo"]["state"] == "PASS" else "INCONCLUSIVE", "plan": result, "authority": "cpu_adapter_observation", "adapter_output_is_authority": False}
