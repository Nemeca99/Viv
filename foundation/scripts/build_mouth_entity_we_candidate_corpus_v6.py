"""Build a schema-complete hold-only 272-row candidate from v5."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.entity_we_contract import classify_we  # noqa: E402
from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
PARENT = ROOT / "campaigns/mouth_full_run_entity_we_v2/train_256.jsonl"
EXPANSION = ROOT / "campaigns/mouth_entity_we_expansion_v5/positive_16_hold.jsonl"
OUT_ROOT = ROOT / "campaigns/mouth_entity_we_candidate_v6"
OUT = OUT_ROOT / "train_272_candidate_hold.jsonl"
MANIFEST = OUT_ROOT / "MANIFEST.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sentence_count(text: str) -> int:
    return max(1, len([part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part]))


def main() -> int:
    if OUT.exists() or MANIFEST.exists():
        raise FileExistsError("refuse_overwrite:mouth_entity_we_candidate_v6")
    OUT_ROOT.mkdir(parents=True, exist_ok=False)
    parent = [json.loads(line) for line in PARENT.read_text(encoding="utf-8").splitlines() if line.strip()]
    source = [json.loads(line) for line in EXPANSION.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(parent) == 256 and len(source) == 16
    expansion_sha = sha(EXPANSION)
    added = []
    errors = []
    for row in source:
        target = str(row["target"])
        we = classify_we(target)
        semantic = judge(target, axis="entity_we_boundary")
        if we["status"] != "ACCEPT" or semantic["status"] != "PASS":
            errors.append({"case_id": row["case_id"], "reason": "entity_we_not_accept"})
        category = sorted({item["category"] for item in we["occurrences"]})
        added.append({
            "anchor_coverage_verified": True,
            "approx_token_count": len(target.split()),
            "ask": row["ask"],
            "ask_hash": row["ask_hash"],
            "axis": "entity_we_boundary",
            "candidate_id": row["case_id"],
            "chosen": target,
            "entity_we_contract": "+".join(category) if category else "none",
            "full_campaign_eligible": False,
            "hold_only": True,
            "optimizer_eligible": False,
            "pair_id": row["case_id"],
            "response_only_loss_allowed": True,
            "run_authorized": False,
            "sentence_count": sentence_count(target),
            "source_anchor_pair_id": "anchor-anchor_train-entity_we_boundary-expansion-v5",
            "source_entity_candidate_id": row["case_id"],
            "source_entity_manifest_sha256": expansion_sha,
            "split": "train_candidate_hold",
            "target": target,
            "target_hash": row["target_hash"],
            "training_authorized": False,
        })
    required = set(parent[0])
    if any(set(row) != required for row in added):
        errors.append({"reason": "schema_projection_mismatch"})
    merged = parent + added
    OUT.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in merged), encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": "mouth_entity_we_candidate_corpus_v6",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "CANDIDATE_SCHEMA_COMPLETE_TRAINING_CLOSED" if not errors else "CANDIDATE_SCHEMA_FAIL",
        "parent_path": str(PARENT).replace("\\", "/"),
        "parent_sha256": sha(PARENT),
        "expansion_path": str(EXPANSION).replace("\\", "/"),
        "expansion_sha256": expansion_sha,
        "candidate_path": str(OUT).replace("\\", "/"),
        "candidate_sha256": sha(OUT),
        "parent_rows": len(parent),
        "expansion_rows": len(added),
        "candidate_rows": len(merged),
        "schema_fields": sorted(required),
        "axis_counts": dict(sorted(Counter(row.get("axis") for row in merged).items())),
        "errors": errors,
        "optimizer_eligible": False,
        "training_authorized": False,
        "run_authorized": False,
        "admission_allowed": False,
        "promotion_allowed": False,
        "next_action": "Review schema-complete candidate separately; do not admit or train from this artifact.",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: manifest[k] for k in ("status", "parent_rows", "expansion_rows", "candidate_rows", "axis_counts", "errors", "optimizer_eligible", "training_authorized", "run_authorized")}, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
