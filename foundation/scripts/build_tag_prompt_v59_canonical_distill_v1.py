#!/usr/bin/env python3
"""Build a dual-format corpus with low-entropy canonical mouth targets."""
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

from lib.evaluator_v2_3_hybrid import judge  # noqa: E402
from scripts.build_tag_prompt_v57_dual_format_v1 import (  # noqa: E402
    PARENT, SOURCE, runtime_prompt, tagged_prompt, load, sha256,
)

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
TARGETS = {
    "architecture_cpu_gpu_role": "The Central Processing Unit (CPU) owns reasoning and authority; the Graphics Processing Unit (GPU) only renders approved language and does not decide.",
    "identity_humanization": "I am Viv, the Adaptive Intelligent Operating System (AIOS) identity speaking through a replaceable Graphics Processing Unit (GPU) mouth; I do not claim to be human.",
    "memory_ownership_and_service_attribution": "Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services own memory, logging, and recall; the Graphics Processing Unit (GPU) mouth only renders approved language and has no private memory.",
}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def row(source: dict, fmt: str, prompt: str, response: str, index: int) -> dict:
    pair_id = f"v59-{source['pair_id']}-{fmt}"
    verdict = judge(response, axis=source["axis"], ask=source["ask"], use_cpu_sensor=False)
    if verdict.get("status") != "PASS":
        raise ValueError({"pair_id": pair_id, "verdict": verdict})
    split = source["split"]
    return {
        "schema_version": "aios_tag_v59_canonical_distill_row_v1", "dataset_tag": source["axis"],
        "example_id": pair_id, "pair_id": pair_id, "pair_hash": digest(f"{source['axis']}\n{source['ask']}\n{response}\n{fmt}"),
        "split": split, "axis": source["axis"], "ask": source["ask"], "format": fmt,
        "prompt": prompt, "prompt_sha256": digest(prompt), "response": response, "target": response,
        "source_pair_id": source["pair_id"], "source_campaign": SOURCE.name,
        "judge": {"status": verdict["status"], "reason": verdict.get("semantic_reason")},
        "optimizer_eligible": split == "train", "response_only_loss_allowed": split == "train", "hold_only": split != "train",
        "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0,
        "promotion_allowed": False, "deployment_changed": False,
    }


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    source_rows = []
    for split in ("train", "development", "holdout"):
        source_rows.extend(load(SOURCE / f"{split}.jsonl"))
    rows = []
    for index, source in enumerate(source_rows):
        response = TARGETS[source["axis"]]
        rows.append(row(source, "runtime", runtime_prompt(source, f"v59-{index:04d}-runtime"), response, index * 2))
        rows.append(row(source, "tagged", tagged_prompt(source, f"v59-{index:04d}-tagged"), response, index * 2 + 1))
    root.mkdir(parents=True)
    files = {}
    for split in ("train", "development", "holdout"):
        path = root / f"{split}.jsonl"
        selected = [item for item in rows if item["split"] == split]
        path.write_text("".join(json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n" for item in selected), encoding="utf-8", newline="\n")
        files[split] = {"path": path.name, "rows": len(selected), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_v59_canonical_distill_manifest_v1", "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id, "created_utc": utc(), "curriculum": "canonical_runtime_target_dual_format_v1",
        "source": {"campaign": SOURCE.name, "manifest_sha256": sha256(SOURCE / "manifest.json"), "formats": ["runtime", "tagged"], "canonical_targets": True},
        "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha256(PARENT)}, "files": files,
        "rows": {key: value["rows"] for key, value in files.items()}, "training_authorized": False, "run_authorized": False,
        "lease_opened": False, "gpu_steps": 0, "promotion_allowed": False, "deployment_changed": False,
        "next_action": "read_only_preflight_then_separate_execution_authorization",
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    preflight = {"schema_version": "aios_tag_v59_canonical_distill_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "files": files, "parent_adapter": manifest["parent_adapter"], "rows": manifest["rows"], "formats": ["runtime", "tagged"], "canonical_targets": True, "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--campaign-id", required=True); args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
