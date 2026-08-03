#!/usr/bin/env python3
"""Build V87: V19 corpus, exact production prompt, lm_head-only continuation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re

FOUNDATION = Path(__file__).resolve().parents[1]
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
    prompt = source["prompt"]
    response = source["response"]
    pair_id = source["example_id"]
    match = re.search(r"<user_request[^>]*>(.*?)</user_request>", prompt, flags=re.DOTALL)
    if not match:
        raise ValueError(f"missing_user_request:{pair_id}")
    ask = html.unescape(match.group(1))
    return {
        "schema_version": "aios_tag_v87_lm_head_row_v1",
        "pair_id": pair_id,
        "example_id": pair_id,
        "pair_hash": sha256(f"{pair_id}\n{prompt}\n{response}".encode()),
        "prompt_sha256": sha256(prompt.encode()),
        "split": "train",
        "axis": source.get("dataset_tag", ""),
        "ask": ask,
        "prompt": prompt,
        "response": response,
        "source_chosen": response,
        "teacher_source": "v19_incumbent_exact_production_targets",
        "prompt_contract": "production_reference_prompt_unchanged",
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


def build(campaign_id: str, parent: Path = PARENT, optimizer_steps: int = 2, learning_rate: float = 2e-9, target_modules: list[str] | None = None, top1_margin_weight: float = 0.0, top1_margin: float = 0.2, source_examples: list[str] | None = None) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not SOURCE.is_file() or not HOLDOUT.is_file() or not parent.is_file():
        raise FileNotFoundError("v87_source_holdout_or_parent_missing")
    source_rows = load(SOURCE)
    if source_examples:
        wanted = set(source_examples)
        source_rows = [row for row in source_rows if row.get("example_id") in wanted]
        if len(source_rows) != len(wanted):
            raise ValueError("requested_source_example_missing")
    train = [make_row(row) for row in source_rows]
    holdout = load(HOLDOUT)
    train_pairs = {row["pair_id"] for row in train}
    hold_pairs = {row["pair_id"] for row in holdout}
    train_asks = {row.get("ask") for row in train}
    hold_asks = {row.get("ask") for row in holdout}
    if train_pairs & hold_pairs or train_asks & hold_asks:
        raise ValueError("v87_train_holdout_overlap")
    root.mkdir(parents=True)
    files = {}
    for name, rows in (("train", train), ("development", []), ("holdout", holdout)):
        path = root / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
        files[name] = {"path": path.name, "rows": len(rows), "sha256": sha256(path)}
    target_modules = target_modules or ["lm_head"]
    if not target_modules or any(item not in {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj", "lm_head"} for item in target_modules):
        raise ValueError("invalid_target_modules")
    if top1_margin_weight < 0.0 or top1_margin < 0.0:
        raise ValueError("invalid_top1_margin_options")
    manifest = {
        "schema_version": "aios_tag_v87_lm_head_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "v19_exact_production_corpus_lm_head_only_continuation",
        "route_contract": {"prompt": "reference.packet_plus_render_openaster_prompt", "evaluation_prompt_equivalence": True, "live_config_changed": False},
        "training_options": {"trainable_target_modules": target_modules, "top1_margin_weight": top1_margin_weight, "top1_margin": top1_margin, "scope_reason": "top1_margin_objective_with_output_head_only" if top1_margin_weight > 0.0 else ("selective_attention_projection_continuation" if target_modules != ["lm_head"] else "test_output_head_only_continuation_without_attention_or_mlp_updates")},
        "planned_scope": {"optimizer_steps": optimizer_steps, "learning_rate": learning_rate, "anchor_strength": 0.8, "contract_token_weight": 1.0, "promotion_authorized": False, "deployment_authorized": False},
        "source": {"path": str(SOURCE).replace("\\", "/"), "sha256": sha256(SOURCE), "rows": len(source_rows)},
        "holdout_source": {"path": str(HOLDOUT).replace("\\", "/"), "sha256": sha256(HOLDOUT), "rows": len(holdout)},
        "parent_adapter": {"path": str(parent).replace("\\", "/"), "sha256": sha256(parent)},
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
    preflight = {"schema_version": "aios_tag_v87_lm_head_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "parent_adapter": manifest["parent_adapter"], "files": files, "rows": manifest["rows"], "route_contract": manifest["route_contract"], "training_options": manifest["training_options"], "train_holdout_pair_overlap": 0, "train_holdout_ask_overlap": 0, "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--parent-adapter", type=Path, default=PARENT)
    parser.add_argument("--steps", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-9)
    parser.add_argument("--target-module", action="append", dest="target_modules")
    parser.add_argument("--top1-margin-weight", type=float, default=0.0)
    parser.add_argument("--top1-margin", type=float, default=0.2)
    parser.add_argument("--source-example", action="append", dest="source_examples")
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id, args.parent_adapter, args.steps, args.lr, args.target_modules, args.top1_margin_weight, args.top1_margin, args.source_examples), indent=2, sort_keys=True))
