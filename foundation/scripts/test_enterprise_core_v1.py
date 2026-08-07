"""Focused tests for the effect-closed enterprise CPU boundary."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.enterprise_core import (  # noqa: E402
    evaluate_compliance,
    evaluate_json_config,
    evaluate_python_source,
    make_audit_event,
    module_status,
    plan_report,
    summarize_observations,
)


GOOD_SOURCE = '''
"""A fully described fixture module."""
import logging

logger = logging.getLogger(__name__)


def answer(value: str) -> str:
    """Return the supplied value."""
    try:
        logger.info("answer")
        return value
    except ValueError as exc:
        logger.error("failed: %s", exc)
        return ""
'''


def main() -> int:
    good = evaluate_python_source(GOOD_SOURCE, path="foundation/lib/example.py")
    bad = evaluate_python_source("def broken(:\n", path="foundation/lib/broken.py")
    assert good["ok"] and good["state"] in {"PASS", "WARN"}, good
    assert bad["ok"] is False and bad["state"] == "FAIL", bad
    assert good["filesystem_scan_performed"] is False, good

    config = evaluate_json_config('{"mode":"cpu","enabled":true}', path="config/example.json", required_keys=("mode",))
    missing = evaluate_json_config('{"enabled":true}', path="config/example.json", required_keys=("mode",))
    assert config["ok"] and config["state"] == "PASS", config
    assert missing["ok"] is False and "mode" in missing["missing_keys"], missing

    observations = summarize_observations(
        [
            {"path": "a.py", "state": "PASS", "score": 100},
            {"path": "b.py", "state": "WARN", "score": 75},
            {"path": "bad.py", "state": "FAIL", "score": 10},
        ]
    )
    assert observations["state"] == "VERIFIED" and observations["state_counts"]["FAIL"] == 1, observations

    partial = evaluate_compliance(
        [
            {"id": "CC1", "state": "PASS", "evidence": "fixture"},
            {"id": "CC2", "state": "UNKNOWN"},
        ],
        standard="soc2",
    )
    compliant = evaluate_compliance([{"id": "CC1", "state": "PASS"}], standard="soc2")
    failed = evaluate_compliance([{"id": "CC1", "state": "FAIL"}], standard="soc2")
    assert partial["disposition"] == "PARTIAL", partial
    assert compliant["disposition"] == "COMPLIANT", compliant
    assert failed["disposition"] == "NON_COMPLIANT", failed

    event = make_audit_event("standards_check", evidence={"source": "fixture"}, occurred_at="2026-08-04T12:00:00Z")
    assert event["event_id"] and event["audit_write_performed"] is False, event
    quality = plan_report("quality", observations=[{"path": "a.py", "state": "PASS", "score": 100}])
    assert quality["ok"] and quality["report_write_performed"] is False, quality
    assert module_status()["llm_authority"] is False

    source = (FOUNDATION / "lib" / "enterprise_core.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    )
    assert not imported.intersection({"subprocess", "socket", "requests", "torch", "threading"}), imported
    forbidden_calls = {"open", "sleep", "system", "run", "Popen", "write_text", "mkdir", "unlink"}
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not calls.intersection(forbidden_calls), calls

    print(
        json.dumps(
            {
                "ok": True,
                "good_source_state": good["state"],
                "bad_source_state": bad["state"],
                "observation_states": observations["state_counts"],
                "compliance_dispositions": [partial["disposition"], compliant["disposition"], failed["disposition"]],
                "audit_write_performed": False,
                "filesystem_scan_performed": False,
                "llm_authority": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
