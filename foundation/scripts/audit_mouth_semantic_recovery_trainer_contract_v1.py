#!/usr/bin/env python3
"""Read-only schema audit between the semantic campaign input and trainer.

This intentionally does not call CUDA, load a model, mutate rows, or authorize
training.  It proves only that a future admission step has the fields needed
to construct optimizer rows for the existing trainer contract.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v3_semantic_projection_v1"
TRAIN_CANDIDATE = ROOT / "train_candidate_256_hold.jsonl"
MANIFEST = ROOT / "manifest.json"
OUT = ROOT / "TRAINER_CONTRACT_AUDIT.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in TRAIN_CANDIDATE.read_text(encoding="utf-8").splitlines() if line.strip()]
    findings: list[str] = []
    if len(rows) != 256:
        findings.append(f"row_count:{len(rows)}")
    required = {"ask", "chosen", "target", "axis", "pair_id", "hold_only", "optimizer_eligible"}
    for row in rows:
        missing = sorted(required - row.keys())
        if missing:
            findings.append(f"missing_fields:{row.get('pair_id')}:{','.join(missing)}")
        if not row.get("ask") or not (row.get("chosen") or row.get("target")):
            findings.append(f"empty_training_text:{row.get('pair_id')}")
        if row.get("hold_only") is not True or row.get("optimizer_eligible") is not False:
            findings.append(f"authority_not_closed:{row.get('pair_id')}")
    if len({row.get("pair_id") for row in rows}) != len(rows):
        findings.append("duplicate_pair_ids")
    if manifest.get("training_authorized") is not False or manifest.get("run_authorized") is not False:
        findings.append("manifest_authority_open")
    report = {
        "schema_version": "mouth_semantic_recovery_trainer_contract_audit_v1",
        "status": "TRAINER_SCHEMA_COMPATIBLE_PENDING_ADMISSION" if not findings else "TRAINER_SCHEMA_AUDIT_FAIL",
        "candidate": {"path": str(TRAIN_CANDIDATE).replace("\\", "/"), "sha256": sha256(TRAIN_CANDIDATE), "rows": len(rows)},
        "required_future_admission_fields": ["split=train", "optimizer_eligible=true", "response_only_loss_allowed=true"],
        "present_text_fields": {"ask": True, "chosen": all(bool(row.get("chosen")) for row in rows), "target": all(bool(row.get("target")) for row in rows)},
        "axis_counts": dict(sorted(Counter(row.get("axis") for row in rows).items())),
        "training_authorized": False,
        "run_authorized": False,
        "optimizer_eligible": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "findings": findings,
        "next_action": "separate_admission_review" if not findings else "repair_schema_findings",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not findings, "status": report["status"], "rows": len(rows), "training_authorized": False, "output": str(OUT)}))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
