#!/usr/bin/env python3
"""Audit the frozen 256-row recovery corpus for proven anchor coverage."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v1_2_4"
OUT = ROOT / "ANCHOR_COVERAGE_ADMISSION_AUDIT.json"
FILES = ("train_256.jsonl", "development_64.jsonl", "blind_32.jsonl")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_file(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    axis_counts: dict[str, int] = {}
    missing: list[str] = []
    for row in rows:
        axis = str(row.get("axis"))
        axis_counts[axis] = axis_counts.get(axis, 0) + 1
        target = str(row.get("target") or row.get("chosen") or "").lower()
        if axis in {"architecture_cpu_gpu_role", "identity_humanization", "memory_ownership_and_service_attribution"}:
            if "viv" not in target or "aios" not in target:
                missing.append(str(row.get("pair_id")))
        if axis == "architecture_cpu_gpu_role" and not ("cpu" in target and "gpu" in target):
            missing.append(str(row.get("pair_id")))
        if axis == "memory_ownership_and_service_attribution" and not any(word in target for word in ("memory", "logs", "logging", "service")):
            missing.append(str(row.get("pair_id")))
    return {
        "path": str(path),
        "sha256": sha256(path),
        "rows": len(rows),
        "axis_counts": axis_counts,
        "missing_anchor_rows": len(set(missing)),
        "missing_anchor_examples": sorted(set(missing))[:12],
        "pass": not missing,
    }


def main() -> int:
    files = {name: audit_file(ROOT / name) for name in FILES}
    report = {
        "schema_version": "mouth_recovery_anchor_coverage_admission_audit_v1",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_campaign": "mouth_training_recovery_v1_2_4",
        "status": "ADMISSION_HOLD_ANCHOR_COVERAGE_INCOMPLETE",
        "admission_recommended": False,
        "training_authorized": False,
        "run_authorized": False,
        "files": files,
        "finding": "The frozen recovery corpus predates the anchor-coverage repair; it must be revised before admission or training.",
        "preservation": "Source bytes were read only and remain unchanged.",
        "next_action": "Construct a new disjoint 256-row corpus using the proven anchor contract, then rerun overlap, evaluator, and admission audits.",
    }
    if OUT.exists():
        raise FileExistsError(f"refuse_overwrite:{OUT}")
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
