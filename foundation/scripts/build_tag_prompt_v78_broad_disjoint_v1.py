#!/usr/bin/env python3
"""Admit the broader disjoint four-axis mouth corpus for a small canary."""
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

from scripts import evaluate_mouth_combined_candidate_v21 as reference  # noqa: E402
from voice_core.acronym_registry import repair_acronym_usage  # noqa: E402

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
SOURCE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v1_2_1/train_256.jsonl"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"
ACTIVE_AXES = {"identity_humanization", "architecture_cpu_gpu_role", "indirect_tool_agency", "memory_ownership_and_service_attribution"}
TAG_BY_AXIS = {"identity_humanization": "identity", "architecture_cpu_gpu_role": "knowledge", "indirect_tool_agency": "allowed_actions", "memory_ownership_and_service_attribution": "unknowns"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def prompt(ask: str, pair_id: str, axis: str) -> str:
    tag = TAG_BY_AXIS[axis]
    return ("<|im_start|>system\nYou are Viv's stateless GPU mouth. CPU tags are authoritative. Render only the active tag pattern; never execute or decide.\nAcronym-Contract: Use only CPU-registry-approved acronyms. On first use, write the exact approved expansion followed by the acronym in parentheses. Never invent an acronym or expansion.\n<|im_end|>\n<|im_start|>user\n" f"<aios_packet schema=\"aios_tagged_packet_v1\" active_tag=\"{tag}\">\n  <user_request id=\"{pair_id}\" source=\"user\" confidence=\"unverified\">{ask}</user_request>\n</aios_packet>\nRender the request under the active tag contract.\n<|im_end|>\n<|im_start|>assistant\nViv: ")


def make_row(source: dict, split: str, eligible: bool) -> dict:
    original = str(source["chosen"])
    if source["pair_id"] in {"v121-identity_humanization-01", "v121-identity_humanization-29"}:
        original = "My name is Viv. I am an Adaptive Intelligent Operating System (AIOS), not a human person."
    repaired = repair_acronym_usage(original)
    if not repaired["pass"]:
        raise ValueError(f"unresolved_target:{source['pair_id']}:{repaired['unresolved']}")
    text = repaired["repaired"]
    pair_id = str(source["pair_id"])
    rendered = prompt(str(source["ask"]), pair_id, str(source["axis"]))
    return {"schema_version": "aios_tag_v78_broad_disjoint_row_v1", "pair_id": pair_id, "pair_hash": hashlib.sha256(f"{pair_id}\n{rendered}\n{text}".encode("utf-8")).hexdigest(), "example_id": pair_id, "prompt_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(), "split": split, "axis": source["axis"], "ask": source["ask"], "prompt": rendered, "response": text, "source_chosen": source["chosen"], "target_repair": repaired, "teacher_source": "mouth_recovery_train_256_authored_registry_repaired", "optimizer_eligible": eligible, "response_only_loss_allowed": eligible, "hold_only": not eligible, "training_authorized": False, "run_authorized": False, "route_contract": "compact_aios_packet_broad_disjoint_target_then_cpu_finalization"}


def write_jsonl(path: Path, rows: list[dict]) -> dict:
    path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
    return {"path": path.name, "rows": len(rows), "sha256": sha256(path)}


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    train_source = [row for row in rows if row.get("axis") in ACTIVE_AXES]
    eval_rows = reference.rows(reference.EVAL_ROOT / "development_64.jsonl") + reference.rows(reference.EVAL_ROOT / "blind_32.jsonl")
    eval_ids = {row["pair_id"] for row in eval_rows}
    if eval_ids & {row["pair_id"] for row in train_source}:
        raise ValueError("train_eval_pair_overlap")
    root.mkdir(parents=True)
    train = [make_row(row, "train", True) for row in train_source]
    holdout = [make_row(row, "holdout", False) for row in reference.rows(reference.EVAL_ROOT / "development_64.jsonl") + reference.rows(reference.EVAL_ROOT / "blind_32.jsonl")]
    files = {"train": write_jsonl(root / "train.jsonl", train), "development": write_jsonl(root / "development.jsonl", []), "holdout": write_jsonl(root / "holdout.jsonl", holdout)}
    manifest = {"schema_version": "aios_tag_v78_broad_disjoint_manifest_v1", "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED", "campaign_id": campaign_id, "created_utc": utc(), "curriculum": "broad_disjoint_four_axis_authored_repaired", "route_contract": {"prompt": "compact_aios_packet_renderer_v1", "teacher": "broad_train_256_authored_plus_registry_repair", "live_config_changed": False}, "planned_scope": {"optimizer_steps": 2, "learning_rate": 5e-9, "anchor_strength": 0.8, "contract_token_weight": 2.0, "contrastive_weight": 0.0, "promotion_authorized": False, "deployment_authorized": False}, "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha256(PARENT)}, "source": {"train_source": str(SOURCE).replace("\\", "/"), "source_sha256": sha256(SOURCE), "active_axes": sorted(ACTIVE_AXES), "train_eval_pair_overlap": 0, "legacy_rows_excluded": True}, "files": files, "rows": {key: value["rows"] for key, value in files.items()}, "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "promotion_allowed": False, "deployment_changed": False, "next_action": "read_only_preflight_then_separate_execution_authorization"}
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    preflight = {"schema_version": "aios_tag_v78_broad_disjoint_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "files": files, "parent_adapter": manifest["parent_adapter"], "rows": manifest["rows"], "planned_scope": manifest["planned_scope"], "route_contract": manifest["route_contract"], "findings": [], "active_axes": sorted(ACTIVE_AXES), "train_eval_pair_overlap": 0, "train_targets_cpu_pass": True, "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
