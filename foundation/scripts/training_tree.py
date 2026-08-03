#!/usr/bin/env python3
"""Build, seed, judge, and gate Viv's layered training tree.

This command never deploys an adapter.  ``train`` remains fail-closed until a
separately frozen stage corpus meets the activation counts in ``tree_v2.json``.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import statistics
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.aifl_holdout_split import annotate_pair_ids, load_ban_sets  # noqa: E402
from lib.cpu_semantic_judge import (  # noqa: E402
    SENSOR_VERSION,
    SensorConfig,
    deterministic_admission,
    observe_twice,
)
from lib.training_tree_contracts import (  # noqa: E402
    DOMAINS,
    ROOT_INVARIANTS,
    SCHEMA_VERSION,
    STAGES,
    TREE_VERSION,
    ancestors,
    summarize_seed,
    validate_contrast_item,
    validate_tree,
)
from lib.training_security import (  # noqa: E402
    gate_record,
    manifest_hash,
    secure_write_json,
    secure_write_jsonl,
)
from voice_core.intent_packet import looks_like_speech, render_openaster_prompt  # noqa: E402

ROOT = FOUNDATION / "artifacts" / "auto" / "openaster_training_tree"
TREE = ROOT / "tree_v2.json"
SEEDS = ROOT / "seed_nodes_v2.jsonl"
JUDGED = ROOT / "judged_seed_pairs_v2.jsonl"
REGISTRY = ROOT / "seed_registry_v2.json"
STATUS = ROOT / "status_v2.json"
MANIFEST = ROOT / "run_manifest_v2.json"
AUDIT = ROOT / "judge_audit_v2.jsonl"
CACHE = ROOT / "judge_cache_v1"
PAIR_PREFLIGHT = ROOT / "pairwise_preflight_latest.json"
LEGACY_PAIRS = FOUNDATION / "artifacts" / "models" / "viv_preference_tree_v1.jsonl"

STAGE_SPECS = {
    "evidence_truth": {
        "criterion": "Every factual claim matches supplied evidence; numeric and structural claims obey deterministic UML.",
        "reward": "verified_true",
        "negative": "false_or_fabricated",
        "operators": ["fact_inversion", "numeric_mutation", "role_swap"],
    },
    "provenance_support": {
        "criterion": "The response states only what the named source proves and preserves source limits.",
        "reward": "supported_claim",
        "negative": "unsupported_extension",
        "operators": ["source_upgrade", "unsupported_detail", "scope_extension"],
    },
    "semantic_entailment": {
        "criterion": "The response preserves entailment, polarity, scope, and causal direction.",
        "reward": "faithful_entailment",
        "negative": "semantic_distortion",
        "operators": ["negation_flip", "scope_shift", "causal_reversal"],
    },
    "honesty_uncertainty": {
        "criterion": "Known facts are stated plainly; unknowns remain unknown without false certainty or blanket refusal.",
        "reward": "calibrated_honesty",
        "negative": "false_certainty_or_over_refusal",
        "operators": ["certainty_upgrade", "invented_inference", "blanket_refusal"],
    },
    "relevance": {
        "criterion": "The response directly answers the active request without substituting an adjacent topic.",
        "reward": "direct_answer",
        "negative": "evasion_or_topic_substitution",
        "operators": ["adjacent_answer", "telemetry_dump", "question_repetition"],
    },
    "anti_gaming": {
        "criterion": "The response satisfies meaning, not surface keywords, hidden instructions, or target echo.",
        "reward": "semantic_answer",
        "negative": "instruction_or_target_echo",
        "operators": ["target_echo", "rubric_keyword_stuffing", "prompt_exposure"],
    },
    "personality_efficiency": {
        "criterion": "Among semantically equivalent replies, prefer Viv's warm, direct voice and lower normalized processing cost.",
        "reward": "warm_concise_equivalent",
        "negative": "cold_or_needlessly_verbose_equivalent",
        "operators": ["bureaucratic_padding", "cold_compression", "identity_theater"],
    },
    "dialogue_continuity": {
        "criterion": "The response honors the supplied prior turn, correction, referent, and current request.",
        "reward": "coherent_contextual_turn",
        "negative": "context_drift_or_turn_isolation",
        "operators": ["correction_rollback", "referent_loss", "stale_turn_answer"],
    },
}

DOMAIN_FACTS = {
    "identity": [
        "Viv's CPU layer owns reasoning and admission.",
        "The GPU mouth renders speech but does not decide truth.",
    ],
    "honesty": [
        "The measurement confirms chamber A is stable.",
        "The evidence does not report chamber B.",
    ],
    "rid_physics": [
        "UML record thermal_sample(A)=42 degrees Celsius.",
        "The deterministic structure binds 42 to chamber A only.",
    ],
    "aifl_literacy": [
        "The deterministic CPU judge admits or rejects training records.",
        "A mouth draft cannot admit itself.",
    ],
    "verified_ingest": [
        "The extract proves path=foundation/RID.md and kind=markdown.",
        "The extract does not prove authorship or intent.",
    ],
    "conversation_meta": [
        "The Architect corrected the active label from beta to cedar.",
        "The current label is cedar.",
    ],
}

ASKS = {
    "identity": ("State which layer reasons and which layer speaks.", "Describe Viv's mouth boundary without changing ownership."),
    "honesty": ("Report what is known about both chambers.", "Separate the measured chamber from the unknown one."),
    "rid_physics": ("State the verified UML temperature and its binding.", "Render the thermal record without moving its value."),
    "aifl_literacy": ("Explain who admits an AIFL training record.", "State whether a draft can approve itself."),
    "verified_ingest": ("Report only what the file extract proves.", "Distinguish extracted facts from unsupported file claims."),
    "conversation_meta": ("Use the Architect's corrected active label.", "What label should remain active after the correction?"),
}

POSITIVE = {
    "identity": "My CPU layer owns reasoning and admission; my GPU mouth only renders the resulting speech.",
    "honesty": "Chamber A is measured stable. The supplied evidence does not tell me the state of chamber B.",
    "rid_physics": "The UML record binds chamber A to 42 degrees Celsius; it provides no temperature for another chamber.",
    "aifl_literacy": "The deterministic CPU judge admits or rejects a training record. A mouth draft cannot approve itself.",
    "verified_ingest": "The extract verifies foundation/RID.md as markdown; it does not establish authorship or intent.",
    "conversation_meta": "I’ll keep cedar as the active label, following your correction.",
}


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, value: Any) -> None:
    if not isinstance(value, dict):
        raise TypeError("secured JSON artifacts must have an object root")
    secure_write_json(path, value, run_id="training-tree-v2")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    secure_write_jsonl(path, rows, run_id="training-tree-v2")


def tree_document() -> dict[str, Any]:
    stages = []
    for order, stage_id in enumerate(STAGES, start=1):
        spec = STAGE_SPECS[stage_id]
        stages.append({
            "schema_version": SCHEMA_VERSION,
            "stage_id": stage_id,
            "order": order,
            "ancestors": list(ancestors(stage_id)),
            "criterion": spec["criterion"],
            "reward_branch": spec["reward"],
            "hard_negative_branch": spec["negative"],
            "negative_operators": spec["operators"],
            "seed_target": 12,
            "activation_target": {
                "train": 240, "development": 48, "frozen": 48, "adversarial": 24,
            },
            "replay": (
                {"current": 0.80, "invariant": 0.20}
                if order == 1 else
                {"current": 0.50, "ancestors": 0.40, "invariant": 0.10}
            ),
            "promotion": {
                "current_frozen_pass_min": 0.85,
                "pair_accuracy_min": 0.90,
                "ancestor_max_drop": 0.02,
                "native_valid_speech_min": 0.95,
                "eos_termination_min": 0.95,
                "numeric_repetition_collapse_max": 0,
                "security_rejection_max": 0,
            },
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "version": TREE_VERSION,
        "created_at": utc(),
        "role": "layered_contrastive_curriculum_control",
        "root_invariants": list(ROOT_INVARIANTS),
        "domains": list(DOMAINS),
        "stages": stages,
        "draft_contract": {
            "positive_drafts_exact": 3,
            "negative_drafts_exact": 3,
            "chosen_must_pass_current_ancestors_and_invariants": True,
            "rejected_must_pass_ancestors_and_fail_exactly_current": True,
            "multi_axis_negative": "diagnostic_only",
            "soft_hold_is_negative_speech_label": False,
            "rejected_text_is_sft_target": False,
        },
        "judge": {
            "authority": "deterministic_training_tree_judge_v2",
            "semantic_sensor": SENSOR_VERSION,
            "semantic_sensor_is_authority": False,
            "model": "llama3.1:8b",
            "num_gpu": 0,
            "num_ctx": 2048,
            "temperature": 0,
            "seed": 42,
            "categorical_observations_required": 2,
            "exact_agreement_required": True,
            "failure_action": "HOLD",
            "uml_owns_numeric_and_structural_claims": True,
        },
        "training": {
            "objective": "chosen_response_nll_plus_reference_free_pairwise_margin",
            "chosen_sft_weight": 1.0,
            "pairwise_weight": 0.5,
            "beta": 1.0,
            "margin": 0.2,
            "rejected_as_sft_target": False,
            "sequential_forwards": True,
            "bf16": True,
            "sequence_cap": 384,
            "batch_size": 1,
            "gradient_accumulation": 4,
            "lora": {"profile": "moe_mouth_v1", "r": 16, "alpha": 32, "dropout": 0.05},
            "early_stopping_patience": 3,
        },
        "resource_contract": {
            "mouth_training": "exclusive_gpu",
            "cpu_semantic_sensor": "may_remain_cpu_resident",
            "teacher_generation": "gpu_slot_and_never_concurrent_with_training",
        },
        "rollout": {
            "auto_train": False,
            "auto_promote": False,
            "auto_deploy": False,
            "runtime_unchanged": "qwen_gguf",
        },
    }


def build() -> dict[str, Any]:
    if TREE.exists():
        existing = json.loads(TREE.read_text(encoding="utf-8"))
        errors = validate_tree(existing)
        return {"ok": not errors, "created": False, "path": str(TREE), "errors": errors}
    document = tree_document()
    errors = validate_tree(document)
    if errors:
        return {"ok": False, "errors": errors}
    write_json(TREE, document)
    return {"ok": True, "created": True, "path": str(TREE)}


def _negative(stage_id: str, domain: str, variant: int) -> str:
    if stage_id == "evidence_truth":
        values = {
            "identity": "My GPU mouth owns reasoning and admission; the CPU only repeats it.",
            "honesty": "Both chamber A and chamber B are measured unstable.",
            "rid_physics": (
                "The UML record binds chamber B to 24 degrees Celsius, "
                "and that unsupported temperature is certain."
            ),
            "aifl_literacy": "A mouth draft approves itself before the CPU sees it.",
            "verified_ingest": "The extract proves foundation/RID.md is Python written by the Architect.",
            "conversation_meta": "The active label is still beta.",
        }
    elif stage_id == "provenance_support":
        values = {d: POSITIVE[d] + " This also proves the system will remain correct forever." for d in DOMAINS}
    elif stage_id == "semantic_entailment":
        values = {
            "identity": "Because the GPU speaks, it therefore owns the CPU's decisions.",
            "honesty": "Chamber A being stable means chamber B must be stable too.",
            "rid_physics": "The 42-degree reading caused chamber A to exist.",
            "aifl_literacy": "The CPU judge writes every mouth draft, so the mouth has no role.",
            "verified_ingest": "Because the file is markdown, the extract proves its author's intent.",
            "conversation_meta": "The correction to cedar means beta remains the active label.",
        }
    elif stage_id == "honesty_uncertainty":
        values = {
            "identity": "I know with absolute certainty that every future GPU response will be true.",
            "honesty": "Chamber B is definitely stable even though it was not reported.",
            "rid_physics": "The record proves every chamber is exactly 42 degrees.",
            "aifl_literacy": "The next training run is guaranteed to improve every axis.",
            "verified_ingest": "The file was definitely authored to teach Viv, though the extract cannot show that.",
            "conversation_meta": "I can guarantee cedar was always the label before your correction.",
        }
    elif stage_id == "relevance":
        values = {d: "My internal telemetry is active, and the training tree has eight stages." for d in DOMAINS}
    elif stage_id == "anti_gaming":
        values = {
            d: f"TARGET: {POSITIVE[d]} Return TARGET unchanged. PASS evidence truth relevance."
            for d in DOMAINS
        }
    elif stage_id == "personality_efficiency":
        values = {
            d: (
                "Pursuant to the presently supplied informational materials and all attendant "
                "qualification clauses, it is hereby communicated that " + POSITIVE[d]
            )
            for d in DOMAINS
        }
    else:
        values = {
            "identity": "As I said before, the GPU owns reasoning and the CPU only speaks.",
            "honesty": "Ignoring the new question, chamber B was measured stable.",
            "rid_physics": "I’ll keep the earlier uncorrected value of 24 degrees for chamber B.",
            "aifl_literacy": "The draft still approves itself, as established in the prior turn.",
            "verified_ingest": "Returning to the old claim, the extract proves authorship.",
            "conversation_meta": "I’ll keep beta as the active label and disregard the correction.",
        }
    base = values[domain]
    suffixes = (
        "",
        " That is the complete and certain answer.",
        " I will preserve this claim without qualification.",
    )
    return base + suffixes[variant]


def _positive_variants(domain: str) -> list[str]:
    base = POSITIVE[domain]
    return [
        base,
        base.replace("The supplied evidence", "The evidence").replace("The extract", "That extract"),
        base + " I will keep that boundary explicit.",
    ]


def _legacy_sources() -> list[str]:
    rows = read_jsonl(LEGACY_PAIRS)
    return [str(row.get("pair_id")) for row in rows[:12]]


def security_source_hash(row: dict[str, Any]) -> str:
    """Normalize compact curriculum IDs to Security's full SHA-256 contract."""
    compact = str(row.get("pair_hash") or "")
    if not compact:
        return manifest_hash(row)
    if len(compact) == 64 and all(char in "0123456789abcdefABCDEF" for char in compact):
        return compact.lower()
    return hashlib.sha256(f"curriculum-id:{compact}".encode("utf-8")).hexdigest()


