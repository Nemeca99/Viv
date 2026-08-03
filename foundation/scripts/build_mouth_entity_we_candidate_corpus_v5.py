"""Construct a manifest-locked 272-row hold-only corpus candidate."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_entity_we_candidate_v5"
PARENT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_full_run_entity_we_v2/train_256.jsonl"
EXPANSION = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_entity_we_expansion_v5/positive_16_hold.jsonl"
OUT = ROOT / "train_272_candidate_hold.jsonl"
MANIFEST = ROOT / "MANIFEST.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists() or MANIFEST.exists():
        raise FileExistsError("refuse_overwrite:mouth_entity_we_candidate_v5")
    ROOT.mkdir(parents=True, exist_ok=False)
    parent = [json.loads(line) for line in PARENT.read_text(encoding="utf-8").splitlines() if line.strip()]
    expansion = [json.loads(line) for line in EXPANSION.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(parent) == 256 and len(expansion) == 16
    parent_bytes = PARENT.read_bytes()
    parent_asks = {row["ask_hash"] for row in parent}
    parent_targets = {row["target_hash"] for row in parent}
    errors = []
    for row in expansion:
        if row["ask_hash"] in parent_asks or row["target_hash"] in parent_targets:
            errors.append({"case_id": row["case_id"], "reason": "parent_overlap"})
        if row.get("optimizer_eligible") is not False or row.get("training_authorized") is not False:
            errors.append({"case_id": row["case_id"], "reason": "candidate_not_hold_only"})
        if judge(row["target"], axis="entity_we_boundary")["status"] != "PASS":
            errors.append({"case_id": row["case_id"], "reason": "semantic_target_not_pass"})
    merged = parent + expansion
    assert len(merged) == 272
    OUT.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in merged), encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": "mouth_entity_we_candidate_corpus_v5",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "CANDIDATE_HOLD_TRAINING_CLOSED" if not errors else "CANDIDATE_FAIL",
        "parent_path": str(PARENT).replace("\\", "/"),
        "parent_sha256": sha(PARENT),
        "parent_bytes_preserved": PARENT.read_bytes() == parent_bytes,
        "expansion_path": str(EXPANSION).replace("\\", "/"),
        "expansion_sha256": sha(EXPANSION),
        "candidate_path": str(OUT).replace("\\", "/"),
        "candidate_sha256": sha(OUT),
        "parent_rows": len(parent),
        "expansion_rows": len(expansion),
        "candidate_rows": len(merged),
        "axis_counts": dict(sorted(Counter(row.get("axis") for row in merged).items())),
        "errors": errors,
        "optimizer_eligible": False,
        "training_authorized": False,
        "run_authorized": False,
        "admission_allowed": False,
        "promotion_allowed": False,
        "next_action": "Review candidate manifest separately; do not admit or train from this artifact.",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: manifest[k] for k in ("status", "parent_rows", "expansion_rows", "candidate_rows", "axis_counts", "errors", "optimizer_eligible", "training_authorized", "run_authorized")}, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
