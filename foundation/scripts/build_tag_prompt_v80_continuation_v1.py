#!/usr/bin/env python3
"""Prepare a bounded production-prompt continuation from the V79 checkpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil

FOUNDATION = Path(__file__).resolve().parents[1]
CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
SOURCE_ID = "tag_prompt_campaign_v79_production_aligned_20260803T020500Z"
PARENT_RUN = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v79_production_aligned_20260803T020500Z_20260802T160809Z"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build(campaign_id: str) -> dict:
    source = CAMPAIGNS / SOURCE_ID
    root = CAMPAIGNS / campaign_id
    parent = PARENT_RUN / "adapter_step_2"
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not source.is_dir() or not (source / "manifest.json").is_file():
        raise FileNotFoundError("v79_source_campaign_missing")
    source_manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if source_manifest.get("status") != "CAMPAIGN_EXECUTED_NO_PROMOTION":
        raise ValueError(f"v79_not_closed:{source_manifest.get('status')}")
    if not parent.is_dir() or not (parent / "adapter_model.safetensors").is_file():
        raise FileNotFoundError(f"v79_checkpoint_missing:{parent}")
    root.mkdir(parents=True)
    files = {}
    for name in ("train.jsonl", "development.jsonl", "holdout.jsonl"):
        src = source / name
        dst = root / name
        shutil.copy2(src, dst)
        files[name.removesuffix(".jsonl")] = {
            "path": name,
            "rows": sum(1 for line in dst.read_text(encoding="utf-8").splitlines() if line.strip()),
            "sha256": sha256(dst),
        }
    manifest = {
        "schema_version": "aios_tag_v80_continuation_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "v79_exact_production_prompt_continuation",
        "route_contract": {
            "prompt": "reference.packet_plus_render_openaster_prompt",
            "evaluation_prompt_equivalence": True,
            "live_config_changed": False,
        },
        "planned_scope": {
            "optimizer_steps": 4,
            "learning_rate": 2.5e-9,
            "anchor_strength": 0.4,
            "contract_token_weight": 2.0,
            "contrastive_weight": 0.0,
            "pairwise_weight": 0.0,
            "promotion_authorized": False,
            "deployment_authorized": False,
        },
        "parent_adapter": {
            "path": str(parent / "adapter_model.safetensors").replace("\\", "/"),
            "sha256": sha256(parent / "adapter_model.safetensors"),
        },
        "source_campaign": {
            "path": str(source).replace("\\", "/"),
            "manifest_sha256": sha256(source / "manifest.json"),
        },
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
    preflight = {
        "schema_version": "aios_tag_v80_continuation_preflight_v1",
        "status": "PREFLIGHT_PASS_TRAINING_CLOSED",
        "recorded_utc": utc(),
        "campaign_root": str(root).replace("\\", "/"),
        "manifest_sha256": sha256(manifest_path),
        "parent_adapter": manifest["parent_adapter"],
        "source_campaign": manifest["source_campaign"],
        "files": files,
        "rows": manifest["rows"],
        "route_contract": manifest["route_contract"],
        "findings": [],
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "model_loaded": False,
        "next_action": "separate_execution_authorization",
    }
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
