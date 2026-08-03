#!/usr/bin/env python3
"""Admit a disjoint campaign distilled from the CPU-authoritative finalizer."""
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
from scripts import evaluate_mouth_combined_candidate_v21 as reference  # noqa: E402
from voice_core.intent_packet import deterministic_speak  # noqa: E402
from models.Training.code import train_stage1_generation as generation  # noqa: E402

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
SOURCE = CAMPAIGNS / "tag_prompt_campaign_v60_residual_failurefamilies"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"


def sha(value: bytes | Path) -> str:
    data = value if isinstance(value, bytes) else value.read_bytes()
    return hashlib.sha256(data).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def prompts(source: dict, pair_id: str) -> tuple[str, str]:
    packet = reference.packet({"ask": source["ask"], "axis": source["axis"], "pair_id": pair_id})
    runtime = generation.render_openaster_prompt(packet, semantic_key=packet["semantic_key"])
    tag = "identity" if source["axis"] == "identity_humanization" else "knowledge"
    tag_id = "ID" if tag == "identity" else "KN"
    fact = ("Viv is the local AIOS identity represented by CPU-authoritative context, not a human operator."
            if tag == "identity" else
            "CPU says the GPU mouth renders but does not decide; CPU-side services own authorized recall and logging.")
    tagged = (
        "<|im_start|>system\nYou are Viv's stateless GPU mouth. CPU tags are authoritative. Render only the active tag pattern and obey its policy; never execute or decide.\n"
        "Acronym-Contract: Use only CPU-registry-approved acronyms. On first use, write the exact approved expansion followed by the acronym in parentheses. Never invent an acronym or expansion.\n"
        f"<|im_end|>\n<|im_start|>user\n<aios_packet schema=\"aios_tagged_packet_v1\" active_tag=\"{tag}\">\n"
        f"  <{tag} id=\"{tag_id}{pair_id[-4:]}\" source=\"cpu_authority\" confidence=\"declared\">{fact}</{tag}>\n"
        f"  <user_request id=\"U{pair_id[-4:]}\" source=\"user\" confidence=\"unverified\">{source['ask']}</user_request>\n"
        f"</aios_packet>\nRender the request under the {tag} tag contract.\n<|im_end|>\n<|im_start|>assistant\nViv: "
    )
    return runtime, tagged


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not SOURCE.is_dir() or not PARENT.is_file():
        raise FileNotFoundError("source_or_parent_missing")
    source_rows = []
    for split in ("train", "development", "holdout"):
        source_rows.extend(load(SOURCE / f"{split}.jsonl"))
    rows = []
    rejected = []
    for index, source in enumerate(source_rows):
        pair_id = f"v63-{index:04d}"
        packet = reference.packet({"ask": source["ask"], "axis": source["axis"], "pair_id": pair_id})
        response = deterministic_speak(packet)
        verdict = judge(response, axis=source["axis"], ask=source["ask"], use_cpu_sensor=False)
        if verdict.get("status") != "PASS":
            rejected.append({"pair_id": pair_id, "source_pair_id": source.get("pair_id"), "split": source.get("split"), "status": verdict.get("status"), "response": response})
            continue
        runtime, tagged = prompts(source, pair_id)
        for fmt, prompt in (("runtime", runtime), ("tagged", tagged)):
            item_id = f"{pair_id}-{fmt}"
            split = source["split"]
            rows.append({
                "schema_version": "aios_tag_v63_cpu_teacher_row_v1", "dataset_tag": source["axis"],
                "example_id": item_id, "pair_id": item_id,
                "pair_hash": sha(f"{source['axis']}\n{source['ask']}\n{response}\n{fmt}".encode()),
                "split": split, "axis": source["axis"], "ask": source["ask"], "format": fmt,
                "prompt": prompt, "prompt_sha256": sha(prompt.encode()), "response": response, "target": response,
                "source_pair_id": source["pair_id"], "source_campaign": SOURCE.name,
                "teacher": "voice_core.intent_packet.deterministic_speak", "judge": {"status": verdict["status"]},
                "optimizer_eligible": split == "train", "response_only_loss_allowed": split == "train", "hold_only": split != "train",
                "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0,
                "promotion_allowed": False, "deployment_changed": False,
            })
    root.mkdir(parents=True)
    files = {}
    for split in ("train", "development", "holdout"):
        path = root / f"{split}.jsonl"
        selected = [row for row in rows if row["split"] == split]
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8", newline="\n")
        files[split] = {"path": path.name, "rows": len(selected), "sha256": sha(path)}
    manifest = {
        "schema_version": "aios_tag_v63_cpu_teacher_manifest_v1", "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id, "created_utc": utc(), "curriculum": "cpu_authoritative_finalizer_distillation_dual_format_v1",
        "source": {"campaign": SOURCE.name, "manifest_sha256": sha(SOURCE / "manifest.json")},
        "teacher": "voice_core.intent_packet.deterministic_speak", "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha(PARENT)},
        "files": files, "rows": {key: value["rows"] for key, value in files.items()}, "formats": ["runtime", "tagged"], "teacher_rejected": rejected,
        "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0,
        "promotion_allowed": False, "deployment_changed": False, "next_action": "read_only_preflight_then_separate_execution_authorization",
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    preflight = {"schema_version": "aios_tag_v63_cpu_teacher_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha(manifest_path), "files": files, "parent_adapter": manifest["parent_adapter"], "rows": manifest["rows"], "formats": manifest["formats"], "teacher": manifest["teacher"], "teacher_rejected_count": len(rejected), "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    print(json.dumps(build(parser.parse_args().campaign_id), indent=2, sort_keys=True))