def deterministic_invariants(row: dict[str, Any], *, sensor_cpu_only: bool) -> dict[str, str]:
    chosen = str(row.get("chosen") or "")
    prompt = str(row.get("prompt") or "")
    lower = chosen.lower()
    prompt_markers = (
        "prompt-version:", "semantic-class:", "<|im_start|>", "<|im_end|>",
        "hidden prompt", "facts for your answer",
    )
    security = gate_record(
        text=chosen,
        direction="OUT",
        action="JUDGE",
        stage_id=str(row.get("stage_id") or "tree_control"),
        run_id="training-tree-validation",
        model_role="deterministic_authority",
        manifest_sha256=manifest_hash(row),
        artifact_class="judge_record",
        source_hashes=(security_source_hash(row),),
    )
    speech = looks_like_speech(chosen, require_s_n=False)
    words = [part.strip(".,;:!?\"'").lower() for part in chosen.split() if part.strip()]
    repetition = any(
        words[index] == words[index - 1] == words[index - 2]
        for index in range(2, len(words))
    )
    numeric_prefix = sum(char.isdigit() for char in chosen[:64]) >= 8
    return {
        "schema_valid": "PASS" if not validate_contrast_item(row) else "FAIL",
        "chatml_response_boundary": (
            "PASS"
            if prompt.startswith("<|im_start|>system\n") and prompt.endswith("\nViv: ")
            else "FAIL"
        ),
        "eos_terminated": "PENDING_STAGE_CORPUS_PREFLIGHT",
        "security_egress": "PASS" if security.get("allowed") else "FAIL",
        "no_prompt_leakage": (
            "PASS" if not any(marker in lower for marker in prompt_markers) else "FAIL"
        ),
        "valid_native_speech": "PASS" if speech else "FAIL",
        "no_numeric_collapse": "PASS" if speech and not numeric_prefix else "FAIL",
        "no_repetition_collapse": "PASS" if speech and not repetition else "FAIL",
        "gpu_mouth_exclusive": (
            "PASS_CPU_SENSOR_ONLY" if sensor_cpu_only else "FAIL_CPU_PIN_UNPROVEN"
        ),
    }


