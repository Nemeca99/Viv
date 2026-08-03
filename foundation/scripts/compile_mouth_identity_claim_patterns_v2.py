#!/usr/bin/env python3
"""Compile identity-claim patterns across the complete semantic bundle."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid import SOURCE_SHA256, VERSION, judge

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
PACKS = {
    "positive": TREE / "mouth_semantic_refinement_v22_42/semantic_refinement_96_hold.jsonl",
    "negative": TREE / "mouth_semantic_refinement_v22_adversarial/semantic_adversarial_48_judge_only.jsonl",
    "closure": TREE / "mouth_semantic_operator_closure_v1/semantic_operator_closure_hold.jsonl",
    "minimal": TREE / "mouth_semantic_minimal_pairs_v2/semantic_minimal_pairs_hold.jsonl",
    "operator_grid": TREE / "mouth_semantic_operator_grid_v1/semantic_operator_grid_hold.jsonl",
    "entity_we_matrix": TREE / "mouth_entity_we_matrix_v3/entity_we_matrix_hold.jsonl",
}
OUT = TREE / "mouth_semantic_refinement_v22_42/IDENTITY_CLAIM_PATTERN_REPORT_V4.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, pack: str) -> list[dict]:
    loaded = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            row["_pack"] = pack
            loaded.append(row)
    return loaded


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    rows = [row for pack, path in PACKS.items() for row in load(path, pack)]
    claim_counts = Counter()
    pack_claim_counts = Counter()
    axis_claim_counts = Counter()
    status_counts = Counter()
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    missing_ledger = []
    for row in rows:
        result = judge(row["target"], axis=row["axis"], ask=row.get("ask", ""), use_cpu_sensor=False)
        status_counts[f"{row['_pack']}:{result['status']}"] += 1
        claims = result.get("deterministic", {}).get("identity_claims")
        if not isinstance(claims, list):
            missing_ledger.append(row.get("pair_id", "<missing>"))
            continue
        for claim in claims:
            category = claim["category"]
            claim_counts[category] += 1
            pack_claim_counts[f"{row['_pack']}:{category}"] += 1
            axis_claim_counts[f"{row['axis']}:{category}"] += 1
            if len(examples[category]) < 8:
                examples[category].append({"pack": row["_pack"], "axis": row["axis"], "pair_id": row.get("pair_id", ""), "match": claim["match"], "context": claim["context"]})
    report = {
        "schema_version": "mouth_identity_claim_pattern_report_v4",
        "status": "IDENTITY_CLAIM_PATTERN_REPORT_DIAGNOSTIC",
        "evaluator": {"version": VERSION, "source_sha256": SOURCE_SHA256},
        "source_files": {pack: {"path": str(path).replace("\\", "/"), "sha256": sha(path), "rows": len(load(path, pack))} for pack, path in PACKS.items()},
        "row_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "claim_counts": dict(sorted(claim_counts.items())),
        "claim_counts_by_pack": dict(sorted(pack_claim_counts.items())),
        "claim_counts_by_axis": dict(sorted(axis_claim_counts.items())),
        "examples": {key: value for key, value in sorted(examples.items())},
        "missing_identity_ledger_rows": missing_ledger,
        "training_authorized": False,
        "run_authorized": False,
        "optimizer_eligible": False,
        "promotion_allowed": False,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not missing_ledger, "rows": len(rows), "claim_counts": dict(claim_counts), "missing_ledger": len(missing_ledger), "output": str(OUT)}, sort_keys=True))
    return 0 if not missing_ledger else 1


if __name__ == "__main__":
    raise SystemExit(main())
