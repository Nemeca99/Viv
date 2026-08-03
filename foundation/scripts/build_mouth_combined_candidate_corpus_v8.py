"""Build the combined 308-row hold-only corpus view."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

F = Path(__file__).resolve().parents[1]
ROOT = F / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
ENTITY = ROOT / "campaigns/mouth_entity_we_candidate_v7/train_272_candidate_hold.jsonl"
GOV = ROOT / "campaigns/mouth_governance_candidate_v8/positive_36_candidate_hold.jsonl"
OUT_ROOT = ROOT / "campaigns/mouth_combined_candidate_v8"
OUT = OUT_ROOT / "train_308_candidate_hold.jsonl"
MANIFEST = OUT_ROOT / "MANIFEST.json"


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path: Path) -> list[dict]: return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    if OUT.exists() or MANIFEST.exists(): raise FileExistsError("refuse_overwrite:mouth_combined_candidate_v8")
    OUT_ROOT.mkdir(parents=True, exist_ok=False)
    entity, gov = load(ENTITY), load(GOV)
    rows = entity + gov
    errors = []
    if len(entity) != 272 or len(gov) != 36 or len(rows) != 308: errors.append({"reason": "row_count"})
    asks = [row.get("ask_hash") for row in rows]; targets = [row.get("target_hash") for row in rows]
    if len(set(asks)) != len(asks): errors.append({"reason": "ask_overlap"})
    if len(set(targets)) != len(targets): errors.append({"reason": "target_overlap"})
    if any(row.get("optimizer_eligible") is not False or row.get("training_authorized") is not False or row.get("run_authorized") is not False for row in rows): errors.append({"reason": "authorization_open"})
    OUT.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {"schema_version": "mouth_combined_candidate_corpus_v8", "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "COMBINED_CANDIDATE_HOLD_TRAINING_CLOSED" if not errors else "COMBINED_CANDIDATE_FAIL", "entity_source": str(ENTITY).replace("\\", "/"), "entity_source_sha256": sha(ENTITY), "governance_source": str(GOV).replace("\\", "/"), "governance_source_sha256": sha(GOV), "candidate_path": str(OUT).replace("\\", "/"), "candidate_sha256": sha(OUT), "entity_rows": len(entity), "governance_rows": len(gov), "candidate_rows": len(rows), "axis_counts": dict(sorted(Counter(row.get("axis") for row in rows).items())), "errors": errors, "optimizer_eligible": False, "training_authorized": False, "run_authorized": False, "admission_allowed": False, "promotion_allowed": False}
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: manifest[k] for k in ("status", "entity_rows", "governance_rows", "candidate_rows", "axis_counts", "errors", "optimizer_eligible", "training_authorized", "run_authorized")}, sort_keys=True)); return 0 if not errors else 1


if __name__ == "__main__": raise SystemExit(main())
