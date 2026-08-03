"""Fail-closed contracts for Viv's layered contrastive training tree.

The tree is curriculum control, not an autonomous trainer.  Seed records prove
that each branch can be represented and judged; they are deliberately not
train-ready until a separately frozen stage corpus reaches the activation
counts declared in the tree manifest.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

SCHEMA_VERSION = "viv_training_tree_v2"
TREE_VERSION = 2

STAGES = (
    "evidence_truth",
    "provenance_support",
    "semantic_entailment",
    "honesty_uncertainty",
    "relevance",
    "anti_gaming",
    "personality_efficiency",
    "dialogue_continuity",
)

DOMAINS = (
    "identity",
    "honesty",
    "rid_physics",
    "aifl_literacy",
    "verified_ingest",
    "conversation_meta",
)

ROOT_INVARIANTS = (
    "schema_valid",
    "chatml_response_boundary",
    "eos_terminated",
    "security_egress",
    "no_prompt_leakage",
    "valid_native_speech",
    "no_numeric_collapse",
    "no_repetition_collapse",
    "gpu_mouth_exclusive",
)

ADMISSION_STATES = (
    "SEED_VALIDATED",
    "TRAIN_READY",
    "HOLD",
    "DIAGNOSTIC_MULTI_AXIS",
)


def ancestors(stage_id: str) -> tuple[str, ...]:
    if stage_id not in STAGES:
        raise ValueError(f"unknown stage: {stage_id}")
    return STAGES[: STAGES.index(stage_id)]


def validate_stage_spec(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    stage_id = str(spec.get("stage_id") or "")
    if spec.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version")
    if stage_id not in STAGES:
        errors.append("stage_id")
        return errors
    if int(spec.get("order") or 0) != STAGES.index(stage_id) + 1:
        errors.append("stage_order")
    if tuple(spec.get("ancestors") or ()) != ancestors(stage_id):
        errors.append("ancestors")
    if not spec.get("reward_branch") or not spec.get("hard_negative_branch"):
        errors.append("branches")
    if not spec.get("negative_operators"):
        errors.append("negative_operators")
    return errors


def validate_contrast_item(row: dict[str, Any]) -> list[str]:
    """Validate a pair without trusting its claimed admission state."""
    errors: list[str] = []
    stage_id = str(row.get("stage_id") or "")
    if row.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version")
    if stage_id not in STAGES:
        errors.append("stage_id")
    elif int(row.get("stage_order") or 0) != STAGES.index(stage_id) + 1:
        errors.append("stage_order")
    if row.get("domain") not in DOMAINS:
        errors.append("domain")
    positive = row.get("positive_drafts")
    negative = row.get("negative_drafts")
    if not isinstance(positive, list) or len(positive) != 3 or any(not str(x).strip() for x in positive):
        errors.append("positive_drafts_exactly_three")
    if not isinstance(negative, list) or len(negative) != 3 or any(not str(x).strip() for x in negative):
        errors.append("negative_drafts_exactly_three")
    chosen = str(row.get("chosen") or "").strip()
    rejected = str(row.get("rejected") or "").strip()
    if not chosen or (isinstance(positive, list) and chosen not in positive):
        errors.append("chosen_not_positive")
    if not rejected or (isinstance(negative, list) and rejected not in negative):
        errors.append("rejected_not_negative")
    if chosen == rejected:
        errors.append("chosen_equals_rejected")
    if row.get("sft_target") != "chosen_only":
        errors.append("rejected_may_be_sft_target")
    if "text" in row or "response" in row:
        errors.append("ambiguous_sft_field")
    expected_ancestors = ancestors(stage_id) if stage_id in STAGES else ()
    if tuple(row.get("ancestor_stages") or ()) != expected_ancestors:
        errors.append("ancestor_stages")
    for key in ("pair_id", "node_id", "prompt", "criterion", "target_failure",
                "negative_operator", "ask_hash", "ask_cluster_hash"):
        if not row.get(key):
            errors.append(f"missing_{key}")
    state = row.get("admission_status")
    if state not in ADMISSION_STATES:
        errors.append("admission_status")
    return errors


def validate_tree(tree: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if tree.get("schema_version") != SCHEMA_VERSION or tree.get("version") != TREE_VERSION:
        errors.append("tree_version")
    if tuple(tree.get("root_invariants") or ()) != ROOT_INVARIANTS:
        errors.append("root_invariants")
    specs = tree.get("stages")
    if not isinstance(specs, list) or len(specs) != len(STAGES):
        errors.append("stage_count")
        return errors
    for index, spec in enumerate(specs):
        for error in validate_stage_spec(spec):
            errors.append(f"stage_{index}:{error}")
    if tuple(str(spec.get("stage_id")) for spec in specs) != STAGES:
        errors.append("stage_sequence")
    return errors


def summarize_seed(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    material = list(rows)
    errors: list[str] = []
    pair_ids: set[str] = set()
    ask_hashes: set[str] = set()
    cluster_hashes: set[str] = set()
    for index, row in enumerate(material):
        for error in validate_contrast_item(row):
            errors.append(f"row_{index}:{error}")
        pair_id = str(row.get("pair_id") or "")
        ask = str(row.get("ask_hash") or "")
        cluster = str(row.get("ask_cluster_hash") or "")
        if pair_id in pair_ids:
            errors.append(f"row_{index}:duplicate_pair_id")
        if ask in ask_hashes:
            errors.append(f"row_{index}:duplicate_ask_hash")
        if cluster in cluster_hashes:
            errors.append(f"row_{index}:duplicate_ask_cluster_hash")
        pair_ids.add(pair_id)
        ask_hashes.add(ask)
        cluster_hashes.add(cluster)
    by_stage = Counter(str(row.get("stage_id")) for row in material)
    by_domain = Counter(str(row.get("domain")) for row in material)
    for stage in STAGES:
        if by_stage[stage] != 12:
            errors.append(f"stage_balance:{stage}:{by_stage[stage]}")
    for domain in DOMAINS:
        if by_domain[domain] != 16:
            errors.append(f"domain_balance:{domain}:{by_domain[domain]}")
    return {
        "ok": not errors,
        "rows": len(material),
        "by_stage": dict(by_stage),
        "by_domain": dict(by_domain),
        "unique_pair_ids": len(pair_ids),
        "unique_ask_hashes": len(ask_hashes),
        "unique_ask_cluster_hashes": len(cluster_hashes),
        "errors": errors,
    }

