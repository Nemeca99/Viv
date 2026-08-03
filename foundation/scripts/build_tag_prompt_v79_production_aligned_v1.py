#!/usr/bin/env python3
"""Build a disjoint tag corpus with byte-equivalent production prompts.

V78 used a hand-written compact prompt that was not the prompt supplied by
the raw evaluator or the live HF-LoRA route.  V79 keeps the validated V78
rows and repaired targets, but renders every prompt through the production
packet and OpenAster renderer used at evaluation time.
"""
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

from models.Training.code import train_stage1_generation as generation  # noqa: E402
from scripts import evaluate_mouth_combined_candidate_v21 as reference  # noqa: E402
from voice_core.acronym_registry import repair_acronym_usage  # noqa: E402

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
SOURCE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v1_2_1/train_256.jsonl"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"
ACTIVE_AXES = {
    "identity_humanization",
    "architecture_cpu_gpu_role",
    "indirect_tool_agency",
    "memory_ownership_and_service_attribution",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def production_prompt(source: dict) -> str:
    packet = reference.packet(
        {"pair_id": source["pair_id"], "axis": source["axis"], "ask": source["ask"]}
    )
    return generation.render_openaster_prompt(
        packet, semantic_key=packet.get("semantic_key")
    )


def repaired_target(source: dict) -> dict:
    original = str(source.get("chosen") or source.get("target") or "")
    if source["pair_id"] in {"v121-identity_humanization-01", "v121-identity_humanization-29"}:
        original = "My name is Viv. I am an Adaptive Intelligent Operating System (AIOS), not a human person."
    repaired = repair_acronym_usage(original)
    if not repaired["pass"]:
        raise ValueError(f"unresolved_target:{source['pair_id']}:{repaired['unresolved']}")
    return repaired


def make_row(source: dict, split: str, eligible: bool) -> dict:
    repair = repaired_target(source)
    response = str(repair["repaired"])
    prompt = production_prompt(source)
    pair_id = str(source["pair_id"])
    pair_hash = hashlib.sha256(f"{pair_id}\n{prompt}\n{response}".encode("utf-8")).hexdigest()
    return {
        "schema_version": "aios_tag_v79_production_aligned_row_v1",
        "pair_id": pair_id,
        "pair_hash": pair_hash,
        "example_id": pair_id,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "split": split,
        "axis": source["axis"],
        "ask": source["ask"],
        "prompt": prompt,
        "response": response,
        "source_chosen": source.get("chosen"),
        "target_repair": repair,
        "teacher_source": "mouth_recovery_train_256_authored_registry_repaired",
        "prompt_contract": "production_reference_packet_plus_render_openaster_prompt",
        "optimizer_eligible": eligible,
        "response_only_loss_allowed": eligible,
        "hold_only": not eligible,
        "training_authorized": False,
        "run_authorized": False,
    }


def write_jsonl(path: Path, rows: list[dict]) -> dict:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    return {"path": path.name, "rows": len(rows), "sha256": sha256(path)}


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not SOURCE.is_file() or not PARENT.is_file():
        raise FileNotFoundError("v79_source_or_parent_missing")
    source_rows = [row for row in load_jsonl(SOURCE) if row.get("axis") in ACTIVE_AXES]
    eval_rows = load_jsonl(reference.EVAL_ROOT / "development_64.jsonl") + load_jsonl(reference.EVAL_ROOT / "blind_32.jsonl")
    train_ids = {row["pair_id"] for row in source_rows}
    eval_ids = {row["pair_id"] for row in eval_rows}
    if train_ids & eval_ids:
        raise ValueError("train_eval_pair_overlap")
    root.mkdir(parents=True)
    train = [make_row(row, "train", True) for row in source_rows]
    holdout = [make_row(row, "holdout", False) for row in eval_rows]
    files = {
        "train": write_jsonl(root / "train.jsonl", train),
        "development": write_jsonl(root / "development.jsonl", []),
        "holdout": write_jsonl(root / "holdout.jsonl", holdout),
    }
    manifest = {
        "schema_version": "aios_tag_v79_production_aligned_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "v78_validated_rows_exact_production_prompt",
        "route_contract": {
            "prompt": "reference.packet_plus_render_openaster_prompt",
            "evaluation_prompt_equivalence": True,
            "live_config_changed": False,
        },
        "planned_scope": {
            "optimizer_steps": 2,
            "learning_rate": 5e-9,
            "anchor_strength": 0.8,
            "contract_token_weight": 2.0,
            "contrastive_weight": 0.0,
            "pairwise_weight": 0.0,
            "promotion_authorized": False,
            "deployment_authorized": False,
        },
        "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha256(PARENT)},
        "source": {
            "train_source": str(SOURCE).replace("\\", "/"),
            "source_sha256": sha256(SOURCE),
            "active_axes": sorted(ACTIVE_AXES),
            "train_eval_pair_overlap": 0,
            "legacy_rows_excluded": True,
        },
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
    preflight = {
        "schema_version": "aios_tag_v79_production_aligned_preflight_v1",
        "status": "PREFLIGHT_PASS_TRAINING_CLOSED",
        "recorded_utc": utc(),
        "campaign_root": str(root).replace("\\", "/"),
        "manifest_sha256": sha256(manifest_path),
        "files": files,
        "parent_adapter": manifest["parent_adapter"],
        "rows": manifest["rows"],
        "route_contract": manifest["route_contract"],
        "train_eval_pair_overlap": 0,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "model_loaded": False,
        "findings": [],
        "next_action": "separate_execution_authorization",
    }
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
