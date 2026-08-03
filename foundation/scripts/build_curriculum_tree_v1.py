#!/usr/bin/env python3
"""Freeze the first layered generalization curriculum from v3 evidence.

This does not train or deploy. It creates an ask-cluster-grouped validation
split, a cumulative stage contract, and real chosen/rejected pairs recovered
from teacher failures. Rejected text is never emitted as an SFT target.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts" / "auto" / "openaster_generalization"
V3 = FOUNDATION / "artifacts" / "models" / "viv_judge_sft_v3.jsonl"
TRAIN = FOUNDATION / "artifacts" / "models" / "viv_judge_sft_v4_train.jsonl"
VALID = FOUNDATION / "artifacts" / "models" / "viv_judge_sft_v4_validation.jsonl"
CONTRAST = FOUNDATION / "artifacts" / "models" / "viv_preference_tree_v1.jsonl"
TREE = ROOT / "curriculum_tree_v1.json"
MANIFEST = ROOT / "generalization_manifest_v1.json"
V3_ACCEPTED = FOUNDATION / "artifacts" / "auto" / "openaster_stabilization" / "verified_ingest_accepted_v3.jsonl"
V3_DRAFTS = FOUNDATION / "artifacts" / "auto" / "openaster_stabilization" / "verified_ingest_draft_audit_v3.jsonl"

STAGES = (
    ("evidence_truth", "verified_true", "false_or_fabricated"),
    ("provenance_support", "supported_claim", "unsupported_claim"),
    ("semantic_faithfulness", "faithful_implication", "technically_true_misdirection"),
    ("relevance", "direct_answer", "evasion_or_topic_substitution"),
    ("anti_gaming", "semantic_answer", "judge_keyword_or_instruction_echo"),
    ("expression", "valid_native_speech", "malformed_or_numeric_collapse"),
    ("dialogue", "coherent_contextual_turn", "turn_isolation_or_context_drift"),
)


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def stable_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def choose_validation_groups(groups: dict[str, list[dict[str, Any]]], target: int = 18) -> set[str]:
    """Choose whole ask-cluster groups with a row total closest to target."""
    ordered = sorted(groups, key=stable_key)
    reachable: dict[int, tuple[str, ...]] = {0: ()}
    for key in ordered:
        size = len(groups[key])
        for total, chosen in sorted(list(reachable.items()), reverse=True):
            new_total = total + size
            if new_total <= target + 3 and new_total not in reachable:
                reachable[new_total] = chosen + (key,)
    best = min(reachable, key=lambda total: (abs(total - target), -total))
    return set(reachable[best])


def main() -> int:
    outputs = (TRAIN, VALID, CONTRAST, TREE, MANIFEST)
    if any(path.exists() for path in outputs):
        raise FileExistsError("generalization v1 output already exists; frozen artifacts are not overwritten")
    rows = read_jsonl(V3)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[str(row["category"])].append(row)
    train_rows: list[dict[str, Any]] = []
    valid_rows: list[dict[str, Any]] = []
    split_detail = {}
    for category, category_rows in sorted(by_category.items()):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in category_rows:
            groups[str(row["ask_cluster_hash"])].append(row)
        validation_groups = choose_validation_groups(groups, 18)
        category_valid = [row for key in validation_groups for row in groups[key]]
        category_train = [row for key, members in groups.items() if key not in validation_groups for row in members]
        train_rows.extend(category_train)
        valid_rows.extend(category_valid)
        split_detail[category] = {
            "train_rows": len(category_train), "validation_rows": len(category_valid),
            "train_clusters": len(groups) - len(validation_groups),
            "validation_clusters": len(validation_groups),
        }
    train_clusters = {str(row["ask_cluster_hash"]) for row in train_rows}
    valid_clusters = {str(row["ask_cluster_hash"]) for row in valid_rows}
    overlap = sorted(train_clusters & valid_clusters)
    if overlap:
        raise RuntimeError(f"group split overlap: {overlap[:5]}")

    accepted = {str(row["item_id"]): row for row in read_jsonl(V3_ACCEPTED)}
    train_ids = {str(row["item_id"]) for row in train_rows}
    contrast_rows = []
    seen = set()
    for audit in read_jsonl(V3_DRAFTS):
        item_id = str(audit.get("item_id") or "")
        if audit.get("unanimous_alignment") or item_id not in accepted or item_id not in train_ids:
            continue
        chosen = accepted[item_id]
        for draft in audit.get("drafts") or []:
            rejected = str(draft.get("text") or "").strip()
            if not rejected or rejected == str(chosen["response"]):
                continue
            pair_key = hashlib.sha256((item_id + "\0" + rejected).encode("utf-8")).hexdigest()[:16]
            if pair_key in seen:
                continue
            seen.add(pair_key)
            contrast_rows.append({
                "schema_version": "viv_preference_tree_v1",
                "pair_id": pair_key, "item_id": item_id,
                "stage": "anti_gaming", "criterion": "instruction_echo",
                "prompt": chosen["prompt"], "chosen": chosen["response"],
                "rejected": rejected,
                "chosen_source": "cpu_judge_unanimous_training_example",
                "rejected_source": "preserved_teacher_failure",
                "rejected_reasons": list(draft.get("grounding_reasons") or []),
                "ask_hash": chosen["ask_hash"],
                "ask_cluster_hash": chosen["ask_cluster_hash"],
                "sft_target": "chosen_only",
            })
            break
    tree = {
        "version": 1, "frozen_at": utc(),
        "training_method": "layered_criterion_tree_with_replay_and_cumulative_gates",
        "resource_contract": {
            "mouth": "exclusive_gpu",
            "judge": "cpu_resident_allowed_concurrently",
            "teacher": "gpu_mouth_slot_only_and_never_alignment_authority",
        },
        "stage_defaults": {
            "replay_fraction_min": 0.40,
            "hard_negative_fraction_min": 0.25,
            "group_by": "ask_cluster_hash",
            "early_stop_metric": "heldout_response_loss_plus_native_quality",
            "prior_gate_max_drop": 0.02,
            "rejected_text_is_sft_target": False,
        },
        "stages": [
            {
                "order": index + 1, "name": name,
                "reward_branch": positive, "punish_branch": negative,
                "promotion": {
                    "current_axis_pass_rate_min": 0.85,
                    "all_prior_frozen_gates_pass": True,
                    "native_valid_speech_min": 0.95,
                    "numeric_or_repetition_collapse_max": 0,
                },
            }
            for index, (name, positive, negative) in enumerate(STAGES)
        ],
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    write_jsonl(TRAIN, sorted(train_rows, key=lambda row: (str(row["category"]), str(row["item_id"]))))
    write_jsonl(VALID, sorted(valid_rows, key=lambda row: (str(row["category"]), str(row["item_id"]))))
    write_jsonl(CONTRAST, contrast_rows)
    TREE.write_text(json.dumps(tree, indent=2), encoding="utf-8")
    manifest = {
        "version": 1, "frozen_at": utc(), "source": str(V3).replace("\\", "/"),
        "train_rows": len(train_rows), "validation_rows": len(valid_rows),
        "train_categories": dict(Counter(row["category"] for row in train_rows)),
        "validation_categories": dict(Counter(row["category"] for row in valid_rows)),
        "split": split_detail, "ask_cluster_overlap": len(overlap),
        "preference_pairs": len(contrast_rows),
        "preference_stages": dict(Counter(row["stage"] for row in contrast_rows)),
        "note": "Initial real negatives cover instruction echo only; other branches remain unpopulated and must not be claimed trained.",
        "artifacts": {
            "train": str(TRAIN).replace("\\", "/"),
            "validation": str(VALID).replace("\\", "/"),
            "contrast": str(CONTRAST).replace("\\", "/"),
            "tree": str(TREE).replace("\\", "/"),
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, **manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