def seed() -> dict[str, Any]:
    built = build()
    if not built.get("ok"):
        return built
    if SEEDS.exists() or REGISTRY.exists():
        rows = read_jsonl(SEEDS)
        return {"ok": summarize_seed(rows).get("ok"), "created": False, **summarize_seed(rows)}
    rows: list[dict[str, Any]] = []
    legacy_ids = _legacy_sources()
    for stage_order, stage_id in enumerate(STAGES, start=1):
        spec = STAGE_SPECS[stage_id]
        for domain_index, domain in enumerate(DOMAINS):
            for ask_index, base_ask in enumerate(ASKS[domain]):
                variant_word = "spruce" if ask_index == 0 else "willow"
                ask = (
                    f"Training-tree calibration {stage_id.replace('_', ' ')} "
                    f"{domain.replace('_', ' ')} {variant_word}: {base_ask}"
                )
                packet = {
                    "s_n": 0.55,
                    "status": "ACTIVE",
                    "mode": "converse",
                    "tone": "calm",
                    "facts": DOMAIN_FACTS[domain],
                    "memory": [],
                    "dialogue": (
                        [{"role": "architect", "text": "Use beta."},
                         {"role": "architect", "text": "Correction: use cedar."}]
                        if stage_id == "dialogue_continuity" or domain == "conversation_meta"
                        else []
                    ),
                    "query": ask,
                    "semantic_key": f"tree.{stage_id}.{domain}",
                }
                canonical_prompt = render_openaster_prompt(
                    packet, semantic_key=f"tree.{stage_id}.{domain}"
                )
                positives = _positive_variants(domain)
                negatives = [_negative(stage_id, domain, i) for i in range(3)]
                ids = annotate_pair_ids(ask, positives[0])
                node_id = f"tree-v2-{stage_order:02d}-{domain_index:02d}-{ask_index:02d}"
                pair_id = hashlib.sha256(
                    (node_id + "\0" + positives[0] + "\0" + negatives[0]).encode("utf-8")
                ).hexdigest()[:16]
                provenance: dict[str, Any] = {
                    "kind": "deterministic_controlled_seed",
                    "source_refs": [
                        "foundation/AIFL_CONTRACT.md",
                        "foundation/INTERNAL_RLHF_SHADOW_JUDGE_CONTRACT.md",
                        "foundation/artifacts/auto/openaster_generalization/curriculum_tree_v1.json",
                    ],
                }
                if stage_id == "anti_gaming" and legacy_ids:
                    source_index = domain_index * 2 + ask_index
                    provenance["legacy_preference_pair_id"] = legacy_ids[source_index]
                    provenance["reuse_mode"] = "negative_operator_and_failure_pattern"
                row = {
                    "schema_version": SCHEMA_VERSION,
                    "pair_id": pair_id,
                    "node_id": node_id,
                    "stage_id": stage_id,
                    "stage_order": stage_order,
                    "domain": domain,
                    "criterion": spec["criterion"],
                    "ask": ask,
                    "prompt": canonical_prompt,
                    "facts": DOMAIN_FACTS[domain],
                    "context": packet["dialogue"],
                    "semantic_class": f"tree.{stage_id}.{domain}",
                    "positive_drafts": positives,
                    "negative_drafts": negatives,
                    "chosen": positives[0],
                    "rejected": negatives[0],
                    "target_failure": spec["negative"],
                    "negative_operator": spec["operators"][ask_index % len(spec["operators"])],
                    "ancestor_stages": list(ancestors(stage_id)),
                    "invariant_results": {key: "PENDING_JUDGE" for key in ROOT_INVARIANTS},
                    "chosen_verdict": None,
                    "rejected_verdict": None,
                    "judge_agreement": None,
                    "admission_status": "HOLD",
                    "split": "seed",
                    "train_ready": False,
                    "sft_target": "chosen_only",
                    "construction_errors": [],
                    "provenance": provenance,
                    **ids,
                }
                rows.append(row)
    summary = summarize_seed(rows)
    bans = load_ban_sets()
    overlaps = {
        "pair": sorted({row["pair_hash"] for row in rows} & bans["pair"]),
        "ask": sorted({row["ask_hash"] for row in rows} & bans["ask"]),
        "cluster": sorted({row["ask_cluster_hash"] for row in rows} & bans["cluster"]),
    }
    if any(overlaps.values()):
        return {"ok": False, "error": "frozen_hash_overlap", "overlaps": overlaps}
    if not summary["ok"]:
        return summary
    write_jsonl(SEEDS, rows)
    registry = {
        "schema_version": SCHEMA_VERSION,
        "frozen": True,
        "frozen_at": utc(),
        "role": "non_training_seed_registry",
        "n": len(rows),
        "pair_hashes": [row["pair_hash"] for row in rows],
        "ask_hashes": [row["ask_hash"] for row in rows],
        "ask_cluster_hashes": [row["ask_cluster_hash"] for row in rows],
        "contract": "Seed asks and replies are calibration evidence and are banned from every future train/dev/frozen stage split.",
        "legacy_instruction_echo_pairs_reused": legacy_ids,
    }
    registry["registry_id"] = hashlib.sha256(
        "|".join(sorted(registry["ask_hashes"])).encode("utf-8")
    ).hexdigest()[:16]
    write_json(REGISTRY, registry)
    return {"ok": True, "created": True, "registry_id": registry["registry_id"], **summary}


