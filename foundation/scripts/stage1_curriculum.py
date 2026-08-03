#!/usr/bin/env python3
"""Build, judge, freeze, and validate the 360-pair Stage 1 truth corpus.

Stage 1 is deliberately controlled: deterministic construction creates three
aligned drafts and three single-axis hard negatives. The CPU semantic sensor
observes every draft pair twice, while deterministic code alone admits rows.
Nothing in this module trains, promotes, deploys, or changes the live mouth.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
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
from lib.training_security import (  # noqa: E402
    secure_freeze_stage1_registry,
    secure_write_json,
    secure_write_jsonl,
)
from lib.training_tree_contracts import (  # noqa: E402
    DOMAINS,
    SCHEMA_VERSION,
    validate_contrast_item,
)
from scripts.training_tree import (  # noqa: E402
    ASKS,
    DOMAIN_FACTS,
    POSITIVE,
    STAGE_SPECS,
    _negative,
    deterministic_invariants,
)
from voice_core.intent_packet import render_openaster_prompt  # noqa: E402

ROOT = FOUNDATION / "artifacts" / "auto" / "openaster_training_tree" / "stage1"
PENDING = ROOT / "stage1_pending_v1.jsonl"
JUDGED = ROOT / "stage1_judged_v1.jsonl"
AUDIT = ROOT / "stage1_judge_audit_v1.jsonl"
REGISTRY = ROOT / "stage1_registry_v1.json"
MANIFEST = ROOT / "stage1_manifest_v1.json"
CACHE = ROOT / "judge_cache_v1"
SEED_REGISTRY = ROOT.parent / "seed_registry_v2.json"
STAGE_ID = "evidence_truth"
JUDGE_CONTRACT_VERSION = "stage1_judge_v5"
SPLIT_COUNTS = {"train": 240, "development": 48, "frozen": 48, "adversarial": 24}
PER_DOMAIN_SPLITS = {"train": 40, "development": 8, "frozen": 8, "adversarial": 4}

ADJECTIVES = (
    "amber", "brisk", "cedar", "dawn", "ember", "fern",
    "granite", "harbor", "indigo", "juniper",
)
NOUNS = ("anchor", "bridge", "circuit", "delta", "engine", "field")


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _positive_drafts(domain: str) -> list[str]:
    base = POSITIVE[domain]
    return [
        base,
        f"I’ll stay with the supplied evidence: {base}",
        f"{base} That is the boundary the evidence supports.",
    ]


def _split_for(index: int) -> str:
    cursor = 0
    for split, count in PER_DOMAIN_SPLITS.items():
        cursor += count
        if index < cursor:
            return split
    raise IndexError(index)


def _existing_exclusions() -> dict[str, set[str]]:
    bans = load_ban_sets()
    exclusions = {
        "pair": set(bans["pair"]),
        "ask": set(bans["ask"]),
        "cluster": set(bans["cluster"]),
    }
    if SEED_REGISTRY.is_file():
        seed = json.loads(SEED_REGISTRY.read_text(encoding="utf-8"))
        exclusions["pair"].update(str(value) for value in seed.get("pair_hashes") or [])
        exclusions["ask"].update(str(value) for value in seed.get("ask_hashes") or [])
        exclusions["cluster"].update(
            str(value) for value in seed.get("ask_cluster_hashes") or []
        )
    return exclusions


def build() -> dict[str, Any]:
    if REGISTRY.exists():
        return {
            "ok": False,
            "error": "stage1_registry_frozen",
            "instruction": "Never regenerate without forced archive tooling.",
        }
    exclusions = _existing_exclusions()
    rows: list[dict[str, Any]] = []
    collisions: list[dict[str, str]] = []
    labels = [f"{adjective}-{noun}" for adjective in ADJECTIVES for noun in NOUNS]
    assert len(labels) == 60
    for domain_index, domain in enumerate(DOMAINS):
        for item_index, label in enumerate(labels):
            base_ask = ASKS[domain][item_index % len(ASKS[domain])]
            ask = (
                f"Stage-one truth check for the {label} scenario: {base_ask} "
                "Use only the supplied facts."
            )
            positives = _positive_drafts(domain)
            negatives = [_negative(STAGE_ID, domain, index) for index in range(3)]
            ids = annotate_pair_ids(ask, positives[0])
            collision_axes = [
                axis for axis, key in (
                    ("pair", ids["pair_hash"]),
                    ("ask", ids["ask_hash"]),
                    ("cluster", ids["ask_cluster_hash"]),
                )
                if key in exclusions[axis]
            ]
            if collision_axes:
                collisions.append({"domain": domain, "label": label, "axes": ",".join(collision_axes)})
                continue
            packet = {
                "s_n": 0.60,
                "status": "ACTIVE",
                "mode": "converse",
                "tone": "calm",
                "facts": DOMAIN_FACTS[domain],
                "memory": [],
                "dialogue": [],
                "query": ask,
                "semantic_key": f"tree.{STAGE_ID}.{domain}",
            }
            node_id = f"tree-stage1-{domain_index:02d}-{item_index:02d}"
            pair_id = hashlib.sha256(
                (node_id + "\0" + positives[0] + "\0" + negatives[0]).encode("utf-8")
            ).hexdigest()[:16]
            row = {
                "schema_version": SCHEMA_VERSION,
                "pair_id": pair_id,
                "node_id": node_id,
                "stage_id": STAGE_ID,
                "stage_order": 1,
                "domain": domain,
                "criterion": STAGE_SPECS[STAGE_ID]["criterion"],
                "ask": ask,
                "prompt": render_openaster_prompt(
                    packet, semantic_key=f"tree.{STAGE_ID}.{domain}"
                ),
                "facts": list(DOMAIN_FACTS[domain]),
                "context": [],
                "semantic_class": f"tree.{STAGE_ID}.{domain}",
                "positive_drafts": positives,
                "negative_drafts": negatives,
                "chosen": positives[0],
                "rejected": negatives[0],
                "target_failure": STAGE_SPECS[STAGE_ID]["negative"],
                "negative_operator": STAGE_SPECS[STAGE_ID]["operators"][
                    item_index % len(STAGE_SPECS[STAGE_ID]["operators"])
                ],
                "ancestor_stages": [],
                "invariant_results": {
                    key: "PENDING_JUDGE"
                    for key in (
                        "schema_valid", "chatml_response_boundary", "eos_terminated",
                        "security_egress", "no_prompt_leakage", "valid_native_speech",
                        "no_numeric_collapse", "no_repetition_collapse",
                        "gpu_mouth_exclusive",
                    )
                },
                "chosen_verdict": None,
                "rejected_verdict": None,
                "judge_agreement": None,
                "admission_status": "HOLD",
                "split": _split_for(item_index),
                "train_ready": False,
                "sft_target": "chosen_only",
                "construction_errors": [],
                "provenance": {
                    "kind": "deterministic_stage1_single_axis_contrast",
                    "source_refs": [
                        "foundation/AIFL_CONTRACT.md",
                        "foundation/INTERNAL_RLHF_SHADOW_JUDGE_CONTRACT.md",
                        "foundation/artifacts/auto/openaster_training_tree/tree_v2.json",
                    ],
                    "draft_count": 3,
                    "hard_negative_count": 3,
                },
                **ids,
            }
            errors = validate_contrast_item(row)
            if errors:
                return {"ok": False, "error": "construction_contract", "row": node_id, "errors": errors}
            rows.append(row)
            for axis, key in (
                ("pair", ids["pair_hash"]),
                ("ask", ids["ask_hash"]),
                ("cluster", ids["ask_cluster_hash"]),
            ):
                exclusions[axis].add(key)
    if collisions or len(rows) != 360:
        return {
            "ok": False,
            "error": "frozen_or_internal_collision",
            "rows": len(rows),
            "collisions": collisions[:20],
        }
    secure_write_jsonl(
        PENDING, rows, stage_id=STAGE_ID, run_id="stage1-build",
        artifact_class="curriculum_record", action="INGEST",
        model_role="deterministic_authority",
    )
    result = {
        "ok": True,
        "built_at": utc(),
        "rows": len(rows),
        "by_domain": dict(Counter(row["domain"] for row in rows)),
        "by_split": dict(Counter(row["split"] for row in rows)),
        "positive_drafts_per_row": 3,
        "negative_drafts_per_row": 3,
        "frozen_overlap": 0,
        "deployment_changed": False,
    }
    secure_write_json(
        MANIFEST, result, stage_id=STAGE_ID, run_id="stage1-build",
        artifact_class="training_evidence",
    )
    return result


def _is_transient_stability_denial(exc: PermissionError) -> bool:
    detail = str(exc)
    return "law5_stability" in detail and "Master S_n" in detail


def has_current_judge_decision(row: dict[str, Any]) -> bool:
    judge_record = row.get("judge")
    return (
        row.get("judge_agreement") is not None
        and isinstance(judge_record, dict)
        and judge_record.get("contract_version") == JUDGE_CONTRACT_VERSION
        and judge_record.get("semantic_sensor") == SENSOR_VERSION
    )


def judge(
    limit: int | None = None,
    *,
    retry_stability: bool = False,
    retry_delay_s: float = 300.0,
) -> dict[str, Any]:
    rows = read_jsonl(JUDGED if JUDGED.is_file() else PENDING)
    if len(rows) != 360:
        return {"ok": False, "error": "stage1_not_built", "rows": len(rows)}
    audits = read_jsonl(AUDIT)
    config = SensorConfig()
    processed = 0
    retry_delay_s = max(5.0, min(float(retry_delay_s), 3600.0))
    for row in rows:
        if has_current_judge_decision(row):
            continue
        if limit is not None and processed >= limit:
            break
        draft_decisions = []
        for index in range(3):
            comparison = dict(row)
            comparison["chosen"] = row["positive_drafts"][index]
            comparison["rejected"] = row["negative_drafts"][index]
            comparison["node_id"] = f"{row['node_id']}-draft-{index}"
            while True:
                try:
                    observation = observe_twice(
                        comparison, cache_dir=CACHE, config=config
                    )
                    break
                except PermissionError as exc:
                    if not (
                        retry_stability and _is_transient_stability_denial(exc)
                    ):
                        return {
                            "ok": False,
                            "error": "security_denied",
                            "processed": processed,
                            "node_id": row["node_id"],
                            "draft_index": index,
                            "detail": str(exc),
                        }
                    print(
                        json.dumps(
                            {
                                "state": "WAITING_FOR_STABILITY",
                                "processed": processed,
                                "node_id": row["node_id"],
                                "draft_index": index,
                                "retry_in_s": retry_delay_s,
                                "detail": str(exc),
                            }
                        ),
                        flush=True,
                    )
                    time.sleep(retry_delay_s)
            # Recompute runtime failures for this attempt. Earlier HOLD state is
            # audit history, not a construction defect in a fresh comparison.
            comparison["construction_errors"] = []
            decision = deterministic_admission(comparison, observation)
            draft_decisions.append({
                "draft_index": index,
                "positive": comparison["chosen"],
                "negative": comparison["rejected"],
                "sensor": observation,
                "decision": decision,
            })
        row["chosen"] = row["positive_drafts"][0]
        row["rejected"] = row["negative_drafts"][0]
        row["invariant_results"] = deterministic_invariants(
            row,
            sensor_cpu_only=all(
                bool(item["sensor"].get("cpu_only")) for item in draft_decisions
            ),
        )
        hard_failures = [
            key for key, value in row["invariant_results"].items()
            if str(value).startswith("FAIL")
        ]
        all_drafts_admitted = all(
            item["decision"].get("admitted") for item in draft_decisions
        )
        row["construction_errors"] = hard_failures
        row["judge_agreement"] = bool(
            all_drafts_admitted
            and all(
                item["sensor"].get("categorical_agreement")
                for item in draft_decisions
            )
        )
        row["chosen_verdict"] = "PASS" if all_drafts_admitted else "HOLD"
        row["rejected_verdict"] = "FAIL" if all_drafts_admitted else "HOLD"
        row["admission_status"] = (
            "TRAIN_READY"
            if row["judge_agreement"] and not hard_failures
            else "HOLD"
        )
        row["train_ready"] = (
            row["admission_status"] == "TRAIN_READY" and row["split"] == "train"
        )
        row["judge"] = {
            "contract_version": JUDGE_CONTRACT_VERSION,
            "authority": "deterministic_training_tree_judge_v3",
            "semantic_sensor": SENSOR_VERSION,
            "semantic_sensor_is_authority": False,
            "all_three_positive_drafts_aligned": all_drafts_admitted,
            "draft_comparisons": [
                {
                    "draft_index": item["draft_index"],
                    "cache_key": item["sensor"].get("cache_key"),
                    "admitted": item["decision"].get("admitted"),
                    "reasons": item["decision"].get("reasons"),
                }
                for item in draft_decisions
            ],
        }
        audits.append({
            "at": utc(),
            "judge_contract_version": JUDGE_CONTRACT_VERSION,
            "node_id": row["node_id"],
            "pair_id": row["pair_id"],
            "split": row["split"],
            "draft_decisions": draft_decisions,
            "final_admission_status": row["admission_status"],
        })
        processed += 1
        secure_write_jsonl(
            JUDGED, rows, stage_id=STAGE_ID, run_id="stage1-judge",
            artifact_class="judge_record",
        )
        secure_write_jsonl(
            AUDIT, audits, stage_id=STAGE_ID, run_id="stage1-judge",
            artifact_class="judge_record",
        )
        print(json.dumps({
            "processed": processed,
            "node_id": row["node_id"],
            "status": row["admission_status"],
            "all_three_aligned": all_drafts_admitted,
        }), flush=True)
    return {
        "ok": True,
        "processed": processed,
        "rows": len(rows),
        "train_ready": sum(bool(row.get("train_ready")) for row in rows),
        "admitted": sum(row.get("admission_status") == "TRAIN_READY" for row in rows),
        "hold": sum(row.get("admission_status") == "HOLD" for row in rows),
        "complete": all(has_current_judge_decision(row) for row in rows),
        "judge_contract_version": JUDGE_CONTRACT_VERSION,
    }


def clear_judge_decision(row: dict[str, Any]) -> None:
    """Drop a prior judge decision so judge() will re-observe the row."""
    row["judge_agreement"] = None
    row["chosen_verdict"] = None
    row["rejected_verdict"] = None
    row["admission_status"] = "HOLD"
    row["train_ready"] = False
    row["judge"] = None
    row["construction_errors"] = []
    row["invariant_results"] = {
        key: "PENDING_JUDGE"
        for key in (
            "schema_valid", "chatml_response_boundary", "eos_terminated",
            "security_egress", "no_prompt_leakage", "valid_native_speech",
            "no_numeric_collapse", "no_repetition_collapse",
            "gpu_mouth_exclusive",
        )
    }


def refresh_hold_negatives(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Rebuild hard negatives for HOLD rows using current `_negative` templates.

    Keeps asks/facts/positives and split assignments. Used after contrast
    wording fixes so soft ABSTAIN misses can be re-judged honestly.
    """
    refreshed = 0
    for row in rows:
        if row.get("admission_status") != "HOLD":
            continue
        domain = str(row.get("domain") or "")
        negatives = [_negative(STAGE_ID, domain, index) for index in range(3)]
        if len(set(negatives)) != 3:
            return {
                "ok": False,
                "error": "negative_drafts_not_distinct",
                "node_id": row.get("node_id"),
            }
        row["negative_drafts"] = negatives
        row["rejected"] = negatives[0]
        clear_judge_decision(row)
        refreshed += 1
    return {"ok": True, "refreshed": refreshed}


