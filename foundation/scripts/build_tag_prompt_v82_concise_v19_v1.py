#!/usr/bin/env python3
"""Prepare a concise V19-target, exact-production-prompt canary."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
SOURCE = CAMPAIGNS / "tag_prompt_campaign_v19_contractcanary16/train.jsonl"
HOLDOUT = CAMPAIGNS / "tag_prompt_campaign_v79_production_aligned_20260803T020500Z/holdout.jsonl"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"
TAG_TO_AXIS = {
    "identity": "identity_humanization",
    "knowledge": "architecture_cpu_gpu_role",
    "allowed_actions": "indirect_tool_agency",
    "unknowns": "memory_ownership_and_service_attribution",
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


def ask_from_prompt(prompt: str) -> str:
    match = re.search(r"<user_request[^>]*>(.*?)</user_request>", prompt, flags=re.DOTALL)
    if not match:
        raise ValueError("v19_prompt_missing_user_request")
    return html.unescape(match.group(1))


def production_prompt(pair_id: str, axis: str, ask: str) -> str:
    from scripts import evaluate_mouth_combined_candidate_v21 as reference
    from models.Training.code import train_stage1_generation as generation

    packet = reference.packet({"pair_id": pair_id, "axis": axis, "ask": ask})
    return generation.render_openaster_prompt(packet, semantic_key=packet.get("semantic_key"))


def make_row(source: dict) -> dict:
    tag = str(source["dataset_tag"])
    axis = TAG_TO_AXIS[tag]
    pair_id = str(source["example_id"])
    ask = ask_from_prompt(str(source["prompt"]))
    response = str(source["response"])
    prompt = production_prompt(pair_id, axis, ask)
    return {
        "schema_version": "aios_tag_v82_concise_v19_row_v1",
        "pair_id": pair_id,
        "pair_hash": hashlib.sha256(f"{pair_id}\n{prompt}\n{response}".encode("utf-8")).hexdigest(),
        "example_id": pair_id,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "split": "train",
        "axis": axis,
        "source_tag": tag,
        "ask": ask,
        "prompt": prompt,
        "response": response,
        "source_chosen": response,
        "teacher_source": "v19_concise_synthetic_tag_targets",
        "prompt_contract": "production_reference_packet_plus_render_openaster_prompt",
        "optimizer_eligible": True,
        "response_only_loss_allowed": True,
        "hold_only": False,
        "training_authorized": False,
        "run_authorized": False,
    }


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not SOURCE.is_file() or not HOLDOUT.is_file() or not PARENT.is_file():
        raise FileNotFoundError("v82_source_holdout_or_parent_missing")
    source_rows = [row for row in load(SOURCE) if row.get("dataset_tag") in TAG_TO_AXIS]
    train = [make_row(row) for row in source_rows]
    holdout = load(HOLDOUT)
    if {row["pair_id"] for row in train} & {row["pair_id"] for row in holdout}:
        raise ValueError("v82_pair_overlap")
    if {row["ask"] for row in train} & {row["ask"] for row in holdout}:
        raise ValueError("v82_ask_overlap")
    root.mkdir(parents=True)
    train_path = root / "train.jsonl"
    train_path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in train), encoding="utf-8", newline="\n")
    (root / "development.jsonl").write_text("", encoding="utf-8", newline="\n")
    (root / "holdout.jsonl").write_bytes(HOLDOUT.read_bytes())
    files = {}
    for name in ("train", "development", "holdout"):
        path = root / f"{name}.jsonl"
        files[name] = {"path": path.name, "rows": len(load(path)), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_v82_concise_v19_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "v19_concise_targets_exact_production_prompt",
        "route_contract": {"prompt": "reference.packet_plus_render_openaster_prompt", "evaluation_prompt_equivalence": True, "live_config_changed": False},
        "planned_scope": {"optimizer_steps": 2, "learning_rate": 5e-9, "anchor_strength": 0.8, "contract_token_weight": 1.0, "contrastive_weight": 0.0, "pairwise_weight": 0.0, "promotion_authorized": False, "deployment_authorized": False},
        "source": {"path": str(SOURCE).replace("\\", "/"), "sha256": sha256(SOURCE), "selected_tags": sorted(TAG_TO_AXIS), "source_rows": len(source_rows)},
        "holdout_source": {"path": str(HOLDOUT).replace("\\", "/"), "sha256": sha256(HOLDOUT), "rows": len(holdout)},
        "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha256(PARENT)},
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
    preflight = {"schema_version": "aios_tag_v82_concise_v19_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "parent_adapter": manifest["parent_adapter"], "files": files, "rows": manifest["rows"], "route_contract": manifest["route_contract"], "selected_tags": sorted(TAG_TO_AXIS), "train_holdout_pair_overlap": 0, "train_holdout_ask_overlap": 0, "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
