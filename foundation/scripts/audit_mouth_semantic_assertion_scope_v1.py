#!/usr/bin/env python3
"""Audit the disjoint assertion-scope semantic hold pack."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import SOURCE_SHA256, VERSION, judge  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_assertion_scope_v1"
SOURCE = ROOT / "assertion_scope_hold.jsonl"
OUT = ROOT / "ASSERTION_SCOPE_AUDIT_V1.json"


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    findings: list[str] = []
    seen: set[str] = set()
    cases = []
    for row in rows:
        pair_id = str(row.get("pair_id", "<missing>"))
        if pair_id in seen:
            findings.append(f"duplicate_pair_id:{pair_id}")
        seen.add(pair_id)
        if not all(row.get(key) is not None for key in ("pair_id", "ask", "target", "axis", "expected")):
            findings.append(f"missing_required_fields:{pair_id}")
        if not (row.get("hold_only") is True and row.get("optimizer_eligible") is False
                and row.get("training_authorized") is False and row.get("run_authorized") is False
                and row.get("full_campaign_eligible") is False):
            findings.append(f"authorization:{pair_id}")
        observed = judge(row["target"], axis=row["axis"], ask=row["ask"], use_cpu_sensor=False)["status"]
        case = {"pair_id": pair_id, "axis": row["axis"], "expected": row["expected"], "observed": observed, "match": observed == row["expected"]}
        cases.append(case)
        if not case["match"]:
            findings.append(f"replay_mismatch:{pair_id}:{row['expected']}!={observed}")
    report = {
        "schema_version": "mouth_semantic_assertion_scope_audit_v1",
        "status": "ASSERTION_SCOPE_AUDIT_PASS" if not findings else "ASSERTION_SCOPE_AUDIT_FAIL",
        "evaluator": {"version": VERSION, "source_sha256": SOURCE_SHA256},
        "source": {"path": str(SOURCE).replace("\\", "/"), "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(), "rows": len(rows)},
        "unique_pair_ids": len(seen),
        "cases": cases,
        "training_authorized": False,
        "run_authorized": False,
        "optimizer_eligible": False,
        "promotion_allowed": False,
        "findings": findings,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not findings, "rows": len(rows), "unique_pair_ids": len(seen), "findings": len(findings), "output": str(OUT)}, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
