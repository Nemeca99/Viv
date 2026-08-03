"""Append governance-semantic v11 positives to verified v18 candidate."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
PARENT = ROOT / "campaigns/mouth_combined_candidate_v18/train_332_candidate_hold.jsonl"
EXPANSION = ROOT / "campaigns/mouth_governance_semantics_expansion_v12/positive_36_hold.jsonl"
OUT_ROOT = ROOT / "campaigns/mouth_combined_candidate_v20"
OUT = OUT_ROOT / "train_368_candidate_hold.jsonl"
MANIFEST = OUT_ROOT / "MANIFEST.json"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT_ROOT.exists():
        raise FileExistsError("refuse_overwrite:mouth_combined_candidate_v20")
    OUT_ROOT.mkdir(parents=True, exist_ok=False)
    parent = load(PARENT)
    added = load(EXPANSION)
    rows = parent + added
    errors = []
    if len(parent) != 332 or len(added) != 36 or len(rows) != 368:
        errors.append("row_count")
    if {row["ask_hash"] for row in parent} & {row["ask_hash"] for row in added}:
        errors.append("ask_overlap")
    if {row["target_hash"] for row in parent} & {row["target_hash"] for row in added}:
        errors.append("target_overlap")
    if any(row.get("optimizer_eligible") is not False or row.get("training_authorized") is not False or row.get("run_authorized") is not False for row in added):
        errors.append("new_rows_authorization_open")
    OUT.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {"schema_version": "mouth_combined_candidate_corpus_v20", "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "COMBINED_CANDIDATE_HOLD_TRAINING_CLOSED" if not errors else "COMBINED_CANDIDATE_FAIL", "parent_path": str(PARENT).replace("\\", "/"), "parent_sha256": sha(PARENT), "expansion_path": str(EXPANSION).replace("\\", "/"), "expansion_sha256": sha(EXPANSION), "candidate_path": str(OUT).replace("\\", "/"), "candidate_sha256": sha(OUT), "parent_rows": len(parent), "added_rows": len(added), "candidate_rows": len(rows), "axis_counts": dict(sorted(Counter(row["axis"] for row in rows).items())), "errors": errors, "parent_preserved": True, "new_rows_hold_only": True, "admission_allowed": False, "optimizer_eligible": False, "training_authorized": False, "run_authorized": False, "promotion_allowed": False}
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: manifest[key] for key in ("status", "parent_rows", "added_rows", "candidate_rows", "axis_counts", "errors", "training_authorized")}, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