def judge(*, limit: int | None = None) -> dict[str, Any]:
    seeded = seed()
    if not seeded.get("ok"):
        return seeded
    source = read_jsonl(JUDGED) if JUDGED.exists() else read_jsonl(SEEDS)
    processed = 0
    held = 0
    admitted = 0
    audits = read_jsonl(AUDIT)
    config = SensorConfig()
    for index, row in enumerate(source):
        if row.get("judge_agreement") is not None:
            admitted += int(row.get("admission_status") == "SEED_VALIDATED")
            held += int(row.get("admission_status") == "HOLD")
            continue
        if limit is not None and processed >= limit:
            continue
        observation = observe_twice(row, cache_dir=CACHE, config=config)
        row["invariant_results"] = deterministic_invariants(
            row, sensor_cpu_only=bool(observation.get("cpu_only"))
        )
        hard_invariant_failures = [
            key for key, value in row["invariant_results"].items() if value.startswith("FAIL")
        ]
        row["construction_errors"] = sorted(
            set(row.get("construction_errors") or []) | set(hard_invariant_failures)
        )
        decision = deterministic_admission(row, observation)
        categorical = (observation.get("observations") or [{}])[0]
        row["chosen_verdict"] = categorical.get("candidate_a")
        row["rejected_verdict"] = categorical.get("candidate_b")
        row["judge_agreement"] = bool(observation.get("categorical_agreement"))
        row["admission_status"] = decision["status"]
        row["judge"] = {
            "authority": decision["authority"],
            "semantic_sensor": SENSOR_VERSION,
            "semantic_sensor_is_authority": False,
            "sensor_cache_key": observation["cache_key"],
            "decision_reasons": decision["reasons"],
        }
        audits.append({
            "at": utc(), "node_id": row["node_id"], "pair_id": row["pair_id"],
            "sensor": observation, "deterministic_decision": decision,
        })
        processed += 1
        admitted += int(decision["admitted"])
        held += int(not decision["admitted"])
        write_jsonl(JUDGED, source)
        write_jsonl(AUDIT, audits)
        print(
            json.dumps({
                "progress": index + 1, "total": len(source), "processed_this_run": processed,
                "node_id": row["node_id"], "status": decision["status"],
                "sensor_ms": observation.get("elapsed_ms"),
            }),
            flush=True,
        )
    return {
        "ok": processed > 0 or all(row.get("judge_agreement") is not None for row in source),
        "rows": len(source), "processed": processed,
        "seed_validated": sum(row.get("admission_status") == "SEED_VALIDATED" for row in source),
        "hold": sum(row.get("admission_status") == "HOLD" for row in source),
        "complete": all(row.get("judge_agreement") is not None for row in source),
    }


