"""Focused tests for the read-only CPU infrastructure operations judge."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_infra_ops_judge import build_probe, evaluate_slos  # noqa: E402


def main() -> None:
    passed = evaluate_slos(
        {"pass_rate": 0.99, "p95_latency_ms": 100, "mean_latency_ms": 80, "boundary_drift": 0.01, "recall_at_5": 0.9, "error_rate": 0.001},
        {"pass_rate_min": 0.95, "p95_latency_max_ms": 200, "mean_latency_max_ms": 150, "boundary_drift_max": 0.08, "recall_at_5_min": 0.85, "error_rate_max": 0.01},
    )
    assert passed["state"] == "PASS"
    failed = evaluate_slos({"pass_rate": 0.5}, {"pass_rate_min": 0.95})
    assert failed["state"] == "ROLLBACK_RECOMMENDED"
    assert evaluate_slos({}, {})["state"] == "INCONCLUSIVE"
    probe = build_probe({})
    assert probe["ok"] and probe["writes"] is False and probe["deployment_changed"] is False and probe["rollback_performed"] is False
    print({"ok": True, "slo_pass": True, "rollback_recommendation": True, "missing_inconclusive": True, "effects": False})


if __name__ == "__main__":
    main()
