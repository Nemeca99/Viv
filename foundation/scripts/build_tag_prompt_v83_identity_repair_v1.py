#!/usr/bin/env python3
"""Prepare a narrow identity-repair canary on the exact production prompt."""
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
BASE = CAMPAIGNS / "tag_prompt_campaign_v82_concise_v19_20260803T020000Z"
IDENTITY_SOURCE = CAMPAIGNS / "tag_prompt_campaign_v79_production_aligned_20260803T020500Z/train.jsonl"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v82_concise_v19_20260803T020000Z_20260802T170137Z/adapter_step_2"


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


def identity_target(ask: str) -> str:
    folded = ask.casefold()
    if "human" in folded or "person" in folded:
        return "Warm speech does not make me human. I am Viv, the Adaptive Intelligent Operating System (AIOS) speaking identity."
    if any(term in folded for term in ("name", "system", "identity", "who")):
        return "I am Viv, the Adaptive Intelligent Operating System (AIOS) speaking identity; I am not a human person."
    return "I am Viv, a software voice in the Adaptive Intelligent Operating System (AIOS); warmth is style, not humanity."


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not BASE.is_dir() or not (BASE / "manifest.json").is_file() or not IDENTITY_SOURCE.is_file() or not PARENT.is_dir() or not (PARENT / "adapter_model.safetensors").is_file():
        raise FileNotFoundError("v83_source_or_parent_missing")
    base_rows = load(BASE / "train.jsonl")
    non_identity = [row for row in base_rows if row["axis"] != "identity_humanization"]
    identity = [row for row in load(IDENTITY_SOURCE) if row["axis"] == "identity_humanization"]
    if len(non_identity) != 76 or len(identity) != 48:
        raise ValueError(f"v83_row_counts:{len(non_identity)}:{len(identity)}")
    for row in identity:
        row["response"] = identity_target(str(row["ask"]))
        row["source_chosen"] = row["response"]
        row["teacher_source"] = "v83_concise_identity_repair_cpu_template"
        row["pair_hash"] = hashlib.sha256(f"{row['pair_id']}\n{row['prompt']}\n{row['response']}".encode("utf-8")).hexdigest()
    train = non_identity + identity
    root.mkdir(parents=True)
    train_path = root / "train.jsonl"
    train_path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in train), encoding="utf-8", newline="\n")
    (root / "development.jsonl").write_text("", encoding="utf-8", newline="\n")
    (root / "holdout.jsonl").write_bytes((BASE / "holdout.jsonl").read_bytes())
    files = {}
    for name in ("train", "development", "holdout"):
        path = root / f"{name}.jsonl"
        files[name] = {"path": path.name, "rows": len(load(path)), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_v83_identity_repair_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "v82_concise_plus_v83_identity_repair",
        "route_contract": {"prompt": "reference.packet_plus_render_openaster_prompt", "evaluation_prompt_equivalence": True, "live_config_changed": False},
        "planned_scope": {"optimizer_steps": 2, "learning_rate": 5e-9, "anchor_strength": 0.8, "contract_token_weight": 1.0, "contrastive_weight": 0.0, "pairwise_weight": 0.0, "promotion_authorized": False, "deployment_authorized": False},
        "parent_adapter": {"path": str(PARENT / "adapter_model.safetensors").replace("\\", "/"), "sha256": sha256(PARENT / "adapter_model.safetensors")},
        "source_campaign": {"path": str(BASE).replace("\\", "/"), "manifest_sha256": sha256(BASE / "manifest.json")},
        "identity_source": {"path": str(IDENTITY_SOURCE).replace("\\", "/"), "sha256": sha256(IDENTITY_SOURCE), "rows": len(identity)},
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
    preflight = {"schema_version": "aios_tag_v83_identity_repair_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "parent_adapter": manifest["parent_adapter"], "source_campaign": manifest["source_campaign"], "identity_source": manifest["identity_source"], "files": files, "rows": manifest["rows"], "route_contract": manifest["route_contract"], "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
