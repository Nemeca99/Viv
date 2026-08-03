#!/usr/bin/env python3
"""Admit a route-aware 16-step canary from the disjoint v65 corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
V65 = CAMPAIGNS / "tag_prompt_campaign_v65_runtime_aligned_general"
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
    if not V65.is_dir() or not V19.is_dir() or not PARENT.is_file():
        raise FileNotFoundError("source_or_parent_missing")
    root.mkdir(parents=True)
    files = {}
    for split in ("train", "development", "holdout"):
        source = V65 / f"{split}.jsonl"
        rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            row["schema_version"] = "aios_tag_v68_route_aware_row_v1"
            row["route_contract"] = "hf_lora_shadow_then_cpu_finalize"
        path = root / f"{split}.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
        files[split] = {"path": path.name, "rows": len(rows), "sha256": sha256(path), "source_sha256": sha256(source)}
    manifest = {
        "schema_version": "aios_tag_v68_route_aware_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "route_aware_runtime_aligned_general_16step",
        "route_contract": {"generation": "hf_lora_explicit_adapter_path", "finalization": "voice_core.runtime_contract.finalize_draft", "live_config_changed": False},
        "planned_scope": {"optimizer_steps": 16, "learning_rate": 1e-8, "anchor_strength": 0.8, "contrastive_weight": 0.0, "promotion_authorized": False, "deployment_authorized": False},
        "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha256(PARENT)},
        "source": {"campaign": str(V65).replace("\\", "/"), "manifest_sha256": sha256(V65 / "manifest.json"), "v19_manifest_sha256": sha256(V19 / "manifest.json"), "disjoint_from_v19": True},
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
    preflight = {"schema_version": "aios_tag_v68_route_aware_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "files": files, "parent_adapter": manifest["parent_adapter"], "rows": manifest["rows"], "planned_scope": manifest["planned_scope"], "route_contract": manifest["route_contract"], "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