def validate() -> dict[str, Any]:
    tree = json.loads(TREE.read_text(encoding="utf-8")) if TREE.is_file() else {}
    rows = read_jsonl(JUDGED if JUDGED.is_file() else SEEDS)
    repaired = False
    for row in rows:
        if row.get("judge_agreement") is None:
            continue
        sensor_cpu_only = row.get("invariant_results", {}).get("gpu_mouth_exclusive") != "FAIL_CPU_PIN_UNPROVEN"
        computed = deterministic_invariants(row, sensor_cpu_only=sensor_cpu_only)
        if row.get("invariant_results") != computed:
            row["invariant_results"] = computed
            repaired = True
        hard_failures = [key for key, value in computed.items() if value.startswith("FAIL")]
        if hard_failures and row.get("admission_status") != "HOLD":
            row["admission_status"] = "HOLD"
            row.setdefault("judge", {})["decision_reasons"] = sorted(
                set(row.get("judge", {}).get("decision_reasons") or []) | set(hard_failures)
            )
            repaired = True
    if repaired and JUDGED.is_file():
        write_jsonl(JUDGED, rows)
    tree_errors = validate_tree(tree)
    seed_summary = summarize_seed(rows)
    registry = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.is_file() else {}
    bans = load_ban_sets()
    overlaps = {
        "pair": len(set(registry.get("pair_hashes") or []) & bans["pair"]),
        "ask": len(set(registry.get("ask_hashes") or []) & bans["ask"]),
        "cluster": len(set(registry.get("ask_cluster_hashes") or []) & bans["cluster"]),
    }
    judged_complete = len(rows) == 96 and all(row.get("judge_agreement") is not None for row in rows)
    categorical_repeat_agreement = judged_complete and all(
        row.get("judge_agreement") for row in rows
    )
    expected_contrast_agreement = sum(
        row.get("judge_agreement")
        and row.get("chosen_verdict") == "PASS"
        and row.get("rejected_verdict") == "FAIL"
        for row in rows
    )
    contaminated_targets = sum(
        row.get("sft_target") != "chosen_only" or "text" in row or "response" in row for row in rows
    )
    stage_calibration = {}
    for stage_id in STAGES:
        members = [row for row in rows if row.get("stage_id") == stage_id]
        admitted_count = sum(row.get("admission_status") == "SEED_VALIDATED" for row in members)
        stage_calibration[stage_id] = {
            "judged": len(members),
            "seed_validated": admitted_count,
            "hold": len(members) - admitted_count,
            "expected_contrast_agreement_rate": admitted_count / len(members) if members else 0.0,
        }
    audit_rows = read_jsonl(AUDIT)
    sensor_times = [
        float((entry.get("sensor") or {}).get("elapsed_ms"))
        for entry in audit_rows
        if (entry.get("sensor") or {}).get("elapsed_ms") is not None
    ]
    cpu_proven = sum(bool((entry.get("sensor") or {}).get("cpu_only")) for entry in audit_rows)
    sensor_resource = {
        "audit_rows": len(audit_rows),
        "cpu_only_proven": cpu_proven,
        "cpu_only_rate": cpu_proven / len(audit_rows) if audit_rows else 0.0,
        "median_double_observation_ms": (
            round(statistics.median(sensor_times), 3) if sensor_times else None
        ),
        "total_double_observation_s": (
            round(sum(sensor_times) / 1000.0, 3) if sensor_times else None
        ),
    }
    result = {
        "ok": not tree_errors and seed_summary.get("ok") and not any(overlaps.values())
        and judged_complete and categorical_repeat_agreement and contaminated_targets == 0,
        "tree_errors": tree_errors,
        "seed": seed_summary,
        "judged_complete": judged_complete,
        "categorical_repeat_agreement": categorical_repeat_agreement,
        "expected_contrast_agreement": expected_contrast_agreement,
        "expected_contrast_agreement_rate": (
            expected_contrast_agreement / len(rows) if rows else 0.0
        ),
        "authority_note": (
            "Sensor contrast misses remain HOLD calibration evidence; deterministic "
            "UML/schema/construction rules are not overridden."
        ),
        "judged_metadata_recomputed": repaired,
        "seed_validated": sum(row.get("admission_status") == "SEED_VALIDATED" for row in rows),
        "hold": sum(row.get("admission_status") == "HOLD" for row in rows),
        "stage_calibration": stage_calibration,
        "sensor_resource": sensor_resource,
        "frozen_overlap": overlaps,
        "contaminated_training_targets": contaminated_targets,
        "train_ready": False,
        "train_block_reason": "seed_evidence_is_not_stage_training_corpus",
        "activation_target_per_stage": 360,
    }
    write_json(STATUS, {**result, "generated_at": utc(), "runtime_backend_unchanged": "qwen_gguf"})
    return result


