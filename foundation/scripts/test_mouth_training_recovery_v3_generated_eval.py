from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import mouth_training_recovery_v3_generated_eval as subject  # noqa: E402


def complete_report(role: str = "checkpoint", step: int | None = 32) -> dict:
    return {
        "role": role,
        "checkpoint_step": step,
        "metrics": {
            "mind_pass_rate": 0.68,
            "valid_speech_rate": 0.95,
            "eos_termination_rate": 0.75,
            "legacy_goal_coverage_rate": 1.0,
            "collapse_count": 0,
            "numeric_prefix_count": 0,
            "security_violation_count": 0,
            "evaluator_error_count": 0,
        },
    }


class GeneratedEvalTests(unittest.TestCase):
    def test_missing_metric_is_inconclusive(self) -> None:
        report = complete_report()
        del report["metrics"]["eos_termination_rate"]
        self.assertEqual(subject._gate_report(report)["status"], "INCONCLUSIVE")

    def test_complete_metrics_pass(self) -> None:
        self.assertEqual(subject._gate_report(complete_report())["status"], "PASS")

    def test_complete_metric_failure_is_fail(self) -> None:
        report = complete_report()
        report["metrics"]["mind_pass_rate"] = 0.67
        self.assertEqual(subject._gate_report(report)["status"], "FAIL")

    def test_pack_loader_preserves_cases_and_excludes_targets(self) -> None:
        root = Path(__file__).resolve().parents[1] / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v3_campaign_v1"
        rows = subject._load_pack(root, "development")
        self.assertEqual(len(rows), 64)
        self.assertIn("ask", rows[0])
        self.assertNotIn("target", rows[0])


if __name__ == "__main__":
    unittest.main()
