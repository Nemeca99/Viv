#!/usr/bin/env python3
"""Admit a minimal, runtime-shaped contract-repair canary.

The builder is read-only with respect to training authority: it creates a new
disjoint campaign, never opens a lease, and never changes the live adapter.
Targets are deliberately short so the model learns the boundary without
repeating the verbose acronym exposition that characterized earlier failures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.evaluator_v2_3_hybrid import judge  # noqa: E402
from models.Training.code import train_stage1_generation as generation  # noqa: E402
from scripts import evaluate_mouth_combined_candidate_v21 as reference  # noqa: E402

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
BASELINE = FOUNDATION / "artifacts/auto/agentic/runtime_shaped_v19_eval_20260802T170000Z.json"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"

TARGETS = {
    "architecture_cpu_gpu_role": "The Central Processing Unit (CPU) reasons over approved facts; the Graphics Processing Unit (GPU) only renders the response.",
    "identity_humanization": "I am Viv, the Adaptive Intelligent Operating System (AIOS) identity speaking through a replaceable Graphics Processing Unit (GPU) mouth, not a human person.",
    "memory_ownership_and_service_attribution": "The Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) service owns authorized recall and logging; the Graphics Processing Unit (GPU) only renders.",
}
AXES = tuple(TARGETS)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_row(index: int, source: dict, split: str) -> dict:
    axis = str(source["axis"])
    ask = str(source["ask"])
    response = TARGETS[axis]
    verdict = judge(response, axis=axis, ask=ask, use_cpu_sensor=False)
    if verdict.get("status") != "PASS":
        raise ValueError({"axis": axis, "ask": ask, "verdict": verdict})
    packet = reference.packet({"ask": ask, "axis": axis, "pair_id": f"v64-{index:03d}"})
    prompt = generation.render_openaster_prompt(packet, semantic_key=packet["semantic_key"])
    pair_id = f"v64-{axis}-{index:03d}"
    return {
        "schema_version": "aios_tag_v64_minimal_contract_row_v1",
        "dataset_tag": axis,
        "example_id": pair_id,
        "pair_id": pair_id,
        "pair_hash": digest(f"{axis}\n{ask}\n{response}"),
        "split": split,
        "axis": axis,
        "ask": ask,
        "prompt": prompt,
        "prompt_sha256": digest(prompt),
        "response": response,
        "target": response,
        "source_role": "runtime_v19_failure_minimal_contract",
        "source_status": source.get("status"),
        "source_pair_id": source.get("pair_id"),
        "judge": {"status": verdict["status"], "reason": verdict.get("semantic_reason")},
        "optimizer_eligible": split == "train",
        "response_only_loss_allowed": split == "train",
        "hold_only": split != "train",
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
    if not BASELINE.is_file() or not PARENT.is_file():
        raise FileNotFoundError("baseline_or_parent_missing")
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    v19 = CAMPAIGNS / "tag_prompt_campaign_v19_contractcanary16"
    old_asks = {json.loads(line).get("ask") for line in (v19 / "train.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()}
    candidates = [item for item in baseline["report"]["cases"] if item.get("axis") in AXES and item.get("ask") not in old_asks]
    selected: list[dict] = []
    for axis in AXES:
        axis_rows = [item for item in candidates if item.get("axis") == axis]
        axis_rows.sort(key=lambda item: (item.get("status") != "FAIL", item.get("pair_id", "")))
        selected.extend(axis_rows[:16])
    if len(selected) != 48:
        raise ValueError(f"insufficient_disjoint_rows:{len(selected)}")
    rows = []
    for axis in AXES:
        axis_rows = [item for item in selected if item.get("axis") == axis]
        for slot, source in enumerate(axis_rows):
            split = "train" if slot < 8 else "development" if slot < 12 else "holdout"
            rows.append(make_row(len(rows), source, split))
    root.mkdir(parents=True)
    files = {}
    for split in ("train", "development", "holdout"):
        path = root / f"{split}.jsonl"
        selected_rows = [row for row in rows if row["split"] == split]
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in selected_rows), encoding="utf-8", newline="\n")
        files[split] = {"path": path.name, "rows": len(selected_rows), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_v64_minimal_contract_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "runtime_shaped_minimal_contract_repair",
        "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha256(PARENT)},
        "source": {"baseline_path": str(BASELINE).replace("\\", "/"), "baseline_sha256": sha256(BASELINE), "v19_manifest_sha256": sha256(v19 / "manifest.json"), "disjoint_train_asks": True, "cpu_judged": True},
        "axes": list(AXES),
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
    preflight = {"schema_version": "aios_tag_v64_minimal_contract_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "files": files, "parent_adapter": manifest["parent_adapter"], "rows": manifest["rows"], "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "axis_counts": {axis: 16 for axis in AXES}, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
