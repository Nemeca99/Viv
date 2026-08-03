#!/usr/bin/env python3
"""Run the canonical mouth semantic regression surface sequentially.

This is read-only with respect to source and training state.  It writes one
immutable receipt so future audits can distinguish a complete replay from a
partial collection of individually green commands.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
ROOT = TREE / "mouth_semantic_refinement_v22_42"
OUT = ROOT / "SEMANTIC_REGRESSION_RUN_V15.json"

TESTS = [
    "test_mouth_acronym_grammar_v1.py",
    "test_mouth_evidence_uncertainty_grammar_v1.py",
    "test_mouth_memory_service_grammar_v1.py",
    "test_mouth_entity_we_grammar_v1.py",
    "test_mouth_tool_agency_grammar_v1.py",
    "test_mouth_semantic_assertion_scope_v1.py",
    "test_mouth_semantic_coverage_pack_v2.py",
    "test_mouth_semantic_residual_pack_v1.py",
    "test_mouth_semantic_relational_invariance_v1.py",
    "test_mouth_semantic_bundle_quality_audit_v20.py",
    "test_mouth_semantic_bundle_quality_audit_v21.py",
    "test_mouth_semantic_fail_closed_inputs_v1.py",
    "test_mouth_semantic_natural_expansion_v1.py",
    "test_mouth_semantic_natural_completion_v1.py",
    "test_mouth_semantic_invariance_v1.py",
    "test_mouth_semantic_composition_v1.py",
    "test_mouth_semantic_reaudit_v1.py",
    "test_mouth_semantic_bundle_audit_v8.py",
    "test_mouth_judge_provenance_v1.py",
    "test_mouth_identity_claim_patterns_v2.py",
    "test_mouth_acronym_contract_matrix_v1.py",
    "test_cpu_semantic_judge.py",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    cases: list[dict] = []
    overall_ok = True
    for name in TESTS:
        path = FOUNDATION / "scripts" / name
        started = datetime.now(timezone.utc)
        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(FOUNDATION),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        finished = datetime.now(timezone.utc)
        ok = result.returncode == 0
        overall_ok = overall_ok and ok
        cases.append({
            "script": name,
            "script_sha256": sha(path),
            "started_utc": started.isoformat(),
            "finished_utc": finished.isoformat(),
            "returncode": result.returncode,
            "ok": ok,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        })
        if not ok:
            break
    report = {
        "schema_version": "mouth_semantic_regression_run_v13",
        "status": "SEMANTIC_REGRESSION_PASS" if overall_ok and len(cases) == len(TESTS) else "SEMANTIC_REGRESSION_FAIL",
        "test_count": len(TESTS),
        "completed_count": len(cases),
        "cases": cases,
        "training_authorized": False,
        "run_authorized": False,
        "optimizer_eligible": False,
        "promotion_allowed": False,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": report["status"] == "SEMANTIC_REGRESSION_PASS", "completed": len(cases), "tests": len(TESTS), "output": str(OUT)}, sort_keys=True))
    return 0 if report["status"] == "SEMANTIC_REGRESSION_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
