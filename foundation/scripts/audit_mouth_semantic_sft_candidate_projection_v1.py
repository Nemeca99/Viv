#!/usr/bin/env python3
"""Audit a conservative, hold-only projection of semantic SFT candidates.

Only the natural-paraphrase positive pack is projected.  Judge-only matrices,
minimal pairs, coverage cases, FAILs, and HOLDs remain excluded even when a
row's expected verdict is PASS.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import PASS, SOURCE_SHA256, VERSION, judge

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_refinement_v22_42"
SOURCE = ROOT / "semantic_refinement_96_hold.jsonl"
OUT = ROOT / "SEMANTIC_SFT_CANDIDATE_PROJECTION_V1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    findings: list[str] = []
    if len(rows) != 96:
        findings.append(f"source_row_count:{len(rows)}")
    asks = [norm(row.get("ask", "")) for row in rows]
    targets = [norm(row.get("target", "")) for row in rows]
    if len(set(asks)) != len(asks):
        findings.append("duplicate_natural_asks")
    if len(set(targets)) != len(targets):
        findings.append("duplicate_natural_targets")
    selected = []
    for row in rows:
        identity = row.get("pair_id", "<missing>")
        if row.get("expected") != PASS:
            findings.append(f"expected_not_pass:{identity}")
        if row.get("full_campaign_eligible") is not False or row.get("optimizer_eligible") is not False:
            findings.append(f"source_already_open:{identity}")
        if row.get("hold_only") is not True or row.get("training_authorized") is not False or row.get("run_authorized") is not False:
            findings.append(f"source_authority:{identity}")
        observed = judge(row["target"], axis=row["axis"], ask=row.get("ask", ""), use_cpu_sensor=False)["status"]
        if observed != PASS:
            findings.append(f"replay_mismatch:{identity}:{observed}")
        selected.append({"pair_id": identity, "axis": row["axis"], "ask": row["ask"], "target": row["target"]})
    status_counts = Counter(row["axis"] for row in selected)
    report = {
        "schema_version": "mouth_semantic_sft_candidate_projection_v1",
        "status": "SFT_CANDIDATE_PROJECTION_HOLD_ONLY" if not findings else "SFT_CANDIDATE_PROJECTION_FAIL",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evaluator": {"version": VERSION, "source_sha256": SOURCE_SHA256},
        "source": {"path": str(SOURCE).replace("\\", "/"), "sha256": sha256(SOURCE), "rows": len(rows)},
        "selection_rule": "positive natural-paraphrase pack only; expected PASS; unique asks/targets; replay PASS",
        "selected_rows": len(selected),
        "selected_axis_counts": dict(sorted(status_counts.items())),
        "selected_pair_ids": [row["pair_id"] for row in selected],
        "excluded_from_projection": {
            "semantic_bundle_total": 389,
            "other_pass_rows": 105,
            "all_fail_rows": 149,
            "all_hold_rows": 39,
            "reason": "judge-only matrices or non-PASS verdicts; not natural SFT inputs",
        },
        "rows_are_copied_or_admitted": False,
        "optimizer_eligible": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
        "findings": findings,
        "next_action": "separate_manifest_locked_campaign_review" if not findings else "repair_projection_findings",
        "selected_rows_preview": selected[:3],
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not findings, "status": report["status"], "selected_rows": report["selected_rows"], "optimizer_eligible": False, "output": str(OUT)}, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