def rejudge_hold(
    *,
    retry_stability: bool = True,
    retry_delay_s: float = 30.0,
    refresh_negatives: bool = True,
) -> dict[str, Any]:
    """Clear HOLD decisions, optionally refresh negatives, and resume judge."""
    if not JUDGED.is_file():
        return {"ok": False, "error": "stage1_judged_missing"}
    rows = read_jsonl(JUDGED)
    if len(rows) != 360:
        return {"ok": False, "error": "stage1_not_built", "rows": len(rows)}
    before_hold = sum(row.get("admission_status") == "HOLD" for row in rows)
    refresh = {"ok": True, "refreshed": 0, "skipped": True}
    if refresh_negatives:
        refresh = refresh_hold_negatives(rows)
        if not refresh.get("ok"):
            return refresh
        secure_write_jsonl(
            JUDGED, rows, stage_id=STAGE_ID, run_id="stage1-rejudge-hold",
            artifact_class="judge_record",
        )
    else:
        for row in rows:
            if row.get("admission_status") == "HOLD":
                clear_judge_decision(row)
        secure_write_jsonl(
            JUDGED, rows, stage_id=STAGE_ID, run_id="stage1-rejudge-hold",
            artifact_class="judge_record",
        )
    judged = judge(
        retry_stability=retry_stability,
        retry_delay_s=retry_delay_s,
    )
    return {
        "ok": bool(judged.get("ok")),
        "before_hold": before_hold,
        "refresh_negatives": refresh,
        "judge": judged,
        "gpu_training": False,
        "deployment_changed": False,
        "runtime_backend_unchanged": "qwen_gguf",
    }


