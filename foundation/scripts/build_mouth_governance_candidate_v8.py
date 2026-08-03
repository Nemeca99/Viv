"""Project governance positives onto the canonical generic training schema."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

F = Path(__file__).resolve().parents[1]
for p in (F, F.parent):
    if str(p) not in sys.path: sys.path.insert(0, str(p))
from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402

ROOT = F / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
SOURCE = ROOT / "campaigns/mouth_governance_semantics_expansion_v8/positive_36_hold.jsonl"
PARENT = ROOT / "campaigns/mouth_full_run_entity_we_v2/train_256.jsonl"
OUT_ROOT = ROOT / "campaigns/mouth_governance_candidate_v8"
OUT = OUT_ROOT / "positive_36_candidate_hold.jsonl"
MANIFEST = OUT_ROOT / "MANIFEST.json"


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists() or MANIFEST.exists(): raise FileExistsError("refuse_overwrite:mouth_governance_candidate_v8")
    OUT_ROOT.mkdir(parents=True, exist_ok=False)
    source = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    parent = [json.loads(line) for line in PARENT.read_text(encoding="utf-8").splitlines() if line.strip()]
    template = parent[0]
    schema = set(template)
    errors = []
    rows = []
    for item in source:
        target = item["target"]
        if judge(target, axis=item["axis"])["status"] != "PASS": errors.append({"case_id": item["case_id"], "reason": "semantic_target_not_pass"})
        rows.append({
            "anchor_coverage_verified": True,
            "approx_token_count": len(target.split()),
            "ask": item["ask"], "ask_hash": item["ask_hash"], "axis": item["axis"],
            "candidate_id": item["case_id"], "chosen": target,
            "full_campaign_eligible": False, "hold_only": True, "optimizer_eligible": False,
            "pair_id": item["case_id"], "response_only_loss_allowed": True, "run_authorized": False,
            "sentence_count": max(1, len([x for x in re.split(r"(?<=[.!?])\s+", target.strip()) if x])),
            "source_anchor_pair_id": "anchor-anchor_train-governance_semantics-expansion-v8",
            "split": "train_candidate_hold", "target": target, "target_hash": item["target_hash"], "training_authorized": False,
        })
    if any(set(row) != schema for row in rows): errors.append({"reason": "schema_projection_mismatch"})
    parent_asks = {row["ask_hash"] for row in parent}; parent_targets = {row["target_hash"] for row in parent}
    if parent_asks & {row["ask_hash"] for row in rows}: errors.append({"reason": "parent_ask_overlap"})
    if parent_targets & {row["target_hash"] for row in rows}: errors.append({"reason": "parent_target_overlap"})
    OUT.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {"schema_version": "mouth_governance_candidate_v8", "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "CANDIDATE_HOLD_TRAINING_CLOSED" if not errors else "CANDIDATE_FAIL", "source_path": str(SOURCE).replace("\\", "/"), "source_sha256": sha(SOURCE), "parent_path": str(PARENT).replace("\\", "/"), "parent_sha256": sha(PARENT), "candidate_path": str(OUT).replace("\\", "/"), "candidate_sha256": sha(OUT), "rows": len(rows), "axis_counts": dict(sorted(Counter(row["axis"] for row in rows).items())), "schema_fields": sorted(schema), "errors": errors, "optimizer_eligible": False, "training_authorized": False, "run_authorized": False, "admission_allowed": False, "promotion_allowed": False}
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: manifest[k] for k in ("status", "rows", "axis_counts", "errors", "optimizer_eligible", "training_authorized", "run_authorized")}, sort_keys=True)); return 0 if not errors else 1


if __name__ == "__main__": raise SystemExit(main())
