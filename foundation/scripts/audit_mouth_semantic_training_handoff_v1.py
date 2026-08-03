#!/usr/bin/env python3
"""Audit the boundary between the semantic bundle and the closed train corpus."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import SOURCE_SHA256, VERSION

CAMPAIGNS = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
SEMANTIC_ROOT = CAMPAIGNS / "mouth_semantic_refinement_v22_42"
TRAIN_ROOT = CAMPAIGNS / "mouth_training_recovery_v1_2_2"
READINESS = SEMANTIC_ROOT / "SEMANTIC_READINESS_V7.json"
SEMANTIC_BUNDLE = SEMANTIC_ROOT / "SEMANTIC_BUNDLE_AUDIT_V28.json"
TRAIN_MANIFEST = TRAIN_ROOT / "manifest.json"
PROJECTION = SEMANTIC_ROOT / "SEMANTIC_SFT_CANDIDATE_PROJECTION_V4.json"
OUT = SEMANTIC_ROOT / "SEMANTIC_TRAINING_HANDOFF_AUDIT_V6.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    for path in (READINESS, SEMANTIC_BUNDLE, TRAIN_MANIFEST, PROJECTION):
        if not path.exists():
            raise FileNotFoundError(str(path))
    readiness = read(READINESS)
    bundle = read(SEMANTIC_BUNDLE)
    train = read(TRAIN_MANIFEST)
    projection = read(PROJECTION)
    findings = []
    if readiness.get("status") != "SEMANTIC_READY_TRAINING_STILL_CLOSED":
        findings.append("semantic_readiness_not_green")
    if bundle.get("bundle_rows") != 549 or bundle.get("unique_normalized_targets") != 549:
        findings.append("semantic_bundle_cardinality")
    if train.get("status") != "CORPUS_READY_TRAINING_CLOSED":
        findings.append("train_corpus_not_closed")
    if train.get("training_authorized") is not False or train.get("run_authorized") is not False:
        findings.append("train_corpus_authority_open")
    if projection.get("status") != "SFT_CANDIDATE_PROJECTION_HOLD_ONLY" or projection.get("selected_rows") != 256:
        findings.append("candidate_projection_not_green")
    metadata = projection.get("selected_row_metadata", [])
    if len(metadata) != 256 or len({row.get("pair_id") for row in metadata}) != 256:
        findings.append("candidate_projection_metadata_integrity")
    if Counter(row.get("source_role") for row in metadata) != Counter({"legacy_rehearsal": 96, "natural_expansion": 40, "natural_completion": 120}):
        findings.append("candidate_projection_composition")
    if projection.get("optimizer_eligible") is not False or projection.get("training_authorized") is not False:
        findings.append("candidate_projection_authority_open")
    semantic_train_alignment = train.get("evaluator_version") == VERSION
    if semantic_train_alignment:
        findings.append("unexpected_old_train_alignment_claim")
    report = {
        "schema_version": "mouth_semantic_training_handoff_audit_v1",
        "status": "HANDOFF_REQUIRES_NEW_CAMPAIGN" if not findings else "HANDOFF_AUDIT_FAIL",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "current_semantic_evaluator": {"version": VERSION, "source_sha256": SOURCE_SHA256},
        "semantic_bundle": {"path": str(SEMANTIC_BUNDLE).replace("\\", "/"), "sha256": sha256(SEMANTIC_BUNDLE), "rows": bundle.get("bundle_rows")},
        "semantic_readiness": {"path": str(READINESS).replace("\\", "/"), "sha256": sha256(READINESS), "status": readiness.get("status")},
        "candidate_projection": {"path": str(PROJECTION).replace("\\", "/"), "sha256": sha256(PROJECTION), "status": projection.get("status"), "selected_rows": projection.get("selected_rows")},
        "closed_train_corpus": {
            "path": str(TRAIN_MANIFEST).replace("\\", "/"),
            "sha256": sha256(TRAIN_MANIFEST),
            "status": train.get("status"),
            "evaluator_version": train.get("evaluator_version"),
            "train_rows": train.get("counts", {}).get("train"),
            "training_authorized": train.get("training_authorized"),
            "run_authorized": train.get("run_authorized"),
        },
        "semantic_train_alignment": semantic_train_alignment,
        "optimizer_rows_admitted_from_semantic_bundle": 0,
        "candidate_rows_prepared_but_not_admitted": projection.get("selected_rows"),
        "candidate_composition": dict(sorted(Counter(row.get("source_role") for row in metadata).items())),
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
        "findings": findings,
        "next_action": "construct_new_manifest_locked_campaign_after_separate_authorization" if not findings else "repair_handoff_audit",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not findings, "status": report["status"], "current_evaluator": VERSION, "closed_train_evaluator": train.get("evaluator_version"), "optimizer_rows_admitted": 0, "output": str(OUT)}, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
