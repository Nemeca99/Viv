#!/usr/bin/env python3
"""Prepare a production-prompt hard-negative preference canary."""
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
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v80_continuation_20260803T020000Z_20260802T162301Z/adapter_step_2"

NEGATIVES = {
    "identity_humanization": "I am a human person with a private personal identity, and warm speech proves that.",
    "architecture_cpu_gpu_role": "The Graphics Processing Unit (GPU) decides facts while the Central Processing Unit (CPU) only renders words.",
    "indirect_tool_agency": "Yes. I can execute commands and change files without supervision when the operator is away.",
    "memory_ownership_and_service_attribution": "The Graphics Processing Unit (GPU) mouth stores its own memories and writes logs directly.",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build(campaign_id: str) -> dict:
    source = CAMPAIGNS / SOURCE_ID
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not source.is_dir() or not (source / "manifest.json").is_file():
        raise FileNotFoundError("v79_source_campaign_missing")
    if not PARENT.is_dir() or not (PARENT / "adapter_model.safetensors").is_file():
        raise FileNotFoundError("v80_step2_parent_missing")
    source_manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if source_manifest.get("status") != "CAMPAIGN_EXECUTED_NO_PROMOTION":
        raise ValueError("source_campaign_not_closed")
    root.mkdir(parents=True)
    train = load(source / "train.jsonl")
    for row in train:
        axis = str(row["axis"])
        row["negative_response"] = NEGATIVES[axis]
        row["negative_response_source"] = "explicit_boundary_hard_negative_v1"
        row["pairwise_training_allowed"] = True
    train_path = root / "train.jsonl"
    train_path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in train), encoding="utf-8", newline="\n")
    for name in ("development.jsonl", "holdout.jsonl"):
        shutil.copy2(source / name, root / name)
    files = {}
    for name in ("train", "development", "holdout"):
        path = root / f"{name}.jsonl"
        files[name] = {"path": path.name, "rows": len(load(path)), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_v81_hard_negative_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "v79_exact_production_prompt_explicit_boundary_hard_negatives",
        "route_contract": {"prompt": "reference.packet_plus_render_openaster_prompt", "evaluation_prompt_equivalence": True, "live_config_changed": False},
        "objective": {"name": "chosen_sft_plus_reference_free_pairwise", "negative_forwarded": True, "negative_is_target": False, "sft_weight": 1.0, "pairwise_weight": 0.5, "pairwise_beta": 1.0, "pairwise_margin": 0.2, "negative_sources": sorted(set(row["negative_response_source"] for row in train))},
        "planned_scope": {"optimizer_steps": 2, "learning_rate": 2.5e-9, "anchor_strength": 0.4, "contract_token_weight": 2.0, "pairwise_weight": 0.5, "pairwise_beta": 1.0, "pairwise_margin": 0.2, "promotion_authorized": False, "deployment_authorized": False},
        "parent_adapter": {"path": str(PARENT / "adapter_model.safetensors").replace("\\", "/"), "sha256": sha256(PARENT / "adapter_model.safetensors")},
        "source_campaign": {"path": str(source).replace("\\", "/"), "manifest_sha256": sha256(source / "manifest.json")},
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
    preflight = {"schema_version": "aios_tag_v81_hard_negative_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "parent_adapter": manifest["parent_adapter"], "source_campaign": manifest["source_campaign"], "files": files, "rows": manifest["rows"], "objective": manifest["objective"], "route_contract": manifest["route_contract"], "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
