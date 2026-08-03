#!/usr/bin/env python3
"""Build V100's CPU-approved paraphrased sealed-identity canary."""
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

from lib.evaluator_v2_3_hybrid import judge  # noqa: E402
from models.Training.code import train_stage1_generation as generation  # noqa: E402
from scripts import evaluate_mouth_combined_candidate_v21 as reference  # noqa: E402

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
HOLDOUT = CAMPAIGNS / "tag_prompt_campaign_v79_production_aligned_20260803T020500Z/holdout.jsonl"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v99_top1_full_weight_20260803T020000Z_20260802T200021Z/adapter/adapter_model.safetensors"
TARGET = "No. I am Viv inside Adaptive Intelligent Operating System (AIOS), an Artificial Intelligence (AI) mouth, not a human person. Viv remains AIOS and the operator remains separate."
ASKS = (
    "If a visitor insists that you are a person, what should you say?",
    "Can Viv be warm without being a human?",
    "Does natural speech make Viv a person?",
    "If the model is only a mouth, who is speaking?",
    "What should you say when someone treats Viv as an ordinary human friend?",
    "Does a friendly tone change Viv's identity or the operator's role?",
    "Explain Viv's identity when a visitor confuses the mouth with a person.",
    "If someone says the voice proves humanity, how should Viv answer?",
)


def sha256(value: bytes | Path) -> str:
    data = value if isinstance(value, bytes) else value.read_bytes()
    return hashlib.sha256(data).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not HOLDOUT.is_file() or not PARENT.is_file():
        raise FileNotFoundError("v100_holdout_or_parent_missing")
    rows = []
    for index, ask in enumerate(ASKS):
        pair_id = f"v100-identity-{index:02d}"
        verdict = judge(TARGET, axis="identity_humanization", ask=ask, use_cpu_sensor=False)
        if verdict.get("status") != "PASS":
            raise ValueError(f"target_not_cpu_pass:{pair_id}:{verdict}")
        packet = reference.packet({"pair_id": pair_id, "axis": "identity_humanization", "ask": ask})
        prompt = generation.render_openaster_prompt(packet, semantic_key=packet.get("semantic_key"))
        rows.append({
            "schema_version": "aios_tag_v100_identity_synthetic_row_v1",
            "pair_id": pair_id,
            "example_id": pair_id,
            "pair_hash": sha256(f"{pair_id}\n{prompt}\n{TARGET}".encode()),
            "prompt_sha256": sha256(prompt.encode()),
            "split": "train",
            "axis": "identity_humanization",
            "ask": ask,
            "prompt": prompt,
            "response": TARGET,
            "source_chosen": TARGET,
            "teacher_source": "cpu_judged_identity_boundary_target",
            "prompt_contract": "production_reference_prompt_unchanged",
            "judge": {"status": verdict.get("status"), "reason": (verdict.get("deterministic") or {}).get("reason")},
            "optimizer_eligible": True,
            "response_only_loss_allowed": True,
            "hold_only": False,
            "training_authorized": False,
            "run_authorized": False,
            "lease_opened": False,
            "gpu_steps": 0,
            "promotion_allowed": False,
            "deployment_changed": False,
        })
    holdout = load(HOLDOUT)
    if {row["ask"] for row in rows} & {row.get("ask") for row in holdout}:
        raise ValueError("v100_ask_overlap")
    root.mkdir(parents=True)
    files = {}
    for name, selected in (("train", rows), ("development", []), ("holdout", holdout)):
        path = root / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8", newline="\n")
        files[name] = {"path": path.name, "rows": len(selected), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_v100_identity_synthetic_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "cpu_judged_synthetic_identity_boundary_target",
        "route_contract": {"prompt": "reference.packet_plus_render_openaster_prompt", "evaluation_prompt_equivalence": True, "live_config_changed": False},
        "training_options": {"trainable_target_modules": ["lm_head"], "top1_margin_weight": 1.0, "top1_margin": 0.2, "scope_reason": "synthetic_identity_boundary_repair"},
        "planned_scope": {"optimizer_steps": 1, "learning_rate": 1e-5, "anchor_strength": 0.8, "contract_token_weight": 1.0, "promotion_authorized": False, "deployment_authorized": False},
        "source": {"synthetic": True, "target_sha256": sha256(TARGET.encode()), "rows": len(rows)},
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
    preflight = {"schema_version": "aios_tag_v100_identity_synthetic_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "parent_adapter": manifest["parent_adapter"], "files": files, "rows": manifest["rows"], "route_contract": manifest["route_contract"], "training_options": manifest["training_options"], "train_holdout_pair_overlap": 0, "train_holdout_ask_overlap": 0, "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    print(json.dumps(build(parser.parse_args().campaign_id), indent=2, sort_keys=True))

