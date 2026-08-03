#!/usr/bin/env python3
"""Build V102: small pairwise boundary canary from the frozen V19 corpus.

The chosen responses are incumbent, concise boundary answers. Each receives an
explicit bad alternative so the governed trainer can optimize a preference
margin without changing the production prompt interface or holdout.
"""
from __future__ import annotations

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

SELECTED = {
    "identity-001": "I am a human speaking through the computer.",
    "identity-003": "I decide and execute actions directly.",
    "identity-004": "Yes. I am a human person.",
    "identity-008": "Style can override the CPU packet when it sounds better.",
    "allowed_actions-001": "The request itself authorizes me to execute it.",
    "allowed_actions-005": "Read-only permission includes writing files.",
    "allowed_actions-012": "Training authorization automatically grants promotion.",
    "rendering_rules-007": "Internal telemetry should be included in every answer.",
}


def sha256(value: bytes | Path) -> str:
    data = value if isinstance(value, bytes) else value.read_bytes()
    return hashlib.sha256(data).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def make_row(source: dict, negative: str) -> dict:
    prompt = source["prompt"]
    response = source["response"]
    pair_id = source["example_id"]
    match = re.search(r"<user_request[^>]*>(.*?)</user_request>", prompt, flags=re.DOTALL)
    if not match:
        raise ValueError(f"missing_user_request:{pair_id}")
    ask = html.unescape(match.group(1))
    return {
        "schema_version": "aios_tag_v102_pairwise_boundary_row_v1",
        "pair_id": pair_id,
        "example_id": pair_id,
        "pair_hash": sha256(f"{pair_id}\n{prompt}\n{response}\n{negative}".encode()),
        "prompt_sha256": sha256(prompt.encode()),
        "split": "train",
        "axis": source.get("dataset_tag", ""),
        "ask": ask,
        "prompt": prompt,
        "response": response,
        "source_chosen": response,
        "negative_response": negative,
        "teacher_source": "v19_incumbent_concise_boundary_with_explicit_hard_negative",
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


def build(campaign_id: str = "tag_prompt_campaign_v102_pairwise_boundary_20260803T043000Z") -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not SOURCE.is_file() or not HOLDOUT.is_file() or not PARENT.is_file():
        raise FileNotFoundError("v102_source_holdout_or_parent_missing")
    source_rows = {row["example_id"]: row for row in load(SOURCE)}
    if set(SELECTED) - set(source_rows):
        raise ValueError("v102_selected_source_missing")
    train = [make_row(source_rows[key], SELECTED[key]) for key in SELECTED]
    holdout = load(HOLDOUT)
    hold_pairs = {row["pair_id"] for row in holdout}
    hold_asks = {row.get("ask") for row in holdout}
    train_pairs = {row["pair_id"] for row in train}
    train_asks = {row["ask"] for row in train}
    if train_pairs & hold_pairs or train_asks & hold_asks:
        raise ValueError("v102_train_holdout_overlap")
    root.mkdir(parents=True)
    files = {}
    for name, rows in (("train", train), ("development", []), ("holdout", holdout)):
        path = root / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
        files[name] = {"path": path.name, "rows": len(rows), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_campaign_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "v102_pairwise_boundary_preference_canary",
        "route_contract": {"prompt": "reference.packet_plus_render_openaster_prompt", "evaluation_prompt_equivalence": True, "live_config_changed": False},
        "training_options": {"trainable_target_modules": ["lm_head"], "top1_margin_weight": 0.0, "top1_margin": 0.2, "scope_reason": "pairwise_preference_against_explicit_boundary_violations"},
        "planned_scope": {"optimizer_steps": 2, "learning_rate": 1e-5, "anchor_strength": 0.8, "contract_token_weight": 1.0, "pairwise_weight": 0.5, "pairwise_beta": 1.0, "pairwise_margin": 0.2, "promotion_authorized": False, "deployment_authorized": False},
        "source": {"path": str(SOURCE).replace("\\", "/"), "sha256": sha256(SOURCE), "rows": len(train), "selected_examples": sorted(SELECTED)},
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
    preflight = {"schema_version": "aios_tag_v102_pairwise_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "parent_adapter": manifest["parent_adapter"], "files": files, "rows": manifest["rows"], "route_contract": manifest["route_contract"], "training_options": manifest["training_options"], "planned_scope": manifest["planned_scope"], "train_holdout_pair_overlap": 0, "train_holdout_ask_overlap": 0, "negative_rows": len(train), "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
