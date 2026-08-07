"""Focused tests for effect-closed infrastructure planning."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.infra_core import evaluate_metrics, module_status, plan_ci_pipeline, plan_deployment, plan_rollback


def _metrics() -> tuple[dict[str, float], dict[str, float]]:
    return ({"pass_rate": 1.0, "p95_latency_ms": 20, "mean_latency_ms": 10, "boundary_drift": 0.0, "recall_at_5": 1.0, "error_rate": 0.0}, {"pass_rate_min": 0.9, "p95_latency_max_ms": 50, "mean_latency_max_ms": 30, "boundary_drift_max": 0.01, "recall_at_5_min": 0.9, "error_rate_max": 0.05})


def test_slo_and_ci_plans_are_deterministic() -> None:
    metrics, thresholds = _metrics()
    slo = evaluate_metrics(metrics, thresholds)
    ci = plan_ci_pipeline([{"stage": "syntax", "ok": True}, {"stage": "tests", "ok": True}])
    assert slo["state"] == "PASS"
    assert ci["state"] == "PASS"
    assert slo["deployment_changed"] is False
    assert ci["ci_executed"] is False


def test_missing_or_failed_evidence_holds() -> None:
    metrics, thresholds = _metrics()
    failed = evaluate_metrics({**metrics, "pass_rate": 0.2}, thresholds)
    missing = evaluate_metrics(metrics, {"pass_rate_min": 0.9})
    ci = plan_ci_pipeline([{"stage": "tests", "ok": False}])
    assert failed["state"] == "ROLLBACK_RECOMMENDED"
    assert missing["state"] == "INCONCLUSIVE"
    assert ci["state"] == "HOLD"


def test_deployment_and_rollback_never_execute() -> None:
    metrics, thresholds = _metrics()
    slo = evaluate_metrics(metrics, thresholds)
    ci = plan_ci_pipeline([{"stage": "tests", "ok": True}])
    deployment = plan_deployment("local", health_ok=True, slo=slo, ci=ci, architect_approved=False)
    rollback = plan_rollback("local", reason="failed canary", baseline_available=True, architect_approved=True)
    assert deployment["state"] == "HOLD"
    assert deployment["deployment_changed"] is False
    assert rollback["state"] == "PROPOSED"
    assert rollback["rollback_authorized"] is False
    assert rollback["rollback_performed"] is False


def test_no_forbidden_effects_or_model_imports() -> None:
    tree = ast.parse((ROOT / "lib" / "infra_core.py").read_text(encoding="utf-8"))
    forbidden = {"subprocess", "socket", "requests", "torch", "numpy", "pathlib", "urllib"}
    assert all(not isinstance(node, ast.ImportFrom) or node.module not in forbidden for node in ast.walk(tree))
    assert all(not isinstance(node, ast.Import) or all(alias.name not in forbidden for alias in node.names) for node in ast.walk(tree))


def test_module_status() -> None:
    result = module_status()
    assert result["ok"] is True
    assert result["read_only"] is True
    assert result["deployment_authorized"] is False
