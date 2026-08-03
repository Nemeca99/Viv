#!/usr/bin/env python3
"""Audit the expanded hold-only natural SFT candidate projection."""
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
SOURCES = [ROOT / "semantic_refinement_96_hold.jsonl", FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_natural_expansion_v1/semantic_natural_expansion_hold.jsonl", FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantic_natural_completion_v1_2/semantic_natural_completion_hold.jsonl"]
OUT = ROOT / "SEMANTIC_SFT_CANDIDATE_PROJECTION_V4.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    rows = []
    for source in SOURCES:
        rows.extend(json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip())
    findings = []
    if len(rows) != 256:
        findings.append(f"source_row_count:{len(rows)}")
    if len({norm(row.get("ask", "")) for row in rows}) != len(rows):
        findings.append("duplicate_natural_asks")
    if len({norm(row.get("target", "")) for row in rows}) != len(rows):
        findings.append("duplicate_natural_targets")
    selected = []
    for row in rows:
        identity = row.get("pair_id", "<missing>")
        if row.get("expected") != PASS:
            findings.append(f"expected_not_pass:{identity}")
        if row.get("optimizer_eligible") is not False or row.get("hold_only") is not True or row.get("training_authorized") is not False or row.get("run_authorized") is not False:
            findings.append(f"source_authority:{identity}")
        observed = judge(row["target"], axis=row["axis"], ask=row.get("ask", ""), use_cpu_sensor=False)["status"]
        if observed != PASS:
            findings.append(f"replay_mismatch:{identity}:{observed}")
        selected.append({"pair_id": identity, "axis": row["axis"], "ask": row["ask"], "target": row["target"], "source": str(next(source for source in SOURCES if identity in source.read_text(encoding='utf-8'))).replace('\\', '/')})
    report = {
        "schema_version": "mouth_semantic_sft_candidate_projection_v4",
        "status": "SFT_CANDIDATE_PROJECTION_HOLD_ONLY" if not findings else "SFT_CANDIDATE_PROJECTION_FAIL",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evaluator": {"version": VERSION, "source_sha256": SOURCE_SHA256},
        "sources": [{"path": str(source).replace('\\', '/'), "sha256": sha256(source), "rows": sum(1 for line in source.read_text(encoding='utf-8').splitlines() if line.strip())} for source in SOURCES],
        "selection_rule": "three natural-paraphrase packs only; expected PASS; unique asks/targets; replay PASS",
        "selected_rows": len(selected),
        "selected_axis_counts": dict(sorted(Counter(row["axis"] for row in selected).items())),
        "selected_pair_ids": [row["pair_id"] for row in selected],
        "selected_row_metadata": [
            {
                "pair_id": row["pair_id"],
                "axis": row["axis"],
                "source_role": (
                    "legacy_rehearsal" if "semantic_refinement_96_hold.jsonl" in row["source"]
                    else "natural_expansion" if "semantic_natural_expansion_v1" in row["source"]
                    else "natural_completion"
                ),
                "style": next(
                    source_row.get("style") or "legacy_rehearsal"
                    for source in SOURCES
                    for source_row in (json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip())
                    if source_row.get("pair_id") == row["pair_id"]
                ),
                "ask_words": len(row["ask"].split()),
                "target_words": len(row["target"].split()),
            }
            for row in selected
        ],
        "excluded_from_projection": {"semantic_bundle_total": 549, "excluded_rows": 293, "reason": "judge-only matrices or non-PASS verdicts; not natural SFT inputs"},
        "rows_are_copied_or_admitted": False,
        "optimizer_eligible": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
        "findings": findings,
        "next_action": "separate_manifest_locked_campaign_review" if not findings else "repair_projection_findings",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not findings, "status": report["status"], "selected_rows": report["selected_rows"], "optimizer_eligible": False, "output": str(OUT)}, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
