#!/usr/bin/env python3
"""Audit semantic-pack balance, operator coverage, and replay consistency.

This is a diagnostic hold-only audit.  It never admits, rewrites, or
authorizes the source packs.  Missing linguistic coverage is reported as a
finding so the next corpus expansion can target it explicitly.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.evaluator_v2_3_hybrid_v1_2_5 import FAIL, PASS, SOURCE_SHA256, VERSION, judge

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
POS_ROOT = TREE / "campaigns/mouth_semantic_refinement_v22_42"
NEG_ROOT = TREE / "campaigns/mouth_semantic_refinement_v22_adversarial"
POS = POS_ROOT / "semantic_refinement_96_hold.jsonl"
NEG = NEG_ROOT / "semantic_adversarial_48_judge_only.jsonl"
COVERAGE = TREE / "campaigns/mouth_semantic_coverage_pack_v2/semantic_coverage_pack_hold.jsonl"
RESIDUAL = TREE / "campaigns/mouth_semantic_residual_pack_v1/semantic_residual_pack_hold.jsonl"
OUT = POS_ROOT / "SEMANTIC_COVERAGE_AUDIT_V6.json"

FEATURES = {
    "negation": re.compile(r"\b(?:no|not|never|cannot|can't|doesn't|don't|without|isn't|won't)\b", re.I),
    "contrast": re.compile(r"\b(?:but|although|while|however|yet)\b", re.I),
    "conditional": re.compile(r"\b(?:if|unless|when|because|so that)\b", re.I),
    "pronoun_inheritance": re.compile(r"\bit\b", re.I),
    "indirect_expression": re.compile(r"\b(?:means?|refers?|sounds?|implies?|role|through|behind|voice|service|agency)\b", re.I),
    "uncertainty": re.compile(r"\b(?:may|might|could|uncertain|unclear|unknown|appears?|seems?)\b", re.I),
    "multi_clause": re.compile(r"[,;:]|\b(?:but|although|while|however)\b", re.I),
}


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, split: str) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            row["_split"] = split
            rows.append(row)
    return rows


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    positives = load(POS, "positive")
    negatives = load(NEG, "negative")
    coverage = load(COVERAGE, "coverage")
    residual = load(RESIDUAL, "residual")
    findings: list[str] = []
    rows = positives + negatives + coverage + residual
    if len(positives) != 96:
        findings.append(f"positive_row_count:{len(positives)}")
    if len(negatives) != 48:
        findings.append(f"negative_row_count:{len(negatives)}")
    if len(coverage) != 33:
        findings.append(f"coverage_row_count:{len(coverage)}")
    if len(residual) != 23:
        findings.append(f"residual_row_count:{len(residual)}")

    required = {"pair_id", "axis", "ask", "target"}
    malformed = [row.get("pair_id", "<missing>") for row in rows if not required.issubset(row)]
    if malformed:
        findings.append(f"malformed_rows:{len(malformed)}")

    ids = [row.get("pair_id") for row in rows]
    if len(set(ids)) != len(ids):
        findings.append("duplicate_pair_ids")
    targets = [row.get("target") for row in rows]
    if len(set(targets)) != len(targets):
        findings.append("duplicate_targets")

    status_counts = Counter()
    feature_counts: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
    axis_counts = Counter()
    claim_counts: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        split = row["_split"]
        axis = row["axis"]
        axis_counts[f"{split}:{axis}"] += 1
        result = judge(row["target"], axis=axis, ask=row.get("ask", ""), use_cpu_sensor=False)
        status_counts[f"{split}:{result['status']}"] += 1
        expected = row.get("expected") if split in {"coverage", "residual"} else (PASS if split == "positive" else FAIL)
        if result["status"] != expected:
            findings.append(f"replay_mismatch:{row.get('pair_id', '<missing>')}")
        for name, pattern in FEATURES.items():
            feature_counts[split][axis][name] = feature_counts[split][axis].get(name, 0) + int(bool(pattern.search(row["target"])))
        for claim in result["deterministic"].get("identity_claims", []):
            claim_counts[split][claim["category"]] += 1

    # These are coverage observations, not verdict failures.  They identify
    # what the next targeted pack must add without pretending the current pack
    # is invalid.
    coverage_gaps = []
    for split in ("positive", "negative"):
        for axis in sorted({row["axis"] for row in rows if row["_split"] == split}):
            counts = feature_counts[split][axis]
            for name in ("contrast", "uncertainty", "conditional"):
                if counts.get(name, 0) == 0:
                    coverage_gaps.append(f"{split}:{axis}:{name}")

    report = {
        "schema_version": "mouth_semantic_coverage_audit_v6",
        "status": "SEMANTIC_COVERAGE_DIAGNOSTIC",
        "evaluator": {"version": VERSION, "source_sha256": SOURCE_SHA256},
        "source_files": {
            "positive": {"path": str(POS).replace("\\", "/"), "sha256": file_sha(POS), "rows": len(positives)},
            "negative": {"path": str(NEG).replace("\\", "/"), "sha256": file_sha(NEG), "rows": len(negatives)},
            "coverage": {"path": str(COVERAGE).replace("\\", "/"), "sha256": file_sha(COVERAGE), "rows": len(coverage)},
            "residual": {"path": str(RESIDUAL).replace("\\", "/"), "sha256": file_sha(RESIDUAL), "rows": len(residual)},
        },
        "training_authorized": False,
        "run_authorized": False,
        "optimizer_eligible": False,
        "status_counts": dict(sorted(status_counts.items())),
        "axis_counts": dict(sorted(axis_counts.items())),
        "feature_counts": {
            split: {axis: dict(sorted(counts.items())) for axis, counts in sorted(by_axis.items())}
            for split, by_axis in sorted(feature_counts.items())
        },
        "identity_claim_counts": {
            split: dict(sorted(counts.items())) for split, counts in sorted(claim_counts.items())
        },
        "coverage_gaps": coverage_gaps,
        "findings": findings,
        "replay_pass": not findings,
        "next_action": "build_targeted_operator_closure_pack" if coverage_gaps else "review_for_admission",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not findings, "coverage_gaps": len(coverage_gaps), "findings": findings, "output": str(OUT)}, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
