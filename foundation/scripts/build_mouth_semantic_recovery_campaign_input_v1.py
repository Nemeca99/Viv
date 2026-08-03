#!/usr/bin/env python3
"""Package the refined semantic projection as a hold-only campaign input.

This creates a new immutable input package only.  It does not admit optimizer
rows, authorize training, open a lease, or execute model code.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
PROJECTION = TREE / "mouth_semantic_refinement_v22_42/SEMANTIC_SFT_CANDIDATE_PROJECTION_V4.json"
ROOT = TREE / "mouth_training_recovery_v3_semantic_projection_v1"
TRAIN_CANDIDATE = ROOT / "train_candidate_256_hold.jsonl"
MANIFEST = ROOT / "manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{ROOT}")
    projection = json.loads(PROJECTION.read_text(encoding="utf-8"))
    if projection.get("status") != "SFT_CANDIDATE_PROJECTION_HOLD_ONLY":
        raise ValueError("projection_not_hold_only")
    if projection.get("selected_rows") != 256 or projection.get("optimizer_eligible") is not False:
        raise ValueError("projection_contract_invalid")
    metadata = projection.get("selected_row_metadata", [])
    if len(metadata) != 256 or len({row.get("pair_id") for row in metadata}) != 256:
        raise ValueError("projection_metadata_invalid")
    sources = [Path(item["path"].replace("/", "\\")) for item in projection["sources"]]
    source_by_id: dict[str, dict] = {}
    for source in sources:
        for line in source.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                source_by_id[row["pair_id"]] = row
    rows = []
    for item in metadata:
        source_row = source_by_id.get(item["pair_id"])
        if source_row is None:
            raise ValueError(f"missing_source_row:{item['pair_id']}")
        if source_row.get("expected") != "PASS" or source_row.get("hold_only") is not True:
            raise ValueError(f"source_row_not_hold_only:{item['pair_id']}")
        rows.append({
            "ask": source_row["ask"],
            "chosen": source_row.get("chosen", source_row["target"]),
            "target": source_row["target"],
            "axis": source_row["axis"],
            "pair_id": source_row["pair_id"],
            "source_role": item["source_role"],
            "style": item["style"],
            "hold_only": True,
            "optimizer_eligible": False,
            "training_authorized": False,
            "run_authorized": False,
        })
    ROOT.mkdir(parents=True)
    TRAIN_CANDIDATE.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "schema_version": "mouth_semantic_recovery_campaign_input_v1",
        "status": "CAMPAIGN_INPUT_READY_TRAINING_CLOSED",
        "created_utc": utc(),
        "projection": {"path": str(PROJECTION).replace("\\", "/"), "sha256": sha256(PROJECTION)},
        "candidate": {"path": str(TRAIN_CANDIDATE).replace("\\", "/"), "sha256": sha256(TRAIN_CANDIDATE), "rows": len(rows)},
        "axis_counts": dict(sorted(Counter(row["axis"] for row in rows).items())),
        "source_role_counts": dict(sorted(Counter(row["source_role"] for row in rows).items())),
        "training_authorized": False,
        "run_authorized": False,
        "optimizer_eligible": False,
        "lora_authorized": False,
        "dpo_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "promotion_allowed": False,
        "deployment_allowed": False,
        "next_action": "separate_admission_and_campaign_preflight_review",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "status": manifest["status"], "rows": len(rows), "training_authorized": False, "run_authorized": False, "output": str(ROOT)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