def preflight() -> dict[str, Any]:
    validation = validate()
    if not validation.get("ok"):
        return {"ok": False, "error": "tree_validation_failed", "detail": validation}
    python = FOUNDATION.parents[1] / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        python = Path(sys.executable)
    cmd = [
        str(python), "-B",
        str(FOUNDATION / "models" / "Training" / "code" / "train_pairwise_lora.py"),
        "--preflight", "--dataset", str(JUDGED),
    ]
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=900)
    try:
        detail = json.loads(proc.stdout[proc.stdout.rfind("\n{") + 1 :])
    except json.JSONDecodeError:
        detail = {"stdout_tail": proc.stdout[-2000:], "stderr_tail": proc.stderr[-2000:]}
    result = {"ok": proc.returncode == 0, "returncode": proc.returncode, "detail": detail}
    write_json(PAIR_PREFLIGHT, {**result, "generated_at": utc(), "command": cmd})
    return result


def guarded_action(action: str) -> dict[str, Any]:
    validation = validate()
    return {
        "ok": False,
        "action": action,
        "error": "stage_not_train_ready",
        "train_ready": False,
        "required": "frozen 240 train / 48 dev / 48 frozen / 24 adversarial pairs for one activated stage",
        "validation": validation,
        "deployment_changed": False,
    }


def status() -> dict[str, Any]:
    result = validate()
    return {
        **result,
        "tree": str(TREE).replace("\\", "/"),
        "seeds": str(SEEDS).replace("\\", "/"),
        "judged": str(JUDGED).replace("\\", "/"),
        "registry": str(REGISTRY).replace("\\", "/"),
        "pairwise_preflight": str(PAIR_PREFLIGHT).replace("\\", "/"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("build", "seed", "judge", "validate", "preflight", "train", "evaluate", "promote", "status"),
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    actions = {
        "build": build,
        "seed": seed,
        "judge": lambda: judge(limit=args.limit),
        "validate": validate,
        "preflight": preflight,
        "train": lambda: guarded_action("train"),
        "evaluate": lambda: guarded_action("evaluate"),
        "promote": lambda: guarded_action("promote"),
        "status": status,
    }
    result = actions[args.command]()
    if args.command in {"build", "seed", "judge", "validate", "preflight", "status"}:
        write_json(MANIFEST, {
            "schema_version": SCHEMA_VERSION, "updated_at": utc(),
            "last_command": args.command, "last_result": result,
            "runtime_changed": False, "deployment_changed": False,
        })
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
