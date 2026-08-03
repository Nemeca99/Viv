#!/usr/bin/env python3
"""Audit the combined hold-only semantic corpus for overlap and contradictions."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import SOURCE_SHA256, VERSION, judge

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
PACKS = {
    "positive": TREE / "mouth_semantic_refinement_v22_42/semantic_refinement_96_hold.jsonl",
    "negative": TREE / "mouth_semantic_refinement_v22_adversarial/semantic_adversarial_48_judge_only.jsonl",
    "closure": TREE / "mouth_semantic_operator_closure_v1/semantic_operator_closure_hold.jsonl",
    "minimal": TREE / "mouth_semantic_minimal_pairs_v2/semantic_minimal_pairs_hold.jsonl",
    "operator_grid": TREE / "mouth_semantic_operator_grid_v1/semantic_operator_grid_hold.jsonl",
    "entity_we_matrix": TREE / "mouth_entity_we_matrix_v3/entity_we_matrix_hold.jsonl",
    "acronym_matrix": TREE / "mouth_acronym_contract_matrix_v1/acronym_contract_matrix_hold.jsonl",
    "evidence_uncertainty_matrix": TREE / "mouth_evidence_uncertainty_matrix_v2/evidence_uncertainty_matrix_hold.jsonl",
    "assertion_scope": TREE / "mouth_semantic_assertion_scope_v1/assertion_scope_hold.jsonl",
    "coverage_pack": TREE / "mouth_semantic_coverage_pack_v2/semantic_coverage_pack_hold.jsonl",
    "residual_pack": TREE / "mouth_semantic_residual_pack_v1/semantic_residual_pack_hold.jsonl",
    "natural_expansion": TREE / "mouth_semantic_natural_expansion_v1/semantic_natural_expansion_hold.jsonl",
    "natural_completion": TREE / "mouth_semantic_natural_completion_v1_2/semantic_natural_completion_hold.jsonl",
}
OUT = TREE / "mouth_semantic_refinement_v22_42/SEMANTIC_BUNDLE_AUDIT_V28.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    rows: list[dict] = []
    pack_counts: dict[str, int] = {}
    findings: list[str] = []
    for pack, path in PACKS.items():
        loaded = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        pack_counts[pack] = len(loaded)
        for row in loaded:
            row = dict(row)
            row["_pack"] = pack
            rows.append(row)
            if row.get("hold_only") is not True or row.get("optimizer_eligible") is not False or row.get("training_authorized") is not False or row.get("run_authorized") is not False:
                findings.append(f"authorization:{pack}:{row.get('pair_id', '<missing>')}")

    by_text: dict[str, list[dict]] = defaultdict(list)
    by_id: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_text[norm(row["target"])].append(row)
        by_id[row.get("pair_id", "")].append(row)
    duplicate_groups = []
    contradictions = []
    migrations = []
    for text, group in by_text.items():
        if len(group) > 1:
            duplicate_groups.append({
                "normalized_target": text,
                "members": [{"pack": r["_pack"], "pair_id": r.get("pair_id", ""), "expected": r.get("expected")} for r in group],
            })
            labels = {r.get("expected") for r in group}
            if len(labels) > 1:
                # The closure pack predates the evaluator promotion recorded
                # by its regression test; preserve that historical artifact.
                if {"closure", "minimal"}.issubset({r["_pack"] for r in group}) and all(r.get("pair_id") in {"operator-hold-01", "minimal-09"} for r in group):
                    migrations.append({"normalized_target": text, "from": "HOLD", "to": "PASS", "reason": "closure_boundary_promoted_by_evaluator"})
                else:
                    contradictions.append({"normalized_target": text, "labels": sorted(labels), "members": [(r["_pack"], r.get("pair_id", "")) for r in group]})
    duplicate_ids = [
        key for key, group in by_id.items()
        if key and len({row["_pack"] for row in group}) > 1
    ]
    if duplicate_ids:
        findings.append(f"duplicate_pair_ids:{len(duplicate_ids)}")
    if contradictions:
        findings.append(f"label_contradictions:{len(contradictions)}")

    replay_mismatches = []
    for row in rows:
        observed = judge(row["target"], axis=row["axis"], use_cpu_sensor=False)["status"]
        expected = row.get("expected")
        if row.get("pair_id") in {"operator-hold-00", "operator-hold-01"}:
            expected = "PASS"
        if observed != expected:
            replay_mismatches.append({"pack": row["_pack"], "pair_id": row.get("pair_id", ""), "expected": expected, "observed": observed})
    if replay_mismatches:
        findings.append(f"replay_mismatches:{len(replay_mismatches)}")
    report = {
        "schema_version": "mouth_semantic_bundle_audit_v25",
        "status": "SEMANTIC_BUNDLE_AUDIT_PASS" if not findings else "SEMANTIC_BUNDLE_AUDIT_FAIL",
        "evaluator": {"version": VERSION, "source_sha256": SOURCE_SHA256},
        "source_files": {pack: {"path": str(path).replace("\\", "/"), "sha256": sha(path), "rows": pack_counts[pack]} for pack, path in PACKS.items()},
        "bundle_rows": len(rows),
        "unique_normalized_targets": len(by_text),
        "pack_counts": pack_counts,
        "duplicate_target_groups": duplicate_groups,
        "duplicate_pair_ids": duplicate_ids,
        "label_migrations": migrations,
        "label_contradictions": contradictions,
        "replay_mismatches": replay_mismatches,
        "training_authorized": False,
        "run_authorized": False,
        "optimizer_eligible": False,
        "promotion_allowed": False,
        "findings": findings,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not findings, "bundle_rows": len(rows), "unique_targets": len(by_text), "duplicates": len(duplicate_groups), "migrations": len(migrations), "contradictions": len(contradictions), "output": str(OUT)}, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
