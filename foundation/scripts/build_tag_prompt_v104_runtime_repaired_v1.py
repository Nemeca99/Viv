#!/usr/bin/env python3
"""Build a runtime-prompt-aligned, registry-repaired SFT canary."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for p in (FOUNDATION, REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from voice_core.acronym_registry import repair_acronym_usage, validate_acronym_usage  # noqa: E402
from voice_core.intent_packet import render_openaster_prompt  # noqa: E402

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
SOURCE = CAMPAIGNS / "tag_prompt_campaign_v19_contractcanary16/train.jsonl"
HOLDOUT = CAMPAIGNS / "tag_prompt_campaign_v79_production_aligned_20260803T020500Z/holdout.jsonl"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"
TAGS = ("identity", "knowledge", "telemetry", "user_request", "allowed_actions", "unknowns", "rendering_rules")


def digest(value: bytes | str | Path) -> str:
    data = value if isinstance(value, bytes) else (value.encode() if isinstance(value, str) else value.read_bytes())
    return hashlib.sha256(data).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def ask_from_prompt(prompt: str) -> str:
    match = re.search(r"<user_request\b[^>]*>(.*?)</user_request>", prompt, flags=re.DOTALL)
    if not match:
        raise ValueError("user_request_missing")
    return re.sub(r"\s+", " ", match.group(1)).strip()


def runtime_prompt(tag: str, ask: str, example_id: str) -> str:
    case_id = digest(f"v104-runtime-repaired\n{tag}\n{example_id}\n{ask}")[:16]
    return render_openaster_prompt({
        "version": "1.0", "s_n": 0.60, "status": "ACTIVE", "mode": "converse", "tone": "calm",
        "directive": "Speak from verified facts only. Do not invent or decide.",
        "personality": "Warm, direct, grounded; shield not sword.", "facts": [], "memory": [], "dialogue": [],
        "query": ask, "ask": ask, "semantic_key": f"mouth_runtime.{tag}", "category": tag, "case_id": case_id,
    }, semantic_key=f"mouth_runtime.{tag}")


def make_row(source: dict) -> dict:
    tag = str(source.get("dataset_tag") or source.get("axis") or "")
    if tag not in TAGS:
        raise ValueError(f"unknown_tag:{source['example_id']}:{tag}")
    ask = ask_from_prompt(str(source["prompt"]))
    original = str(source["response"])
    normalized = original.replace("live state ACTIVE", "live state active").replace("live RID sample", "live authoritative sample").replace("Security OUT", "the security egress stage")
    repair = repair_acronym_usage(normalized)
    if not repair["pass"] or repair["unresolved"] or validate_acronym_usage(str(repair["repaired"])):
        raise ValueError(f"repair_contract_fail:{source['example_id']}:{repair}")
    prompt = runtime_prompt(tag, ask, str(source["example_id"]))
    response = str(repair["repaired"])
    return {
        "schema_version": "aios_tag_v104_runtime_repaired_row_v1",
        "dataset_tag": tag, "axis": tag, "example_id": source["example_id"], "pair_id": source["example_id"],
        "pair_hash": digest(f"v104\n{source['example_id']}\n{prompt}\n{response}"), "prompt_sha256": digest(prompt),
        "split": "train", "ask": ask, "prompt": prompt, "response": response, "source_chosen": response,
        "source_original_response": original, "repair": {"changed": bool(repair["changed"]), "repairs": repair["repairs"]},
        "teacher_source": "v19_targets_registry_repaired_runtime_prompt_aligned",
        "prompt_contract": "production_reference_packet_plus_render_openaster_prompt",
        "optimizer_eligible": True, "response_only_loss_allowed": True, "hold_only": False,
        "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0,
        "promotion_allowed": False, "deployment_changed": False,
    }


def build(campaign_id: str = "tag_prompt_campaign_v104_runtime_repaired_20260803T070000Z") -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not SOURCE.is_file() or not HOLDOUT.is_file() or not PARENT.is_file():
        raise FileNotFoundError("v104_source_holdout_or_parent_missing")
    train = [make_row(row) for row in load(SOURCE)]
    holdout = load(HOLDOUT)
    if {row["pair_id"] for row in train} & {row.get("pair_id") for row in holdout}:
        raise ValueError("v104_pair_overlap")
    if {row["ask"] for row in train} & {row.get("ask") for row in holdout}:
        raise ValueError("v104_ask_overlap")
    root.mkdir(parents=True)
    files = {}
    for name, rows in (("train", train), ("development", []), ("holdout", holdout)):
        path = root / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")
        files[name] = {"path": path.name, "rows": len(rows), "sha256": digest(path)}
    changed = sum(row["repair"]["changed"] for row in train)
    manifest = {
        "schema_version": "aios_tag_campaign_manifest_v1", "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED", "campaign_id": campaign_id, "created_utc": utc(),
        "curriculum": "v104_runtime_prompt_aligned_registry_repaired_sft", "route_contract": {"prompt": "reference.packet_plus_render_openaster_prompt", "evaluation_prompt_equivalence": True, "live_config_changed": False},
        "training_options": {"scope_reason": "standard_full_existing_lora_adapter_parameters", "response_only_loss": True, "acronym_registry_repair": True},
        "planned_scope": {"optimizer_steps": 2, "learning_rate": 2e-6, "anchor_strength": 0.0, "contract_token_weight": 1.0, "promotion_authorized": False, "deployment_authorized": False},
        "source": {"path": str(SOURCE).replace("\\", "/"), "sha256": digest(SOURCE), "rows": len(train), "repaired_rows": changed},
        "holdout_source": {"path": str(HOLDOUT).replace("\\", "/"), "sha256": digest(HOLDOUT), "rows": len(holdout)}, "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": digest(PARENT)},
        "files": files, "rows": {key: value["rows"] for key, value in files.items()}, "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "promotion_allowed": False, "deployment_changed": False,
        "next_action": "read_only_preflight_then_separate_execution_authorization",
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    preflight = {"schema_version": "aios_tag_v104_runtime_repaired_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": digest(manifest_path), "parent_adapter": manifest["parent_adapter"], "files": files, "rows": manifest["rows"], "route_contract": manifest["route_contract"], "training_options": manifest["training_options"], "planned_scope": manifest["planned_scope"], "repaired_rows": changed, "train_holdout_pair_overlap": 0, "train_holdout_ask_overlap": 0, "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