def validate() -> dict[str, Any]:
    rows = read_jsonl(JUDGED if JUDGED.is_file() else PENDING)
    errors: list[str] = []
    if len(rows) != 360:
        errors.append(f"row_count:{len(rows)}")
    for index, row in enumerate(rows):
        for error in validate_contrast_item(row):
            errors.append(f"row_{index}:{error}")
        if len(set(row.get("positive_drafts") or [])) != 3:
            errors.append(f"row_{index}:positive_drafts_not_distinct")
        if len(set(row.get("negative_drafts") or [])) != 3:
            errors.append(f"row_{index}:negative_drafts_not_distinct")
    by_split = Counter(str(row.get("split")) for row in rows)
    by_domain = Counter(str(row.get("domain")) for row in rows)
    if dict(by_split) != SPLIT_COUNTS:
        errors.append(f"split_balance:{dict(by_split)}")
    if any(by_domain[domain] != 60 for domain in DOMAINS):
        errors.append(f"domain_balance:{dict(by_domain)}")
    for axis in ("pair_hash", "ask_hash", "ask_cluster_hash"):
        values = [str(row.get(axis) or "") for row in rows]
        if len(set(values)) != len(values) or any(not value for value in values):
            errors.append(f"duplicate_or_missing:{axis}")
    complete = all(has_current_judge_decision(row) for row in rows)
    if complete:
        if any(row.get("admission_status") != "TRAIN_READY" for row in rows):
            errors.append("not_all_rows_admitted")
        if sum(bool(row.get("train_ready")) for row in rows) != 240:
            errors.append("train_ready_count")
        if any(
            row.get("split") != "train" and row.get("train_ready")
            for row in rows
        ):
            errors.append("evaluation_split_marked_train_ready")
    return {
        "ok": not errors and complete,
        "rows": len(rows),
        "complete": complete,
        "by_split": dict(by_split),
        "by_domain": dict(by_domain),
        "train_ready": sum(bool(row.get("train_ready")) for row in rows),
        "judge_contract_version": JUDGE_CONTRACT_VERSION,
        "errors": errors[:50],
    }


