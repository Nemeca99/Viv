#!/usr/bin/env python3
"""Fail-closed readiness gate for the current semantic evaluator and bundle.

This verifier consolidates the immutable receipts produced by the semantic
passes.  It does not admit data, authorize training, open a lease, or run a
model.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import SOURCE_SHA256, VERSION

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v22_42"
BUNDLE = ROOT / "SEMANTIC_BUNDLE_AUDIT_V28.json"
QUALITY = ROOT / "SEMANTIC_BUNDLE_QUALITY_AUDIT_V27.json"
COVERAGE = ROOT / "SEMANTIC_COVERAGE_AUDIT_V6.json"
REGRESSION = ROOT / "SEMANTIC_REGRESSION_RUN_V15.json"
OUT = ROOT / "SEMANTIC_READINESS_V7.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    paths = {"bundle": BUNDLE, "quality": QUALITY, "coverage": COVERAGE, "regression": REGRESSION}
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing_receipts:{','.join(missing)}")
    reports = {name: read(path) for name, path in paths.items()}
    findings: list[str] = []

    for name in ("bundle", "quality", "coverage"):
        report = reports[name]
        evaluator = report.get("evaluator", {})
        if evaluator.get("version") != VERSION:
            findings.append(f"evaluator_version:{name}:{evaluator.get('version')}")
        if evaluator.get("source_sha256") != SOURCE_SHA256:
            findings.append(f"evaluator_source_sha256:{name}")

    bundle = reports["bundle"]
    if bundle.get("status") != "SEMANTIC_BUNDLE_AUDIT_PASS":
        findings.append(f"bundle_status:{bundle.get('status')}")
    if bundle.get("bundle_rows") != 549 or bundle.get("unique_normalized_targets") != 549:
        findings.append("bundle_cardinality")
    if bundle.get("duplicate_target_groups") or bundle.get("label_contradictions") or bundle.get("replay_mismatches"):
        findings.append("bundle_integrity_findings")

    quality = reports["quality"]
    if quality.get("status") != "SEMANTIC_BUNDLE_QUALITY_PASS":
        findings.append(f"quality_status:{quality.get('status')}")
    if quality.get("findings"):
        findings.append("quality_findings")
    if quality.get("meta_tail_count") != 0 or quality.get("target_equals_ask_count") != 0:
        findings.append("quality_leakage")
    if quality.get("near_copy_review_required_count") != 0:
        findings.append("near_copy_review_required")

    coverage = reports["coverage"]
    if not coverage.get("replay_pass") or coverage.get("findings"):
        findings.append("coverage_replay")
    if coverage.get("training_authorized") is not False or coverage.get("run_authorized") is not False:
        findings.append("coverage_authority")

    regression = reports["regression"]
    if regression.get("status") != "SEMANTIC_REGRESSION_PASS" or regression.get("completed_count") != 22:
        findings.append("regression_status")
    if regression.get("training_authorized") is not False or regression.get("run_authorized") is not False:
        findings.append("regression_authority")

    report = {
        "schema_version": "mouth_semantic_readiness_v1",
        "status": "SEMANTIC_READY_TRAINING_STILL_CLOSED" if not findings else "SEMANTIC_NOT_READY",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evaluator": {"version": VERSION, "source_sha256": SOURCE_SHA256},
        "receipts": {name: {"path": str(path).replace("\\", "/"), "sha256": sha256(path)} for name, path in paths.items()},
        "bundle_rows": bundle.get("bundle_rows"),
        "unique_targets": bundle.get("unique_normalized_targets"),
        "regression_tests": regression.get("completed_count"),
        "training_authorized": False,
        "run_authorized": False,
        "optimizer_eligible": False,
        "promotion_allowed": False,
        "findings": findings,
        "next_action": "separate_governed_training_authorization" if not findings else "repair_failed_readiness_invariant",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not findings, "status": report["status"], "bundle_rows": report["bundle_rows"], "regression_tests": report["regression_tests"], "output": str(OUT)}, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
