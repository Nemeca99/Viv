#!/usr/bin/env python3
"""Admit a governed pairwise-preference canary from the compact v72b corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
SOURCE_ID = "tag_prompt_campaign_v72b_compact_packet_teacher"
SOURCE = CAMPAIGNS / SOURCE_ID
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
    if not SOURCE.is_dir() or not PARENT.is_file():
        raise FileNotFoundError("source_or_parent_missing")
    root.mkdir(parents=True)
    files = {}
    for name in ("train", "development", "holdout"):
        source = SOURCE / f"{name}.jsonl"
        target = root / source.name
        target.write_bytes(source.read_bytes())
        files[name] = {"path": target.name, "rows": sum(1 for line in target.read_text(encoding="utf-8").splitlines() if line.strip()), "sha256": sha256(target), "source_sha256": sha256(source)}
    manifest = {
        "schema_version": "aios_tag_v73_pairwise_preference_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "compact_packet_cpu_teacher_pairwise_preference",
        "route_contract": {"prompt": "compact_aios_packet_renderer_v1", "teacher": "cpu_finalized_positive_vs_raw_negative", "objective": "reference_free_pairwise_softplus", "live_config_changed": False},
        "planned_scope": {"optimizer_steps": 4, "learning_rate": 5e-9, "anchor_strength": 0.8, "contract_token_weight": 1.0, "contrastive_weight": 0.0, "pairwise_weight": 0.5, "pairwise_beta": 1.0, "pairwise_margin": 0.2, "promotion_authorized": False, "deployment_authorized": False},
        "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha256(PARENT)},
        "source": {"campaign": str(SOURCE).replace("\\", "/"), "manifest_sha256": sha256(SOURCE / "manifest.json"), "pairwise_negative_source": "v19_raw_teacher_report", "blind_holdout_excluded_from_train": True},
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
    preflight = {"schema_version": "aios_tag_v73_pairwise_preference_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "files": files, "parent_adapter": manifest["parent_adapter"], "rows": manifest["rows"], "planned_scope": manifest["planned_scope"], "route_contract": manifest["route_contract"], "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
