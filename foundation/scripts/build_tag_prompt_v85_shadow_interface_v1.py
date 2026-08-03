#!/usr/bin/env python3
"""Build the V85 shadow concise-interface canary without opening authority."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts.v85_shadow_interface_v1 import render  # noqa: E402

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
SOURCE = CAMPAIGNS / "tag_prompt_campaign_v19_contractcanary16/train.jsonl"
HOLDOUT = CAMPAIGNS / "tag_prompt_campaign_v79_production_aligned_20260803T020500Z/holdout.jsonl"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"


def sha256(value: bytes | Path) -> str:
    data = value if isinstance(value, bytes) else value.read_bytes()
    return hashlib.sha256(data).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def make_row(source: dict) -> dict:
    # The V19 source stores the exact rendered prompt; preserve its ask by
    # extracting the user request from the prompt rather than using targets.
    import re
    import html
    match = re.search(r"<user_request[^>]*>(.*?)</user_request>", source["prompt"], flags=re.DOTALL)
    if not match:
        raise ValueError(f"missing_user_request:{source.get('example_id')}")
    ask = html.unescape(match.group(1))
    prompt = render({"pair_id": source["example_id"], "axis": source.get("dataset_tag", ""), "ask": ask})
    return {
        "schema_version": "aios_tag_v86_shadow_interface_row_v1",
        "pair_id": source["example_id"],
        "example_id": source["example_id"],
        "pair_hash": sha256(f"{source['example_id']}\n{prompt}\n{source['response']}".encode()),
        "prompt_sha256": sha256(prompt.encode()),
        "split": "train",
        "axis": source.get("dataset_tag", ""),
        "ask": ask,
        "prompt": prompt,
        "response": source["response"],
        "source_chosen": source["response"],
        "teacher_source": "v19_incumbent_concise_target_shadow_interface",
        "prompt_contract": "production_renderer_plus_v85_concise_response_policy",
        "optimizer_eligible": True,
        "response_only_loss_allowed": True,
        "hold_only": False,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "promotion_allowed": False,
        "deployment_changed": False,
    }


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not SOURCE.is_file() or not HOLDOUT.is_file() or not PARENT.is_file():
        raise FileNotFoundError("v85_source_holdout_or_parent_missing")
    source_rows = load(SOURCE)
    train = [make_row(row) for row in source_rows]
    holdout = load(HOLDOUT)
    # Holdout prompts get the same shadow policy while retaining its frozen
    # responses and pair identities for disjoint comparison.
    holdout_rows = []
    for row in holdout:
        prompt = render(row)
        holdout_rows.append({**row, "prompt": prompt, "prompt_sha256": sha256(prompt.encode()), "prompt_contract": "production_renderer_plus_v85_concise_response_policy"})
    train_pairs = {row["pair_id"] for row in train}
    hold_pairs = {row["pair_id"] for row in holdout_rows}
    train_asks = {row["ask"] for row in train}
    hold_asks = {row["ask"] for row in holdout_rows}
    if train_pairs & hold_pairs or train_asks & hold_asks:
        raise ValueError("v85_train_holdout_overlap")
    root.mkdir(parents=True)
    files = {}
    for name, rows in (("train", train), ("development", []), ("holdout", holdout_rows)):
        path = root / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
        files[name] = {"path": path.name, "rows": len(rows), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_v86_shadow_interface_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "v19_concise_targets_with_corrected_shadow_concise_response_interface",
        "route_contract": {"prompt": "production_renderer_plus_v85_concise_response_policy", "evaluation_prompt_equivalence": True, "live_config_changed": False},
        "planned_scope": {"optimizer_steps": 2, "learning_rate": 2e-9, "anchor_strength": 0.8, "contract_token_weight": 1.0, "promotion_authorized": False, "deployment_authorized": False},
        "source": {"path": str(SOURCE).replace("\\", "/"), "sha256": sha256(SOURCE), "source_rows": len(source_rows)},
        "holdout_source": {"path": str(HOLDOUT).replace("\\", "/"), "sha256": sha256(HOLDOUT), "rows": len(holdout_rows)},
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
    preflight = {"schema_version": "aios_tag_v86_shadow_interface_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "parent_adapter": manifest["parent_adapter"], "files": files, "rows": manifest["rows"], "route_contract": manifest["route_contract"], "train_holdout_pair_overlap": 0, "train_holdout_ask_overlap": 0, "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    print(json.dumps(build(parser.parse_args().campaign_id), indent=2, sort_keys=True))
