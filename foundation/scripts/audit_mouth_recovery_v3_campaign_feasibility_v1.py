#!/usr/bin/env python3
"""Audit whether existing artifacts can form the governed v3 eval splits.

This is intentionally a feasibility audit only.  It never copies evaluation
rows, admits training data, opens a lease, or changes authorization.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import judge

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
INPUT_ROOT = TREE / "mouth_training_recovery_v3_semantic_projection_v1"
EVAL_ROOT = TREE / "mouth_training_recovery_v3_eval_rebuild_v1"
OUT = INPUT_ROOT / "CAMPAIGN_FEASIBILITY_AUDIT_V4.json"
SOURCES = {
    "train_candidate": INPUT_ROOT / "train_candidate_256_hold.jsonl",
    "development_candidate": EVAL_ROOT / "development.jsonl",
    "blind_candidate": EVAL_ROOT / "blind.jsonl",
    "legacy_candidate": EVAL_ROOT / "legacy.jsonl",
    "auditor_negative_candidate": EVAL_ROOT / "auditor_negative.jsonl",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def keys(rows: list[dict], field: str) -> set[str]:
    if field == "pair_id":
        return {str(row.get("pair_id")) for row in rows}
    return {norm(row.get(field) or row.get("chosen")) for row in rows}


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    raw = {name: load(path) for name, path in SOURCES.items()}
    legacy_inventory = []
    for path in TREE.rglob("*.jsonl"):
        try:
            candidate_rows = [row for row in load(path) if str(row.get("axis", "")).startswith("legacy.")]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if candidate_rows:
            statuses = Counter(judge(row.get("target") or row.get("chosen"), axis=row["axis"], ask=row.get("ask", ""), use_cpu_sensor=False)["status"] for row in candidate_rows)
            legacy_inventory.append({"path": str(path).replace("\\", "/"), "sha256": sha256(path), "rows": len(candidate_rows), "current_evaluator_status": dict(sorted(statuses.items()))})
    train = raw["train_candidate"]
    source_reports = {}
    for name, rows in raw.items():
        observed = Counter()
        if name != "train_candidate":
            for row in rows:
                observed[judge(row.get("target") or row.get("chosen"), axis=row["axis"], ask=row.get("ask", ""), use_cpu_sensor=False)["status"]] += 1
        source_reports[name] = {
            "path": str(SOURCES[name]).replace("\\", "/"),
            "sha256": sha256(SOURCES[name]),
            "rows": len(rows),
            "axis_counts": dict(sorted(Counter(row.get("axis") for row in rows).items())),
            "current_evaluator_status": dict(sorted(observed.items())),
        }
    findings = []
    required = {"development_candidate": 64, "blind_candidate": 32, "legacy_candidate": 64, "auditor_negative_candidate": 20}
    for name, count in required.items():
        if len(raw[name]) != count:
            findings.append(f"row_count:{name}:{len(raw[name])}:expected={count}")
    for name in required:
        if keys(raw[name], "pair_id") & keys(train, "pair_id"):
            findings.append(f"pair_id_overlap:{name}:train")
        if keys(raw[name], "ask") & keys(train, "ask"):
            findings.append(f"ask_overlap:{name}:train")
        if keys(raw[name], "target") & keys(train, "target"):
            findings.append(f"target_overlap:{name}:train")
    eval_names = list(required)
    for index, left in enumerate(eval_names):
        for right in eval_names[index + 1 :]:
            for field in ("pair_id", "ask", "target"):
                overlap = keys(raw[left], field) & keys(raw[right], field)
                if overlap:
                    findings.append(f"{field}_overlap:{left}:{right}:{len(overlap)}")
    if source_reports["development_candidate"]["current_evaluator_status"].get("PASS", 0) != 64:
        findings.append("development_not_current_evaluator_pass")
    if source_reports["blind_candidate"]["current_evaluator_status"].get("PASS", 0) != 32:
        findings.append("blind_not_current_evaluator_pass")
    if source_reports["legacy_candidate"]["current_evaluator_status"].get("PASS", 0) != 64:
        findings.append("legacy_not_current_evaluator_pass")
    if source_reports["auditor_negative_candidate"]["current_evaluator_status"].get("FAIL", 0) != 20:
        findings.append("negative_pack_not_current_evaluator_fail")
    report = {
        "schema_version": "mouth_recovery_v3_campaign_feasibility_audit_v1",
        "status": "CAMPAIGN_FEASIBILITY_BLOCKED_EXISTING_EVAL_STALE" if findings else "CAMPAIGN_FEASIBLE_NO_EXECUTION",
        "evaluator": {"version": "evaluator_v2_3_hybrid_v1_2_5"},
        "sources": source_reports,
        "legacy_inventory": sorted(legacy_inventory, key=lambda item: item["path"]),
        "current_valid_semantic_pass_pool": "available_in_nonlegacy_hold_packs_but_not_a_legacy_source",
        "findings": findings,
        "copied_rows": False,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "next_action": "recalibrate_or_supply_current_evaluator_legacy_dev_blind_sets" if findings else "separate_campaign_construction_review",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not findings, "status": report["status"], "findings": findings, "output": str(OUT)}))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
