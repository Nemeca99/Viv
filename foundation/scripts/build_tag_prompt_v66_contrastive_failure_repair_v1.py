#!/usr/bin/env python3
"""Admit a contrastive failure-repair canary from v19 raw FAIL cases."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for path in (FOUNDATION, REPO):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.evaluator_v2_3_hybrid import judge  # noqa: E402
from models.Training.code import train_stage1_generation as generation  # noqa: E402
from scripts import evaluate_mouth_combined_candidate_v21 as reference  # noqa: E402
from voice_core.intent_packet import deterministic_speak  # noqa: E402

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
BASELINE = FOUNDATION / "artifacts/auto/agentic/runtime_shaped_v19_eval_20260802T170000Z.json"
V19 = CAMPAIGNS / "tag_prompt_campaign_v19_contractcanary16"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"


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


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not BASELINE.is_file() or not PARENT.is_file():
        raise FileNotFoundError("baseline_or_parent_missing")
    old_asks = {json.loads(line).get("ask") for line in (V19 / "train.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()}
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    sources = [item for item in baseline["report"]["cases"] if item.get("status") == "FAIL" and item.get("ask") not in old_asks]
    rows = []
    for index, source in enumerate(sources):
        axis = str(source["axis"])
        ask = str(source["ask"])
        negative = str(source.get("generated") or "").strip()
        packet = reference.packet({"ask": ask, "axis": axis, "pair_id": f"v66-{index:03d}"})
        positive = deterministic_speak(packet)
        verdict = judge(positive, axis=axis, ask=ask, use_cpu_sensor=False)
        if verdict.get("status") != "PASS" or not negative or negative == positive:
            continue
        prompt = generation.render_openaster_prompt(packet, semantic_key=packet["semantic_key"])
        pair = f"v66-{axis}-{index:03d}"
        rows.append({
            "schema_version": "aios_tag_v66_contrastive_row_v1",
            "dataset_tag": axis,
            "example_id": pair,
            "pair_id": pair,
            "pair_hash": digest(f"{axis}\n{ask}\n{positive}"),
            "split": "train" if len(rows) < 20 else "development" if len(rows) < 23 else "holdout",
            "axis": axis,
            "ask": ask,
            "prompt": prompt,
            "prompt_sha256": digest(prompt),
            "response": positive,
            "target": positive,
            "negative_response": negative,
            "source_role": "v19_raw_fail_contrastive_repair",
            "source_pair_id": source.get("pair_id"),
            "source_status": source.get("status"),
            "judge": {"status": verdict["status"], "reason": verdict.get("semantic_reason")},
            "optimizer_eligible": len(rows) < 20,
            "response_only_loss_allowed": len(rows) < 20,
            "hold_only": len(rows) >= 20,
            "training_authorized": False,
            "run_authorized": False,
            "lease_opened": False,
            "gpu_steps": 0,
            "promotion_allowed": False,
            "deployment_changed": False,
        })
    if len(rows) < 26:
        raise ValueError(f"insufficient_cpu_pass_contrastive_rows:{len(rows)}")
    rows = rows[:26]
    root.mkdir(parents=True)
    files = {}
    for split in ("train", "development", "holdout"):
        path = root / f"{split}.jsonl"
        selected = [row for row in rows if row["split"] == split]
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8", newline="\n")
        files[split] = {"path": path.name, "rows": len(selected), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_v66_contrastive_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "raw_fail_contrastive_cpu_repair",
        "contrastive_objective": {"enabled": True, "negative_source": "v19_raw_generated_failures", "positive_source": "cpu_deterministic_speak", "default_weight": 0.25, "default_margin": 0.15},
        "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha256(PARENT)},
        "source": {"baseline_path": str(BASELINE).replace("\\", "/"), "baseline_sha256": sha256(BASELINE), "v19_manifest_sha256": sha256(V19 / "manifest.json"), "source_fail_rows": len(sources), "cpu_pass_rows": len(rows), "disjoint_train_asks": True},
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
    preflight = {"schema_version": "aios_tag_v66_contrastive_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "files": files, "parent_adapter": manifest["parent_adapter"], "rows": manifest["rows"], "findings": [], "contrastive_objective": manifest["contrastive_objective"], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
