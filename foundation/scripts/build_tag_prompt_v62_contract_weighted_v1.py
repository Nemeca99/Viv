#!/usr/bin/env python3
"""Admit the v61 corpus for a contract-token-weighted objective canary."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
SOURCE = CAMPAIGNS / "tag_prompt_campaign_v61_dual_residual_replay"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not SOURCE.is_dir() or not PARENT.is_file():
        raise FileNotFoundError("source_or_parent_missing")
    root.mkdir(parents=True)
    files = {}
    for split in ("train", "development", "holdout"):
        source = SOURCE / f"{split}.jsonl"
        target = root / source.name
        shutil.copy2(source, target)
        files[split] = {"path": target.name, "rows": len(rows(target)), "sha256": sha(target)}
    manifest = {
        "schema_version": "aios_tag_v62_contract_weighted_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "v61_dual_residual_replay_with_contract_token_weighting",
        "source": {"campaign": SOURCE.name, "manifest_sha256": sha(SOURCE / "manifest.json")},
        "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha(PARENT)},
        "files": files,
        "rows": {key: value["rows"] for key, value in files.items()},
        "objective": {"contract_token_weight": 3.0, "standard_eval_nll": True, "response_only_loss": True},
        "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0,
        "promotion_allowed": False, "deployment_changed": False,
        "next_action": "read_only_preflight_then_separate_execution_authorization",
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    preflight = {
        "schema_version": "aios_tag_v62_contract_weighted_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED",
        "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha(manifest_path),
        "files": files, "parent_adapter": manifest["parent_adapter"], "rows": manifest["rows"],
        "objective": manifest["objective"], "findings": [], "training_authorized": False,
        "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False,
        "next_action": "separate_execution_authorization",
    }
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    print(json.dumps(build(parser.parse_args().campaign_id), indent=2, sort_keys=True))
