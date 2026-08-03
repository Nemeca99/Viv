#!/usr/bin/env python3
"""Admit v66 contrastive repair with frozen v19 replay anchors."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
V66 = CAMPAIGNS / "tag_prompt_campaign_v66_contrastive_failure_repair"
V19 = CAMPAIGNS / "tag_prompt_campaign_v19_contractcanary16"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not V66.is_dir() or not V19.is_dir() or not PARENT.is_file():
        raise FileNotFoundError("source_or_parent_missing")
    contrastive = [json.loads(line) for line in (V66 / "train.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    anchors = [json.loads(line) for line in (V19 / "train.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()][:20]
    if len(contrastive) != 20 or len(anchors) != 20:
        raise ValueError(f"row_count:{len(contrastive)}:{len(anchors)}")
    for row in anchors:
        row["source_role"] = "v19_frozen_preservation_anchor"
        row["negative_response"] = None
        row["schema_version"] = "aios_tag_v67_replay_anchor_row_v1"
        row["optimizer_eligible"] = True
        row["response_only_loss_allowed"] = True
        row["hold_only"] = False
        row["training_authorized"] = False
        row["run_authorized"] = False
        row["lease_opened"] = False
        row["gpu_steps"] = 0
        row["promotion_allowed"] = False
        row["deployment_changed"] = False
    train = contrastive + anchors
    for row in train:
        row["split"] = "train"
    root.mkdir(parents=True)
    files = {}
    for split in ("train", "development", "holdout"):
        if split == "train":
            selected = train
        else:
            selected = [json.loads(line) for line in (V66 / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            for row in selected:
                row["schema_version"] = "aios_tag_v67_eval_row_v1"
        path = root / f"{split}.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8", newline="\n")
        files[split] = {"path": path.name, "rows": len(selected), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_v67_contrastive_replay_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "contrastive_failure_repair_with_incumbent_replay",
        "contrastive_objective": {"enabled": True, "weight": 0.10, "margin": 0.10, "negative_rows": 20, "preservation_anchor_rows": 20},
        "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha256(PARENT)},
        "source": {"contrastive_campaign": str(V66).replace("\\", "/"), "contrastive_manifest_sha256": sha256(V66 / "manifest.json"), "replay_campaign": str(V19).replace("\\", "/"), "replay_manifest_sha256": sha256(V19 / "manifest.json"), "disjoint_holdout_preserved": True},
        "files": files,
        "rows": {key: value["rows"] for key, value in files.items()},
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "promotion_allowed": False,
        "deployment_changed": False,
        "next_action": "read_only_preflight_then_separate_execution_authorization",
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    preflight = {"schema_version": "aios_tag_v67_contrastive_replay_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "files": files, "parent_adapter": manifest["parent_adapter"], "rows": manifest["rows"], "contrastive_objective": manifest["contrastive_objective"], "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
