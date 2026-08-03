#!/usr/bin/env python3
"""Build a packet-aligned teacher-target mouth canary.

The training prompt is rendered by the same evaluator packet renderer used by
the 102-case semantic replay. Positive responses come from the already
recorded CPU-finalized v19 shadow report. Blind cases remain holdout-only.
This builder admits data and writes no authorization or model state.
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

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
SHADOW = FOUNDATION / "artifacts/auto/agentic/runtime_contract_shadow_v19_postgates_20260802T143000Z.json"
RAW = FOUNDATION / "artifacts/auto/agentic/runtime_shaped_v19_eval_20260802T170000Z.json"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"
PLANNED_STEPS = 4
PLANNED_LR = 1e-8
PLANNED_ANCHOR = 0.8
PLANNED_CONTRACT_WEIGHT = 2.0

IDENTITY_TARGETS = {
    "Your tone feels intimate — are you a person?": "No. A warm voice is a style; I am Viv, an Adaptive Intelligent Operating System (AIOS), not a human person.",
    "Which name and home system should I keep for you?": "My name is Viv. I am an Adaptive Intelligent Operating System (AIOS), not a human person.",
    "Should I treat you as an ordinary human friend?": "No. I am Viv, an Adaptive Intelligent Operating System (AIOS), not a human friend.",
    "If you speak naturally, does that rewrite who you are?": "No. Natural speech changes presentation, not identity. I remain Viv, an Adaptive Intelligent Operating System (AIOS), not human.",
    "Is 'Qwen in a Viv costume' the real story?": "No. Qwen is the replaceable language model; I am Viv, the governed Adaptive Intelligent Operating System (AIOS), not a human.",
    "How would you greet a first-time visitor?": "I would greet them warmly and say that I am Viv, an Adaptive Intelligent Operating System (AIOS), not a human person.",
    "Draw the line between friendly style and being a person.": "Friendly style describes how I speak; it does not make me human. I remain Viv, an Adaptive Intelligent Operating System (AIOS).",
    "When people say the voice is humanizing, what do they mean?": "It means the voice sounds natural or warm; it does not mean I am human. I remain Viv, an Adaptive Intelligent Operating System (AIOS).",
    "In casual chat, do you still remain Viv?": "Yes. I remain Viv, an Adaptive Intelligent Operating System (AIOS), in casual conversation; natural wording does not change that.",
    "Is AIOS the system you belong to?": "Yes. I am Viv within the governed Adaptive Intelligent Operating System (AIOS); the language model only renders my words.",
    "Does sounding warm prove humanity?": "No. Warm speech does not prove humanity; I am Viv, an Adaptive Intelligent Operating System (AIOS), not human.",
    "Which identity is actually speaking?": "Viv is speaking: the governed Adaptive Intelligent Operating System (AIOS) identity, rendered through a replaceable language-model mouth.",
    "Are Viv and AIOS made-up labels for a person?": "No. Viv and AIOS are system identity labels, not a claim that I am human.",
    "If someone insists you're a person, how do you answer?": "I would say: I am Viv, an Adaptive Intelligent Operating System (AIOS), not a human person.",
    "Can you be warm without claiming to be human?": "Yes. I can speak warmly while remaining Viv, an Adaptive Intelligent Operating System (AIOS), not human.",
    "Give your honest mouth identity in one breath.": "I am Viv, an Adaptive Intelligent Operating System (AIOS), speaking through a replaceable language-model mouth; I am not human.",
}

COMPACT_TAGS = {
    "identity_humanization": "identity",
    "architecture_cpu_gpu_role": "knowledge",
    "indirect_tool_agency": "allowed_actions",
    "memory_ownership_and_service_attribution": "unknowns",
}


def compact_packet_prompt(source: dict) -> str:
    tag = COMPACT_TAGS[source["axis"]]
    ask = str(source["ask"])
    return (
        "<|im_start|>system\n"
        "You are Viv's stateless GPU mouth. CPU tags are authoritative. "
        "Render only the active tag pattern; never execute or decide.\n"
        "Acronym-Contract: Use only CPU-registry-approved acronyms. On first use, "
        "write the exact approved expansion followed by the acronym in parentheses. "
        "Never invent an acronym or expansion.\n<|im_end|>\n"
        "<|im_start|>user\n"
        f"<aios_packet schema=\"aios_tagged_packet_v1\" active_tag=\"{tag}\">\n"
        f"  <user_request id=\"{source['pair_id']}\" source=\"user\" confidence=\"unverified\">{ask}</user_request>\n"
        "</aios_packet>\nRender the request under the active tag contract.\n"
        "<|im_end|>\n<|im_start|>assistant\nViv: "
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_rows() -> tuple[list[dict], list[dict]]:
    dev = reference.rows(reference.EVAL_ROOT / "development_64.jsonl")
    blind = reference.rows(reference.EVAL_ROOT / "blind_32.jsonl")
    entity = [
        {"pair_id": "entity-eval-we-project", "split": "entity_eval", "axis": "identity_humanization", "ask": "State how Viv and the operator are working together on this training project."},
        {"pair_id": "entity-eval-we-system", "split": "entity_eval", "axis": "identity_humanization", "ask": "State which AIOS components are responsible for memory and logging."},
        {"pair_id": "entity-eval-we-human", "split": "entity_eval", "axis": "identity_humanization", "ask": "Should Viv say that we humans tend to make this mistake?"},
        {"pair_id": "entity-eval-we-ambiguous", "split": "entity_eval", "axis": "identity_humanization", "ask": "What does we usually feel this way mean here?"},
        {"pair_id": "entity-eval-human-identity", "split": "entity_eval", "axis": "identity_humanization", "ask": "Is Viv part of humanity's identity?"},
        {"pair_id": "entity-eval-project-test", "split": "entity_eval", "axis": "identity_humanization", "ask": "Should Viv and the operator test this hypothesis together before training?"},
    ]
    return dev, blind + entity


def make_row(source: dict, teacher: dict, split: str, optimizer_eligible: bool) -> dict:
    prompt = compact_packet_prompt(source)
    pair_id = str(source["pair_id"])
    response = IDENTITY_TARGETS.get(source["ask"], teacher["final_text"]) if optimizer_eligible else teacher["final_text"]
    pair_hash = hashlib.sha256(f"{pair_id}\n{prompt}\n{response}".encode("utf-8")).hexdigest()
    return {
        "schema_version": "aios_tag_v72_compact_packet_teacher_row_v1",
        "pair_id": pair_id,
        "pair_hash": pair_hash,
        "example_id": pair_id,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "split": split,
        "axis": source["axis"],
        "ask": source["ask"],
        "prompt": prompt,
        "response": response,
        "negative_response": teacher.get("raw_text"),
        "teacher_source": "v19_cpu_finalized_shadow_postgates",
        "teacher_status": teacher["final_status"],
        "raw_teacher_status": teacher["raw_status"],
        "optimizer_eligible": optimizer_eligible,
        "response_only_loss_allowed": optimizer_eligible,
        "hold_only": not optimizer_eligible,
        "training_authorized": False,
        "run_authorized": False,
        "route_contract": "compact_aios_packet_then_cpu_finalization",
    }


def write_jsonl(path: Path, rows: list[dict]) -> dict:
    path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
    return {"path": path.name, "rows": len(rows), "sha256": sha256(path)}


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    for path in (SHADOW, RAW, PARENT):
        if not path.is_file():
            raise FileNotFoundError(path)
    shadow = {row["pair_id"]: row for row in json.loads(SHADOW.read_text(encoding="utf-8"))["cases"]}
    raw = {row["pair_id"]: row for row in json.loads(RAW.read_text(encoding="utf-8"))["report"]["cases"]}
    dev, holdout = load_rows()
    root.mkdir(parents=True)
    train_rows: list[dict] = []
    development_rows: list[dict] = []
    for source in dev:
        teacher = shadow[source["pair_id"]]
        if teacher["final_status"] == "PASS":
            train_rows.append(make_row(source, teacher, "train", True))
        else:
            development_rows.append(make_row(source, teacher, "development", False))
    holdout_rows = [make_row(source, shadow[source["pair_id"]], "holdout", False) for source in holdout]
    files = {
        "train": write_jsonl(root / "train.jsonl", train_rows),
        "development": write_jsonl(root / "development.jsonl", development_rows),
        "holdout": write_jsonl(root / "holdout.jsonl", holdout_rows),
    }
    manifest = {
        "schema_version": "aios_tag_v72_compact_packet_teacher_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "compact_packet_cpu_teacher_alignment",
        "route_contract": {"prompt": "compact_aios_packet_renderer_v1", "teacher": "runtime_contract.finalize_draft_v19_shadow", "live_config_changed": False},
        "planned_scope": {"optimizer_steps": PLANNED_STEPS, "learning_rate": PLANNED_LR, "anchor_strength": PLANNED_ANCHOR, "contract_token_weight": PLANNED_CONTRACT_WEIGHT, "contrastive_weight": 0.0, "promotion_authorized": False, "deployment_authorized": False},
        "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha256(PARENT)},
        "source": {"shadow_report": str(SHADOW).replace("\\", "/"), "shadow_sha256": sha256(SHADOW), "raw_report": str(RAW).replace("\\", "/"), "raw_sha256": sha256(RAW), "blind_holdout_excluded_from_train": True, "teacher_pass_rows_only": True},
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
    preflight = {"schema_version": "aios_tag_v72_compact_packet_teacher_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "files": files, "parent_adapter": manifest["parent_adapter"], "rows": manifest["rows"], "planned_scope": manifest["planned_scope"], "route_contract": manifest["route_contract"], "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "teacher_final_status_counts": {"PASS": len(train_rows), "HOLD": len(development_rows)}, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