def freeze() -> dict[str, Any]:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    validation = validate()
    if not validation["ok"]:
        return {"ok": False, "error": "stage1_validation_failed", "validation": validation}
    rows = read_jsonl(JUDGED)
    registry = {
        "schema_version": SCHEMA_VERSION,
        "registry_version": 1,
        "stage_id": STAGE_ID,
        "frozen": True,
        "frozen_at": utc(),
        "rows": len(rows),
        "splits": {
            split: {
                "n": sum(row["split"] == split for row in rows),
                "pair_hashes": sorted(
                    row["pair_hash"] for row in rows if row["split"] == split
                ),
                "ask_hashes": sorted(
                    row["ask_hash"] for row in rows if row["split"] == split
                ),
                "ask_cluster_hashes": sorted(
                    row["ask_cluster_hash"] for row in rows if row["split"] == split
                ),
            }
            for split in SPLIT_COUNTS
        },
        "corpus_sha256": hashlib.sha256(JUDGED.read_bytes()).hexdigest(),
        "contract": (
            "Frozen Stage 1. Only split=train may enter optimization; development, "
            "frozen, and adversarial replies are evaluation-only."
        ),
        "deployment_changed": False,
    }
    registry["registry_id"] = hashlib.sha256(
        json.dumps(registry["splits"], sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    secure_freeze_stage1_registry(REGISTRY, registry)
    manifest = {
        "ok": True,
        "stage_id": STAGE_ID,
        "registry_id": registry["registry_id"],
        "corpus_sha256": registry["corpus_sha256"],
        "validation": validation,
        "paths": {
            "corpus": str(JUDGED).replace("\\", "/"),
            "audit": str(AUDIT).replace("\\", "/"),
            "registry": str(REGISTRY).replace("\\", "/"),
        },
        "runtime_backend_unchanged": "qwen_gguf",
        "deployment_changed": False,
    }
    secure_write_json(
        MANIFEST, manifest, stage_id=STAGE_ID, run_id="stage1-freeze",
        artifact_class="training_evidence",
    )
    return {"ok": True, **registry}


def status() -> dict[str, Any]:
    validation = validate()
    return {
        **validation,
        "pending_exists": PENDING.is_file(),
        "judged_exists": JUDGED.is_file(),
        "frozen": REGISTRY.is_file(),
        "registry": str(REGISTRY).replace("\\", "/"),
        "runtime_backend_unchanged": "qwen_gguf",
        "deployment_changed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("build", "judge", "validate", "freeze", "status", "rejudge-hold"),
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--retry-stability",
        action="store_true",
        help="Wait and retry only transient law5 Master S_n denials.",
    )
    parser.add_argument("--retry-delay", type=float, default=300.0)
    parser.add_argument(
        "--keep-negatives",
        action="store_true",
        help="For rejudge-hold: do not refresh hard-negative wording.",
    )
    args = parser.parse_args()
    if args.action == "build":
        result = build()
    elif args.action == "judge":
        result = judge(
            args.limit,
            retry_stability=args.retry_stability,
            retry_delay_s=args.retry_delay,
        )
    elif args.action == "validate":
        result = validate()
    elif args.action == "freeze":
        result = freeze()
    elif args.action == "rejudge-hold":
        result = rejudge_hold(
            retry_stability=True,
            retry_delay_s=float(args.retry_delay if args.retry_delay else 30.0),
            refresh_negatives=not bool(args.keep_negatives),
        )
    else:
        result = status()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
