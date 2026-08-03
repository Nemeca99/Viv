#!/usr/bin/env python3
"""Verify semantic receipts use the canonical wrapper provenance."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
LIB = FOUNDATION / "lib"
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v22_42"
OUT = ROOT / "SEMANTIC_PROVENANCE_AUDIT_V1.json"
WRAPPER = LIB / "evaluator_v2_3_hybrid_v1_2_5.py"
BASE = LIB / "evaluator_v2_3_hybrid.py"
VERSION = "evaluator_v2_3_hybrid_v1_2_5"
RECEIPTS = [
    ROOT / "SEMANTIC_BUNDLE_AUDIT_V28.json",
    ROOT / "SEMANTIC_BUNDLE_QUALITY_AUDIT_V27.json",
    ROOT / "SEMANTIC_READINESS_V7.json",
    ROOT / "SEMANTIC_SFT_CANDIDATE_PROJECTION_V4.json",
    ROOT / "SEMANTIC_TRAINING_HANDOFF_AUDIT_V6.json",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    wrapper_sha = sha256(WRAPPER)
    base_sha = sha256(BASE)
    findings = []
    receipts = []
    for path in RECEIPTS:
        report = json.loads(path.read_text(encoding="utf-8"))
        evaluator = report.get("evaluator", report.get("current_semantic_evaluator", {}))
        version = evaluator.get("version")
        source_sha = evaluator.get("source_sha256")
        if version != VERSION or source_sha != wrapper_sha:
            findings.append(f"receipt_provenance:{path.name}")
        receipts.append({"name": path.name, "version": version, "source_sha256": source_sha, "receipt_sha256": sha256(path)})
    report = {
        "schema_version": "mouth_semantic_provenance_audit_v1",
        "status": "SEMANTIC_PROVENANCE_PASS" if not findings else "SEMANTIC_PROVENANCE_FAIL",
        "canonical_wrapper": {"path": str(WRAPPER).replace("\\", "/"), "sha256": wrapper_sha, "version": VERSION},
        "delegated_base": {"path": str(BASE).replace("\\", "/"), "sha256": base_sha},
        "receipts": receipts,
        "findings": findings,
        "training_authorized": False,
        "run_authorized": False,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not findings, "status": report["status"], "wrapper_sha256": wrapper_sha, "base_sha256": base_sha, "receipts": len(receipts), "output": str(OUT)}))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
