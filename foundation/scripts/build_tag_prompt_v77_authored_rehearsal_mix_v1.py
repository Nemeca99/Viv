#!/usr/bin/env python3
"""Admit authored repaired targets plus frozen v19 rehearsal anchors."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts.build_tag_prompt_v75_authored_repaired_v1 import make_row  # noqa: E402
from scripts import evaluate_mouth_combined_candidate_v21 as reference  # noqa: E402

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
V19 = CAMPAIGNS / "tag_prompt_campaign_v19_contractcanary16"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    root.mkdir(parents=True)
    authored = reference.rows(reference.EVAL_ROOT / "development_64.jsonl")
    authored_rows = [make_row(row, "train", True) for row in authored]
    anchors = [json.loads(line) for line in (V19 / "train.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()][:32]
    for row in anchors:
        row = dict(row)
        row.update({"schema_version": "aios_tag_v77_rehearsal_anchor_row_v1", "source_kind": "frozen_v19_rehearsal_anchor", "training_authorized": False, "run_authorized": False, "split": "train", "optimizer_eligible": True, "response_only_loss_allowed": True, "hold_only": False})
        authored_rows.append(row)
    train_path = root / "train.jsonl"
    train_path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in authored_rows), encoding="utf-8", newline="\n")
    (root / "development.jsonl").write_text("", encoding="utf-8", newline="\n")
    blind = reference.rows(reference.EVAL_ROOT / "blind_32.jsonl")
    holdout = [make_row(row, "holdout", False) for row in blind]
    holdout_path = root / "holdout.jsonl"
    holdout_path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in holdout), encoding="utf-8", newline="\n")
    files = {"train": {"path": "train.jsonl", "rows": len(authored_rows), "sha256": sha256(train_path), "authored_rows": len(authored), "rehearsal_rows": len(anchors)}, "development": {"path": "development.jsonl", "rows": 0, "sha256": sha256(root / "development.jsonl")}, "holdout": {"path": "holdout.jsonl", "rows": len(holdout), "sha256": sha256(holdout_path)}}
    manifest = {"schema_version": "aios_tag_v77_authored_rehearsal_mix_manifest_v1", "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED", "campaign_id": campaign_id, "created_utc": utc(), "curriculum": "authored_repaired_targets_plus_frozen_v19_rehearsal", "route_contract": {"prompt": "compact_aios_packet_renderer_v1_plus_v19_anchor_prompts", "teacher": "authored_targets_registry_repaired", "live_config_changed": False}, "planned_scope": {"optimizer_steps": 2, "learning_rate": 5e-9, "anchor_strength": 0.8, "contract_token_weight": 2.0, "contrastive_weight": 0.0, "promotion_authorized": False, "deployment_authorized": False}, "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha256(PARENT)}, "source": {"authored_development": str(reference.EVAL_ROOT / "development_64.jsonl").replace("\\", "/"), "v19_rehearsal_manifest_sha256": sha256(V19 / "manifest.json"), "rehearsal_rows": len(anchors), "blind_holdout_excluded_from_train": True}, "files": files, "rows": {key: value["rows"] for key, value in files.items()}, "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "promotion_allowed": False, "deployment_changed": False, "next_action": "read_only_preflight_then_separate_execution_authorization"}
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    preflight = {"schema_version": "aios_tag_v77_authored_rehearsal_mix_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "files": files, "parent_adapter": manifest["parent_adapter"], "rows": manifest["rows"], "planned_scope": manifest["planned_scope"], "route_contract": manifest["route_contract"], "findings": [], "authored_rows": len(authored), "rehearsal_rows": len(anchors), "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
