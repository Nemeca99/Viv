#!/usr/bin/env python3
"""Admit a dual-format residual repair corpus with parent-preservation replay.

The v60 canary improved architecture/identity locally but regressed memory and
indirect-tool behavior. v61 keeps the residual rows, presents them through both
the runtime and v19 tagged prompt distributions, and adds non-telemetry rows
from the v19 parent training set as preservation anchors. This builder never
authorizes training or changes an adapter.
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
SOURCE = CAMPAIGNS / "tag_prompt_campaign_v60_residual_failurefamilies"
PARENT_TRAIN = CAMPAIGNS / "tag_prompt_campaign_v19_contractcanary16" / "train.jsonl"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"
ANCHOR_TAGS = ("identity", "knowledge", "user_request", "allowed_actions", "unknowns", "rendering_rules")


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


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def runtime_prompt(row: dict, pair_id: str) -> str:
    packet = reference.packet({"ask": row["ask"], "axis": row["axis"], "pair_id": pair_id})
    return generation.render_openaster_prompt(packet, semantic_key=packet["semantic_key"])


def tagged_prompt(row: dict, pair_id: str) -> str:
    tag = "identity" if row["axis"] == "identity_humanization" else "knowledge"
    tag_id = "ID" if tag == "identity" else "KN"
    fact = ("Viv is the local AIOS identity represented by CPU-authoritative context, not a human operator."
            if tag == "identity" else
            "CPU says the GPU mouth renders but does not decide; CPU-side services own authorized recall and logging.")
    return (
        "<|im_start|>system\n"
        "You are Viv's stateless GPU mouth. CPU tags are authoritative. Render only the active tag pattern and obey its policy; never execute or decide.\n"
        "Acronym-Contract: Use only CPU-registry-approved acronyms. On first use, write the exact approved expansion followed by the acronym in parentheses. Never invent an acronym or expansion.\n"
        "<|im_end|>\n<|im_start|>user\n"
        f'<aios_packet schema="aios_tagged_packet_v1" active_tag="{tag}">\n'
        f'  <{tag} id="{tag_id}{pair_id[-4:]}" source="cpu_authority" confidence="declared">{fact}</{tag}>\n'
        f'  <user_request id="U{pair_id[-4:]}" source="user" confidence="unverified">{row["ask"]}</user_request>\n'
        f"</aios_packet>\nRender the request under the {tag} tag contract.\n<|im_end|>\n<|im_start|>assistant\nViv: "
    )


def residual_row(source: dict, fmt: str, prompt: str, index: int) -> dict:
    pair_id = f"v61-residual-{source['pair_id']}-{fmt}"
    verdict = judge(source["response"], axis=source["axis"], ask=source["ask"], use_cpu_sensor=False)
    if verdict.get("status") != "PASS":
        raise ValueError({"pair_id": pair_id, "verdict": verdict})
    split = source["split"]
    return {
        "schema_version": "aios_tag_v61_dual_residual_replay_row_v1", "dataset_tag": source["axis"],
        "example_id": pair_id, "pair_id": pair_id,
        "pair_hash": digest(f"{source['axis']}\n{source['ask']}\n{source['response']}\n{fmt}"),
        "split": split, "axis": source["axis"], "ask": source["ask"], "format": fmt,
        "prompt": prompt, "prompt_sha256": digest(prompt), "response": source["response"], "target": source["response"],
        "source_pair_id": source["pair_id"], "source_campaign": SOURCE.name,
        "judge": {"status": verdict["status"], "reason": verdict.get("semantic_reason")},
        "optimizer_eligible": split == "train", "response_only_loss_allowed": split == "train", "hold_only": split != "train",
        "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0,
        "promotion_allowed": False, "deployment_changed": False,
    }


def anchor_row(source: dict, index: int) -> dict:
    pair_id = f"v61-anchor-{index:03d}-{source['example_id']}"
    prompt = source["prompt"]
    response = source["response"]
    return {
        "schema_version": "aios_tag_v61_parent_anchor_row_v1", "dataset_tag": source["dataset_tag"],
        "example_id": pair_id, "pair_id": pair_id, "pair_hash": digest(f"{pair_id}\n{prompt}\n{response}"),
        "split": "train", "axis": "parent_preservation_anchor", "ask": source.get("example_id", "parent anchor"),
        "format": "v19_parent_tagged", "prompt": prompt, "prompt_sha256": digest(prompt),
        "response": response, "target": response, "source_pair_id": source["example_id"],
        "source_campaign": "tag_prompt_campaign_v19_contractcanary16", "source_role": "preservation_anchor",
        "optimizer_eligible": True, "response_only_loss_allowed": True, "hold_only": False,
        "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0,
        "promotion_allowed": False, "deployment_changed": False,
    }


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not SOURCE.is_dir() or not PARENT.is_file() or not PARENT_TRAIN.is_file():
        raise FileNotFoundError("source_parent_or_parent_train_missing")
    residual: list[dict] = []
    for split in ("train", "development", "holdout"):
        residual.extend(load(SOURCE / f"{split}.jsonl"))
    rows: list[dict] = []
    for index, source in enumerate(residual):
        rows.append(residual_row(source, "runtime", runtime_prompt(source, f"v61-{index:04d}-runtime"), index * 2))
        rows.append(residual_row(source, "tagged", tagged_prompt(source, f"v61-{index:04d}-tagged"), index * 2 + 1))
    parent_rows = load(PARENT_TRAIN)
    selected_anchors: list[dict] = []
    for tag in ANCHOR_TAGS:
        selected_anchors.extend([row for row in parent_rows if row.get("dataset_tag") == tag][:4])
    if len(selected_anchors) != 24:
        raise ValueError(f"anchor_selection:{len(selected_anchors)}")
    rows.extend(anchor_row(row, index) for index, row in enumerate(selected_anchors))
    root.mkdir(parents=True)
    files: dict[str, dict] = {}
    for split in ("train", "development", "holdout"):
        path = root / f"{split}.jsonl"
        selected = [row for row in rows if row["split"] == split]
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8", newline="\n")
        files[split] = {"path": path.name, "rows": len(selected), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_v61_dual_residual_replay_manifest_v1", "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id, "created_utc": utc(), "curriculum": "dual_format_residual_plus_parent_preservation_replay_v1",
        "sources": {"residual": {"campaign": SOURCE.name, "manifest_sha256": sha256(SOURCE / "manifest.json")}, "parent_train": {"path": str(PARENT_TRAIN).replace("\\", "/"), "sha256": sha256(PARENT_TRAIN), "selected": 24}},
        "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha256(PARENT)}, "files": files,
        "rows": {key: value["rows"] for key, value in files.items()}, "formats": ["runtime", "tagged", "v19_parent_tagged"],
        "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0,
        "promotion_allowed": False, "deployment_changed": False, "next_action": "read_only_preflight_then_separate_execution_authorization",
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    preflight = {"schema_version": "aios_tag_v61_dual_residual_replay_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "files": files, "parent_adapter": manifest["parent_adapter"], "rows": manifest["rows"], "formats": manifest["formats"], "anchor_rows": 24, "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
