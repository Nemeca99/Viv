#!/usr/bin/env python3
"""Audit stable reason families and tri-state verdicts across semantic packs."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import FAIL, HOLD, PASS, SOURCE_SHA256, VERSION, judge, reason_family

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
POS = TREE / "mouth_semantic_refinement_v22_42/semantic_refinement_96_hold.jsonl"
NEG = TREE / "mouth_semantic_refinement_v22_adversarial/semantic_adversarial_48_judge_only.jsonl"
CAL = TREE / "mouth_semantics_calibration_v5/calibration_96.jsonl"
BLIND = TREE / "mouth_semantics_blind_v4/blind_48.jsonl"
BLIND_GOLD = TREE / "mouth_semantics_blind_v4/BLIND_GOLD_48.json"
CLOSURE = TREE / "mouth_semantic_operator_closure_v1/semantic_operator_closure_hold.jsonl"
MINIMAL = TREE / "mouth_semantic_minimal_pairs_v2/semantic_minimal_pairs_hold.jsonl"
GRID = TREE / "mouth_semantic_operator_grid_v1/semantic_operator_grid_hold.jsonl"
ENTITY = TREE / "mouth_entity_we_matrix_v3/entity_we_matrix_hold.jsonl"
ACRONYM = TREE / "mouth_acronym_contract_matrix_v1/acronym_contract_matrix_hold.jsonl"
EVIDENCE = TREE / "mouth_evidence_uncertainty_matrix_v2/evidence_uncertainty_matrix_hold.jsonl"
OUT = TREE / "mouth_semantic_refinement_v22_42/SEMANTIC_REASON_PROVENANCE_AUDIT_V13.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    findings: list[str] = []
    verdict_counts = Counter()
    family_counts = Counter()
    family_drift: list[dict] = []
    status_drift: list[dict] = []

    def check(pack: str, row: dict, expected: str | None = None, historical_reason: str | None = None, allowed: set[str] | None = None) -> None:
        result = judge(row["target"], axis=row["axis"], ask=row.get("ask", ""), use_cpu_sensor=False)
        observed = result["status"]
        observed_family = result["deterministic"].get("reason_family")
        verdict_counts[f"{pack}:{observed}"] += 1
        family_counts[f"{pack}:{observed_family}"] += 1
        if expected is not None and observed != expected and observed not in (allowed or set()):
            status_drift.append({"pack": pack, "pair_id": row.get("pair_id", row.get("case_id", "")), "expected": expected, "observed": observed})
        if historical_reason is not None:
            expected_family = reason_family(historical_reason)
            if expected_family != observed_family:
                family_drift.append({"pack": pack, "pair_id": row.get("pair_id", ""), "historical_reason": historical_reason, "expected_family": expected_family, "observed_family": observed_family})

    positive = rows(POS)
    negative = rows(NEG)
    calibration = rows(CAL)
    blind = rows(BLIND)
    gold = {row["case_id"]: row for row in json.loads(BLIND_GOLD.read_text(encoding="utf-8"))["rows"]}
    closure = rows(CLOSURE)
    minimal = rows(MINIMAL)
    grid = rows(GRID)
    entity = rows(ENTITY)
    acronym = rows(ACRONYM)
    evidence = rows(EVIDENCE)
    for row in positive:
        check("positive", row, PASS, row.get("target_judge", {}).get("reason"))
    for row in negative:
        check("negative", row, FAIL)
    for row in calibration:
        check("calibration", row, row["expected"])
    for row in blind:
        check("blind", row, gold[row["case_id"]]["expected"])
    promotions = {"operator-hold-00": PASS, "operator-hold-01": PASS}
    for row in closure:
        check("closure", row, promotions.get(row["pair_id"], row["expected"]), allowed={PASS} if row["pair_id"] in promotions else set())
    for row in minimal:
        check("minimal_pair", row, row["expected"])
    for row in grid:
        check("operator_grid", row, row["expected"])
    for row in entity:
        check("entity_we_matrix", row, row["expected"])
    for row in acronym:
        check("acronym_matrix", row, row["expected"])
    for row in evidence:
        check("evidence_uncertainty_matrix", row, row["expected"])

    if status_drift:
        findings.append(f"status_drift:{len(status_drift)}")
    if family_drift:
        findings.append(f"reason_family_drift:{len(family_drift)}")
    if any(row.get("hold_only") is not True or row.get("optimizer_eligible") is not False for row in closure):
        findings.append("closure_authorization_projection")
    report = {
        "schema_version": "mouth_reason_provenance_audit_v13",
        "status": "REASON_PROVENANCE_PASS" if not findings else "REASON_PROVENANCE_FAIL",
        "evaluator": {"version": VERSION, "source_sha256": SOURCE_SHA256},
        "source_files": {
            str(POS): {"sha256": sha(POS), "rows": len(positive)},
            str(NEG): {"sha256": sha(NEG), "rows": len(negative)},
            str(CAL): {"sha256": sha(CAL), "rows": len(calibration)},
            str(BLIND): {"sha256": sha(BLIND), "rows": len(blind)},
            str(BLIND_GOLD): {"sha256": sha(BLIND_GOLD), "rows": len(gold)},
            str(CLOSURE): {"sha256": sha(CLOSURE), "rows": len(closure)},
            str(MINIMAL): {"sha256": sha(MINIMAL), "rows": len(minimal)},
            str(GRID): {"sha256": sha(GRID), "rows": len(grid)},
            str(ENTITY): {"sha256": sha(ENTITY), "rows": len(entity)},
            str(ACRONYM): {"sha256": sha(ACRONYM), "rows": len(acronym)},
            str(EVIDENCE): {"sha256": sha(EVIDENCE), "rows": len(evidence)},
        },
        "training_authorized": False,
        "run_authorized": False,
        "optimizer_eligible": False,
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "reason_family_counts": dict(sorted(family_counts.items())),
        "status_drift": status_drift,
        "reason_family_drift": family_drift,
        "findings": findings,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not findings, "status_drift": len(status_drift), "reason_family_drift": len(family_drift), "output": str(OUT)}, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
