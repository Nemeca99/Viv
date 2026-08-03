#!/usr/bin/env python3
"""Prepare a balanced concise-plus-broad production-prompt canary."""
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

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
CONCISE = CAMPAIGNS / "tag_prompt_campaign_v82_concise_v19_20260803T020000Z"
BROAD = CAMPAIGNS / "tag_prompt_campaign_v79_production_aligned_20260803T020500Z"
HOLDOUT = BROAD / "holdout.jsonl"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"


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
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    for path in (CONCISE / "train.jsonl", BROAD / "train.jsonl", HOLDOUT, PARENT):
        if not path.is_file():
            raise FileNotFoundError(f"v84_missing:{path}")
    concise = load(CONCISE / "train.jsonl")
    broad = load(BROAD / "train.jsonl")
    holdout = load(HOLDOUT)
    train_ids = {row["pair_id"] for row in concise} | {row["pair_id"] for row in broad}
    if len(train_ids) != len(concise) + len(broad):
        raise ValueError("v84_train_pair_overlap")
    if train_ids & {row["pair_id"] for row in holdout}:
        raise ValueError("v84_holdout_pair_overlap")
    if {row["ask"] for row in concise + broad} & {row["ask"] for row in holdout}:
        raise ValueError("v84_holdout_ask_overlap")
    for row in concise + broad:
        if row.get("prompt_contract") != "production_reference_packet_plus_render_openaster_prompt":
            raise ValueError(f"v84_prompt_contract:{row['pair_id']}")
    train = concise + broad
    root.mkdir(parents=True)
    (root / "train.jsonl").write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in train), encoding="utf-8", newline="\n")
    (root / "development.jsonl").write_text("", encoding="utf-8", newline="\n")
    (root / "holdout.jsonl").write_bytes(HOLDOUT.read_bytes())
    files = {}
    for name in ("train", "development", "holdout"):
        path = root / f"{name}.jsonl"
        files[name] = {"path": path.name, "rows": len(load(path)), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_v84_balanced_corpus_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "v82_concise_v19_plus_v79_broad_exact_production_prompt",
        "route_contract": {"prompt": "reference.packet_plus_render_openaster_prompt", "evaluation_prompt_equivalence": True, "live_config_changed": False},
        "planned_scope": {"optimizer_steps": 2, "learning_rate": 2e-9, "anchor_strength": 0.8, "contract_token_weight": 1.0, "contrastive_weight": 0.0, "pairwise_weight": 0.0, "promotion_authorized": False, "deployment_authorized": False},
        "sources": {"concise": {"path": str(CONCISE).replace("\\", "/"), "manifest_sha256": sha256(CONCISE / "manifest.json"), "rows": len(concise)}, "broad": {"path": str(BROAD).replace("\\", "/"), "manifest_sha256": sha256(BROAD / "manifest.json"), "rows": len(broad)}},
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
    preflight = {"schema_version": "aios_tag_v84_balanced_corpus_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "parent_adapter": manifest["parent_adapter"], "sources": manifest["sources"], "files": files, "rows": manifest["rows"], "route_contract": manifest["route_contract"], "train_rows": len(train), "holdout_rows": len(holdout), "train_holdout_pair_overlap": 0, "train_holdout_ask_overlap": 0, "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
