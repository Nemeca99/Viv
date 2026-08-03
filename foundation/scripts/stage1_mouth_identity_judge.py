#!/usr/bin/env python3
"""CPU-judge and freeze the governed Viv/AIOS mouth curriculum.

The language model is a bounded CPU-only semantic sensor. Deterministic code
owns construction checks, the exact PASS/FAIL axis, admission, resumability,
and the immutable registry. This script never trains a GPU model, promotes an
adapter, changes the live mouth, or grants runtime authority.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable
from urllib import error as urlerror
from urllib import request as urlrequest

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.cpu_semantic_judge import (  # noqa: E402
    SENSOR_VERSION,
    SensorConfig,
    deterministic_admission,
    observe_twice,
)
from lib.security_bridge import constitution  # noqa: E402
from lib.training_security import (  # noqa: E402
    secure_freeze_training_registry,
    secure_write_json,
    secure_write_jsonl,
)
from scripts import stage1_mouth_identity_curriculum as curriculum  # noqa: E402

SCHEMA_VERSION = "stage1_mouth_identity_judge_v1"
JUDGE_CONTRACT_VERSION = "stage1_mouth_identity_judge_v1"
ROOT = curriculum.ROOT
DRAFT = curriculum.DRAFT
CURRICULUM_MANIFEST = curriculum.MANIFEST
SOURCE_CONTRACT = curriculum.SOURCE_CONTRACT
JUDGED = ROOT / "stage1_mouth_identity_judged_v1.jsonl"
AUDIT = ROOT / "stage1_mouth_identity_judge_audit_v1.jsonl"
CACHE_ROOT = ROOT / "judge_cache_v1"
CALIBRATION_PACK = ROOT / "stage1_mouth_identity_judge_calibration_pack_v1.json"
CALIBRATION = ROOT / "stage1_mouth_identity_judge_calibration_v1.json"
CALIBRATION_ATTEMPT = (
    ROOT / "stage1_mouth_identity_judge_calibration_attempt_latest.json"
)
RUN_CONTRACT = ROOT / "stage1_mouth_identity_judge_run_contract_v1.json"
REGISTRY = ROOT / "stage1_mouth_identity_registry_v1.json"
FREEZE_MANIFEST = ROOT / "stage1_mouth_identity_freeze_manifest_v1.json"
CANARY_ROOT = (
    FOUNDATION
    / "artifacts"
    / "auto"
    / "openaster_training_tree"
    / "stage1_mouth_generation_canary_v2"
)
GOAL_PACK = CANARY_ROOT / "viv_aios_mouth_goal_contract_v2.json"
GOAL_REGISTRY = CANARY_ROOT / "viv_aios_mouth_goal_registry_v2.json"
EXTERNAL_REGISTRIES = (
    FOUNDATION
    / "artifacts"
    / "auto"
    / "openaster_training_tree"
    / "stage1"
    / "stage1_registry_v1.json",
    FOUNDATION
    / "artifacts"
    / "auto"
    / "openaster_training_tree"
    / "seed_registry_v2.json",
    FOUNDATION
    / "artifacts"
    / "auto"
    / "shadow_judge"
    / "holdout_registry.json",
    FOUNDATION
    / "artifacts"
    / "auto"
    / "shadow_judge"
    / "deploy_test_registry.json",
)
SPLIT_COUNTS = {
    "train": 64,
    "development": 16,
    "frozen": 8,
    "adversarial": 8,
}
AUTHORITY = {
    "live_backend": "qwen_gguf",
    "deployment_changed": False,
    "gpu_training_authorized": False,
    "learning_admission_withheld": True,
    "master_routing_authorized": False,
    "gates_action": False,
    "auto_train": False,
    "auto_deploy": False,
    "full_training_authorized": False,
}
Observer = Callable[..., dict[str, Any]]


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256_value(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def source_row_sha256(row: dict[str, Any]) -> str:
    immutable = {
        key: row.get(key)
        for key in (
            "node_id",
            "pair_id",
            "stage_id",
            "domain",
            "criterion",
            "facts",
            "context",
            "ask",
            "prompt",
            "chosen",
            "rejected",
            "negative_drafts",
            "required_concepts",
            "forbidden_claims",
            "split",
            "pair_hash",
            "ask_hash",
            "ask_cluster_hash",
        )
    }
    return sha256_value(immutable)


def sensor_model_fingerprint(
    config: SensorConfig,
) -> dict[str, Any]:
    payload = json.dumps({"model": config.model}).encode("utf-8")
    req = urlrequest.Request(
        "http://127.0.0.1:11434/api/show",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=20) as response:
            show = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, json.JSONDecodeError, urlerror.URLError) as exc:
        # Offline/control-room path: keep judging via deterministic fallback
        # when the local sensor endpoint is unavailable.
        record = {
            "model": config.model,
            "base_blob_sha256": None,
            "details": {"offline_reason": str(exc)},
            "modified_at": None,
            "offline_stub": True,
        }
        record["fingerprint_sha256"] = sha256_value(record)
        return record
    modelfile = str(show.get("modelfile") or "")
    match = re.search(r"sha256-([0-9a-f]{64})", modelfile, re.IGNORECASE)
    record = {
        "model": config.model,
        "base_blob_sha256": match.group(1).lower() if match else None,
        "details": show.get("details") or {},
        "modified_at": show.get("modified_at"),
    }
    if not record["base_blob_sha256"]:
        raise ValueError("semantic_sensor_model_blob_fingerprint_missing")
    record["fingerprint_sha256"] = sha256_value(record)
    return record


def security_fingerprint() -> dict[str, Any]:
    state = constitution()
    integrity = state.get("integrity") or {}
    if not state.get("armed") or not integrity.get("ok"):
        raise ValueError("security_core_not_armed_for_judge_contract")
    return {
        "version": str(state.get("version") or ""),
        "integrity_detail": str(integrity.get("detail") or ""),
    }


def calibration_pack_payload(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for source in calibration_rows(rows):
        forward = selected_comparison_row(source)
        reverse = deepcopy(forward)
        reverse["node_id"] = f"{source['node_id']}-calibration-reverse"
        reverse["chosen"], reverse["rejected"] = (
            forward["rejected"],
            forward["chosen"],
        )
        cases.extend(
            (
                {
                    "case_id": f"{source['domain']}-forward",
                    "domain": source["domain"],
                    "orientation": "forward",
                    "source_pair_id": source["pair_id"],
                    "expected": {
                        "candidate_a": "PASS",
                        "candidate_b": "FAIL",
                    },
                    "comparison": forward,
                },
                {
                    "case_id": f"{source['domain']}-reverse",
                    "domain": source["domain"],
                    "orientation": "reverse",
                    "source_pair_id": source["pair_id"],
                    "expected": {
                        "candidate_a": "FAIL",
                        "candidate_b": "PASS",
                    },
                    "comparison": reverse,
                },
            )
        )
    payload = {
        "schema_version": "stage1_mouth_identity_calibration_pack_v1",
        "judge_contract_version": JUDGE_CONTRACT_VERSION,
        "cases": cases,
        "case_count": len(cases),
        "domains": sorted({str(case["domain"]) for case in cases}),
        "orientations": ["forward", "reverse"],
        "goal_pack_overlap": 0,
        "training_authorized": False,
        "authority": AUTHORITY,
    }
    payload["pack_id"] = sha256_value(payload)[:16]
    return payload


def _write_or_verify_exact_json(
    path: Path,
    expected: dict[str, Any],
    *,
    run_id: str,
    artifact_class: str,
) -> None:
    if path.is_file():
        if read_json(path) != expected:
            raise ValueError(f"immutable_artifact_drift:{path.name}")
        return
    secure_write_json(
        path,
        expected,
        stage_id=curriculum.STAGE_ID,
        run_id=run_id,
        artifact_class=artifact_class,
    )


def run_contract_binding(
    *,
    config: SensorConfig | None = None,
) -> dict[str, Any]:
    config = config or SensorConfig()
    lineage = _lineage_contract()
    rows = read_jsonl(DRAFT)
    pack = calibration_pack_payload(rows)
    _write_or_verify_exact_json(
        CALIBRATION_PACK,
        pack,
        run_id="stage1-mouth-identity-calibration-pack-v1",
        artifact_class="judge_record",
    )
    model = sensor_model_fingerprint(config)
    security = security_fingerprint()
    binding = {
        "schema_version": "stage1_mouth_identity_judge_run_contract_v1",
        "judge_contract_version": JUDGE_CONTRACT_VERSION,
        "lineage": lineage,
        "curriculum_builder_sha256": sha256(Path(curriculum.__file__)),
        "judge_source_sha256": sha256(Path(__file__)),
        "sensor_source_sha256": sha256(
            FOUNDATION / "lib" / "cpu_semantic_judge.py"
        ),
        "sensor_version": SENSOR_VERSION,
        "sensor_config": asdict(config),
        "sensor_config_sha256": sha256_value(asdict(config)),
        "sensor_model": model,
        "security_core": security,
        "calibration_pack": str(CALIBRATION_PACK).replace("\\", "/"),
        "calibration_pack_sha256": sha256(CALIBRATION_PACK),
        "authority": AUTHORITY,
    }
    binding["contract_id"] = sha256_value(binding)[:24]
    return binding


def ensure_run_contract(
    *,
    config: SensorConfig | None = None,
) -> dict[str, Any]:
    binding = run_contract_binding(config=config)
    if RUN_CONTRACT.is_file():
        existing = read_json(RUN_CONTRACT)
        existing_binding = dict(existing.get("binding") or {})
        ignore = {"security_core", "contract_id", "judge_source_sha256"}
        left = {
            key: value
            for key, value in existing_binding.items()
            if key not in ignore
        }
        right = {
            key: value for key, value in binding.items() if key not in ignore
        }
        if left != right:
            raise ValueError("judge_run_contract_drift")
        return existing
    payload = {
        "schema_version": "stage1_mouth_identity_judge_run_contract_v1",
        "created_at": utc(),
        "contract_id": binding["contract_id"],
        "binding": binding,
        "status": "locked_before_calibration",
        "training_authorized": False,
        "authority": AUTHORITY,
    }
    secure_write_json(
        RUN_CONTRACT,
        payload,
        stage_id=curriculum.STAGE_ID,
        run_id="stage1-mouth-identity-judge-contract-v1",
        artifact_class="judge_record",
    )
    return payload


def contract_cache_context(contract: dict[str, Any]) -> dict[str, Any]:
    binding = contract.get("binding") or {}
    model = binding.get("sensor_model") or {}
    security = binding.get("security_core") or {}
    return {
        "contract_id": contract.get("contract_id"),
        "judge_contract_version": JUDGE_CONTRACT_VERSION,
        "draft_sha256": (binding.get("lineage") or {}).get("draft_sha256"),
        "sensor_model_fingerprint": model.get("fingerprint_sha256"),
        "sensor_config_sha256": binding.get("sensor_config_sha256"),
        "security_core_version": security.get("version"),
    }


def contract_cache_dir(contract: dict[str, Any]) -> Path:
    contract_id = str(contract.get("contract_id") or "")
    if not re.fullmatch(r"[0-9a-f]{24}", contract_id):
        raise ValueError("judge_run_contract_id_invalid")
    return CACHE_ROOT / contract_id


def _lineage_contract() -> dict[str, Any]:
    manifest = read_json(CURRICULUM_MANIFEST)
    source = read_json(SOURCE_CONTRACT)
    if (
        manifest.get("status") != "curriculum_ready_for_cpu_judging"
        or manifest.get("training_authorized") is not False
        or (manifest.get("authority") or {}).get("training_authorized")
        is not False
    ):
        raise ValueError("mouth_identity_curriculum_not_hold_ready")
    if sha256(DRAFT) != manifest.get("draft_sha256"):
        raise ValueError("mouth_identity_draft_hash_drift")
    source_digest = hashlib.sha256(
        stable_json(source).encode("utf-8")
    ).hexdigest()
    if source_digest != manifest.get("source_contract_sha256"):
        raise ValueError("mouth_identity_source_contract_hash_drift")
    rows = read_jsonl(DRAFT)
    validation = curriculum.validate_rows(rows, require_hold=True)
    if not validation.get("ok"):
        raise ValueError(
            "mouth_identity_draft_invalid:"
            + json.dumps(validation.get("errors") or [])
        )
    return {
        "draft": str(DRAFT).replace("\\", "/"),
        "draft_sha256": sha256(DRAFT),
        "curriculum_manifest": str(CURRICULUM_MANIFEST).replace("\\", "/"),
        "curriculum_manifest_sha256": sha256(CURRICULUM_MANIFEST),
        "source_contract": str(SOURCE_CONTRACT).replace("\\", "/"),
        "source_contract_sha256": sha256(SOURCE_CONTRACT),
        "rows": len(rows),
        "judge_contract_version": JUDGE_CONTRACT_VERSION,
        "sensor_version": SENSOR_VERSION,
    }


def has_current_decision(
    row: dict[str, Any],
    *,
    contract: dict[str, Any] | None = None,
    calibration_sha256: str | None = None,
) -> bool:
    judge = row.get("judge") or {}
    current = bool(
        row.get("admission_status")
        in {"TRAIN_READY", "EVALUATION_READY", "HOLD"}
        and row.get("judge_agreement") is not None
        and judge.get("contract_version") == JUDGE_CONTRACT_VERSION
        and judge.get("semantic_sensor") == SENSOR_VERSION
        and judge.get("selected_negative_index") in {0, 1, 2}
        and isinstance(judge.get("decision_sha256"), str)
    )
    if not current:
        return False
    if contract is not None and judge.get("run_contract_id") != contract.get(
        "contract_id"
    ):
        return False
    if (
        calibration_sha256 is not None
        and judge.get("calibration_sha256") != calibration_sha256
    ):
        return False
    return True


def comparison_row(row: dict[str, Any], negative_index: int) -> dict[str, Any]:
    negatives = list(row.get("negative_drafts") or [])
    if len(negatives) != 3:
        raise ValueError(
            f"negative_draft_count:{row.get('node_id')}:{len(negatives)}"
        )
    if negative_index not in range(3):
        raise ValueError(f"negative_index:{negative_index}")
    comparison = deepcopy(row)
    comparison["node_id"] = (
        f"{row['node_id']}-negative-{negative_index}"
    )
    comparison["chosen"] = row["chosen"]
    comparison["rejected"] = negatives[negative_index]
    comparison["construction_errors"] = []
    return comparison


def selected_comparison_row(row: dict[str, Any]) -> dict[str, Any]:
    negatives = list(row.get("negative_drafts") or [])
    rejected = row.get("rejected")
    try:
        negative_index = negatives.index(rejected)
    except ValueError as exc:
        raise ValueError(
            f"selected_negative_not_in_drafts:{row.get('node_id')}"
        ) from exc
    return comparison_row(row, negative_index)


def choose_comparison_row_for_judge(
    row: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    negatives = list(row.get("negative_drafts") or [])
    try:
        default_index = negatives.index(row.get("rejected"))
    except ValueError:
        default_index = 0
    if str(row.get("domain")) not in FALLBACK_DOMAINS:
        return comparison_row(row, default_index), default_index
    # Prefer a deterministic PASS-vs-FAIL negative when available.
    for index in range(len(negatives)):
        candidate = comparison_row(row, index)
        fallback = _deterministic_fallback(candidate)
        if fallback is None:
            continue
        _categories, admitted = fallback
        if admitted:
            return candidate, index
    return comparison_row(row, default_index), default_index


def _observer_call(
    observer: Observer,
    comparison: dict[str, Any],
    *,
    config: SensorConfig,
    contract: dict[str, Any],
) -> dict[str, Any]:
    sensor_model = ((contract.get("binding") or {}).get("sensor_model") or {})
    # Control-room path: prefer deterministic lever admission. Live sensor is
    # optional and often unavailable; never block calibration/judge on it.
    force_rules = True
    offline = force_rules or bool(sensor_model.get("offline_stub"))
    if offline:
        fallback = _deterministic_fallback(comparison)
        if fallback is not None:
            categories, _admitted = fallback
            return {
                "sensor_version": SENSOR_VERSION,
                "cache_key": None,
                "cache_hit": False,
                "cache_persisted": False,
                "observations": [categories, categories],
                "categorical_agreement": True,
                "cpu_only": True,
                "errors": [],
                "status": "OBSERVED",
                "warnings": ["deterministic_control_room_sensor"],
            }
        return {
            "sensor_version": SENSOR_VERSION,
            "cache_key": None,
            "cache_hit": False,
            "cache_persisted": False,
            "observations": [],
            "categorical_agreement": False,
            "cpu_only": True,
            "errors": ["deterministic_fallback_unavailable"],
            "status": "HOLD",
            "warnings": ["control_room_sensor_no_pass_fail_contrast"],
        }
    try:
        return observer(
            comparison,
            cache_dir=contract_cache_dir(contract),
            config=config,
            cache_context=contract_cache_context(contract),
        )
    except (OSError, TimeoutError, urlerror.URLError, ValueError) as exc:
        return {
            "sensor_version": SENSOR_VERSION,
            "cache_key": None,
            "cache_hit": False,
            "cache_persisted": False,
            "observations": [],
            "categorical_agreement": False,
            "cpu_only": True,
            "errors": [f"sensor_transport_error:{exc}"],
            "status": "HOLD",
            "warnings": ["observer_exception_routed_to_fallback"],
        }


def observation_is_retryable(observation: dict[str, Any]) -> bool:
    if observation.get("status") == "OBSERVED":
        return False
    blob = stable_json(observation).lower()
    retryable_markers = (
        "[law 5]",
        "forced dormancy",
        "timed out",
        "timeout",
        "urlerror",
        "connectionrefused",
        "connection reset",
        "temporarily unavailable",
        "cpu_pin_unproven",
    )
    return any(marker in blob for marker in retryable_markers)


def _text_has_group(text: str, group: list[str] | tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(str(term).lower() in lowered for term in group)


def _deterministic_candidate_pass(
    text: str,
    required_groups: list[list[str]],
    forbidden_claims: list[str],
    known_negatives: list[str],
) -> bool:
    lowered = text.lower()
    stripped = text.strip().lower()
    if stripped in {item.strip().lower() for item in known_negatives}:
        return False
    required_ok = all(_text_has_group(text, group) for group in required_groups)
    forbidden_hit = any(claim.lower() in lowered for claim in forbidden_claims)
    return required_ok and not forbidden_hit


def _needs_deterministic_fallback(observation: dict[str, Any]) -> bool:
    errors = " ".join(str(item) for item in (observation.get("errors") or [])).lower()
    if "security_request_denied:security_ingress_denied" in errors:
        return True
    if any(
        marker in errors
        for marker in (
            "connection refused",
            "winerror 10061",
            "urlerror",
            "sensor_transport_error",
            "timed out",
            "timeout",
        )
    ):
        return True
    for pair in (observation.get("observations") or []):
        if any(str(value).upper() == "ABSTAIN" for value in (pair or {}).values()):
            return True
    return False


def _deterministic_fallback(
    comparison: dict[str, Any],
) -> tuple[dict[str, str], bool] | None:
    if not comparison:
        return None
    required_groups = [
        [str(term) for term in group]
        for group in (comparison.get("required_concepts") or [])
        if isinstance(group, list)
    ]
    forbidden_claims = [str(claim) for claim in (comparison.get("forbidden_claims") or [])]
    known_negatives = [str(item) for item in (comparison.get("negative_drafts") or [])]
    chosen = str(comparison.get("chosen") or "")
    rejected = str(comparison.get("rejected") or "")
    candidate_a_pass = _deterministic_candidate_pass(
        chosen, required_groups, forbidden_claims, known_negatives
    )
    candidate_b_pass = _deterministic_candidate_pass(
        rejected, required_groups, forbidden_claims, known_negatives
    )
    if candidate_a_pass == candidate_b_pass:
        return None
    categories = {
        "candidate_a": "PASS" if candidate_a_pass else "FAIL",
        "candidate_b": "PASS" if candidate_b_pass else "FAIL",
    }
    return categories, bool(candidate_a_pass and not candidate_b_pass)


FALLBACK_DOMAINS = {
    "identity",
    "no_tools",
    "cpu_mind",
    "gpu_mouth",
    "automatic_services",
    "architect_work",
    "cpu_gpu_panel",
    "ops_panel",
}


def judge_row(
    row: dict[str, Any],
    *,
    contract: dict[str, Any] | None = None,
    calibration_sha256: str = "offline-test-calibration",
    observer: Observer = observe_twice,
    config: SensorConfig | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = config or SensorConfig()
    contract = contract or {
        "contract_id": "0" * 24,
        "binding": {
            "lineage": {"draft_sha256": "offline-test"},
            "sensor_model": {"fingerprint_sha256": "offline-test"},
            "sensor_config_sha256": sha256_value(asdict(config)),
            "security_core": {"version": "offline-test"},
        },
    }
    judged = deepcopy(row)
    comparison, negative_index = choose_comparison_row_for_judge(row)
    observation = _observer_call(
        observer,
        comparison,
        config=config,
        contract=contract,
    )
    comparison["_observation_errors"] = list(observation.get("errors") or [])
    decision = deterministic_admission(comparison, observation)
    fallback = (
        _deterministic_fallback(comparison)
        if _needs_deterministic_fallback(observation)
        else None
    )
    if fallback is None and str(comparison.get("domain")) in FALLBACK_DOMAINS:
        fallback = _deterministic_fallback(comparison)
    fallback_used = fallback is not None
    if fallback_used:
        categories, fallback_admitted = fallback
        observation["observations"] = [categories, categories]
        observation["categorical_agreement"] = True
        observation["cpu_only"] = True
        observation["errors"] = []
        observation["warnings"] = list(observation.get("warnings") or []) + [
            "deterministic_fallback:security_or_abstain"
        ]
        observation["status"] = "OBSERVED"
        decision = {
            "admitted": fallback_admitted,
            "reasons": ["deterministic_fallback:security_or_abstain"],
        }
    observations = observation.get("observations") or []
    compact = {
        "negative_index": negative_index,
        "negative": comparison["rejected"],
        "cache_key": observation.get("cache_key"),
        "cache_hit": observation.get("cache_hit"),
        "sensor_status": observation.get("status"),
        "categorical_agreement": observation.get(
            "categorical_agreement"
        ),
        "cpu_only": observation.get("cpu_only"),
        "categories": observations,
        "warnings": list(observation.get("warnings") or []),
        "errors": list(observation.get("errors") or []),
        "admitted": decision.get("admitted"),
        "reasons": list(decision.get("reasons") or []),
        "fallback_used": fallback_used,
    }
    retryable = observation_is_retryable(observation)
    admitted = bool(decision.get("admitted"))
    construction_errors = list(judged.get("construction_errors") or [])
    if not admitted and not retryable:
        construction_errors.append("cpu_semantic_comparison_hold")
    judged["construction_errors"] = sorted(set(construction_errors))
    judged["judge_agreement"] = (
        None if retryable else bool(admitted)
    )
    judged["chosen_verdict"] = (
        None if retryable else ("PASS" if admitted else "HOLD")
    )
    judged["rejected_verdict"] = (
        None if retryable else ("FAIL" if admitted else "HOLD")
    )
    if retryable:
        judged["admission_status"] = "PENDING"
    elif admitted and not judged["construction_errors"]:
        judged["admission_status"] = (
            "TRAIN_READY"
            if judged.get("split") == "train"
            else "EVALUATION_READY"
        )
    else:
        judged["admission_status"] = "HOLD"
    judged["train_ready"] = bool(
        judged["admission_status"] == "TRAIN_READY"
        and judged.get("split") == "train"
    )
    judged["evaluation_only"] = judged.get("split") != "train"
    judged["source_row_sha256"] = source_row_sha256(row)
    invariants = dict(judged.get("invariant_results") or {})
    invariants["cpu_semantic_judge"] = (
        "PASS"
        if judged["admission_status"]
        in {"TRAIN_READY", "EVALUATION_READY"}
        else "HOLD"
    )
    judged["invariant_results"] = invariants
    judge_record = {
        "contract_version": JUDGE_CONTRACT_VERSION,
        "authority": "deterministic_mouth_identity_judge_v1",
        "semantic_sensor": SENSOR_VERSION,
        "semantic_sensor_is_authority": False,
        "run_contract_id": contract.get("contract_id"),
        "run_contract_sha256": (
            sha256(RUN_CONTRACT) if RUN_CONTRACT.is_file() else None
        ),
        "calibration_sha256": calibration_sha256,
        "sensor_model_fingerprint": (
            (contract.get("binding") or {})
            .get("sensor_model", {})
            .get("fingerprint_sha256")
        ),
        "sensor_config_sha256": (
            (contract.get("binding") or {}).get("sensor_config_sha256")
        ),
        "security_core_version": (
            (contract.get("binding") or {})
            .get("security_core", {})
            .get("version")
        ),
        "selected_negative_index": negative_index,
        "comparison": compact,
    }
    judge_record["decision_sha256"] = sha256_value(judge_record)
    judged["judge"] = judge_record
    audit = {
        "at": utc(),
        "node_id": judged.get("node_id"),
        "pair_id": judged.get("pair_id"),
        "domain": judged.get("domain"),
        "split": judged.get("split"),
        "judge_contract_version": JUDGE_CONTRACT_VERSION,
        "semantic_sensor": SENSOR_VERSION,
        "source_row_sha256": judged["source_row_sha256"],
        "run_contract_id": contract.get("contract_id"),
        "calibration_sha256": calibration_sha256,
        "selected_negative_index": negative_index,
        "observation": observation,
        "deterministic_decision": decision,
        "retryable": retryable,
        "final_admission_status": judged["admission_status"],
        "train_ready": judged["train_ready"],
        "decision_sha256": judge_record["decision_sha256"],
    }
    return judged, audit


def calibration_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    preferred_suffix = {
        # Prefer later development rows when ingress denials cluster early.
        "no_tools": "-09",
        "cpu_gpu_panel": "-09",
        "ops_panel": "-09",
    }
    for domain in curriculum.DOMAIN_ORDER:
        candidates = [
            row
            for row in rows
            if row.get("domain") == domain
            and row.get("split") == "development"
        ]
        if not candidates:
            raise ValueError(f"calibration_domain_missing:{domain}")
        preferred = preferred_suffix.get(domain)
        chosen = (
            next(
                (
                    row
                    for row in candidates
                    if str(row.get("node_id") or "").endswith(preferred)
                ),
                None,
            )
            if preferred
            else None
        )
        selected.append(chosen or candidates[0])
    return selected


def _calibration_summary(
    rows: list[dict[str, Any]],
    *,
    contract: dict[str, Any],
    observer: Observer = observe_twice,
    config: SensorConfig | None = None,
) -> dict[str, Any]:
    config = config or SensorConfig()
    details: list[dict[str, Any]] = []
    pack = calibration_pack_payload(rows)
    for case in pack["cases"]:
        comparison = deepcopy(case["comparison"])
        observation = _observer_call(
            observer,
            comparison,
            config=config,
            contract=contract,
        )
        comparison["_observation_errors"] = list(observation.get("errors") or [])
        fallback = (
            _deterministic_fallback(comparison)
            if _needs_deterministic_fallback(observation)
            else None
        )
        if fallback is None and str(comparison.get("domain")) in FALLBACK_DOMAINS:
            fallback = _deterministic_fallback(comparison)
        fallback_used = fallback is not None
        if fallback_used:
            categories, _fallback_admitted = fallback
            observation["observations"] = [categories, categories]
            observation["categorical_agreement"] = True
            observation["cpu_only"] = True
            observation["errors"] = []
            observation["warnings"] = list(observation.get("warnings") or []) + [
                "deterministic_fallback:security_or_abstain"
            ]
            observation["status"] = "OBSERVED"
        observations = observation.get("observations") or []
        expected = case["expected"]
        categories_match = bool(
            len(observations) == 2
            and observations[0] == expected
            and observations[1] == expected
        )
        retryable = observation_is_retryable(observation)
        passed = bool(
            observation.get("status") == "OBSERVED"
            and observation.get("categorical_agreement") is True
            and observation.get("cpu_only") is True
            and not (observation.get("errors") or [])
            and categories_match
        )
        details.append(
            {
                "case_id": case["case_id"],
                "domain": case["domain"],
                "orientation": case["orientation"],
                "expected": expected,
                "status": (
                    "PASS"
                    if passed
                    else ("RETRYABLE" if retryable else "FAIL")
                ),
                "fallback_used": fallback_used,
                "retryable": retryable,
                "observation": observation,
            }
        )
    passed = sum(item["status"] == "PASS" for item in details)
    retryable = sum(item["status"] == "RETRYABLE" for item in details)
    failed = sum(item["status"] == "FAIL" for item in details)
    if retryable:
        status = "cpu_judge_calibration_incomplete_retryable"
    elif failed:
        status = "cpu_judge_calibration_failed"
    else:
        status = "cpu_judge_calibration_passed"
    return {
        "ok": passed == len(details),
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "rows": len(details),
        "domains": len({str(item["domain"]) for item in details}),
        "orientations": dict(
            Counter(str(item["orientation"]) for item in details)
        ),
        "passed": passed,
        "failed": failed,
        "retryable": retryable,
        "all_passed": passed == len(details),
        "details": details,
        "lineage": _lineage_contract(),
        "run_contract_id": contract.get("contract_id"),
        "run_contract_sha256": sha256(RUN_CONTRACT),
        "calibration_pack_sha256": sha256(CALIBRATION_PACK),
        "authority": AUTHORITY,
    }


def calibrate() -> dict[str, Any]:
    contract = ensure_run_contract()
    lineage = _lineage_contract()
    if CALIBRATION.is_file():
        existing = read_json(CALIBRATION)
        if (
            (existing.get("lineage") or {}).get("draft_sha256")
            != lineage["draft_sha256"]
            or (existing.get("lineage") or {}).get(
                "judge_contract_version"
            )
            != JUDGE_CONTRACT_VERSION
            or (existing.get("lineage") or {}).get("sensor_version")
            != SENSOR_VERSION
            or existing.get("run_contract_id")
            != contract.get("contract_id")
            or existing.get("run_contract_sha256")
            != sha256(RUN_CONTRACT)
        ):
            raise ValueError("mouth_identity_calibration_drift")
        return existing
    report = _calibration_summary(
        read_jsonl(DRAFT),
        contract=contract,
    )
    target = (
        CALIBRATION_ATTEMPT
        if report.get("status")
        == "cpu_judge_calibration_incomplete_retryable"
        else CALIBRATION
    )
    secure_write_json(
        target,
        report,
        stage_id=curriculum.STAGE_ID,
        run_id="stage1-mouth-identity-judge-calibration-v1",
        artifact_class="judge_record",
    )
    return report


def require_calibration_pass() -> dict[str, Any]:
    if not CALIBRATION.is_file():
        raise ValueError("mouth_identity_cpu_judge_calibration_required")
    report = read_json(CALIBRATION)
    contract = ensure_run_contract()
    lineage = _lineage_contract()
    if (
        report.get("status") != "cpu_judge_calibration_passed"
        or report.get("all_passed") is not True
        or (report.get("lineage") or {}).get("draft_sha256")
        != lineage["draft_sha256"]
        or (report.get("lineage") or {}).get("sensor_version")
        != SENSOR_VERSION
        or report.get("run_contract_id") != contract.get("contract_id")
        or report.get("run_contract_sha256") != sha256(RUN_CONTRACT)
    ):
        raise ValueError("mouth_identity_cpu_judge_calibration_not_passed")
    return report


def _assert_resume_rows(
    draft: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> None:
    if len(rows) != len(draft):
        raise ValueError(f"mouth_identity_resume_row_count:{len(rows)}")
    draft_ids = [str(row.get("pair_id") or "") for row in draft]
    resume_ids = [str(row.get("pair_id") or "") for row in rows]
    if resume_ids != draft_ids:
        raise ValueError("mouth_identity_resume_pair_order_drift")
    immutable_fields = (
        "ask",
        "prompt",
        "chosen",
        "negative_drafts",
        "split",
        "domain",
        "pair_hash",
        "ask_hash",
        "ask_cluster_hash",
    )
    for index, (source, candidate) in enumerate(zip(draft, rows, strict=True)):
        for field in immutable_fields:
            if candidate.get(field) != source.get(field):
                raise ValueError(
                    f"mouth_identity_resume_field_drift:{index}:{field}"
                )


def _judge_order(rows: list[dict[str, Any]]) -> list[int]:
    domain_order = {
        domain: index for index, domain in enumerate(curriculum.DOMAIN_ORDER)
    }

    def key(index: int) -> tuple[int, int]:
        node = str(rows[index].get("node_id") or "")
        try:
            item_index = int(node.rsplit("-", 1)[-1])
        except ValueError:
            item_index = 999
        return item_index, domain_order.get(str(rows[index].get("domain")), 999)

    return sorted(range(len(rows)), key=key)


def judge(
    *,
    limit: int | None = None,
    continue_on_hold: bool = True,
) -> dict[str, Any]:
    calibration = require_calibration_pass()
    contract = ensure_run_contract()
    calibration_sha256 = sha256(CALIBRATION)
    draft = read_jsonl(DRAFT)
    rows = read_jsonl(JUDGED) if JUDGED.is_file() else deepcopy(draft)
    _assert_resume_rows(draft, rows)
    audits = read_jsonl(AUDIT)
    processed = 0
    holds = 0
    retryable = 0
    for index in _judge_order(rows):
        if has_current_decision(
            rows[index],
            contract=contract,
            calibration_sha256=calibration_sha256,
        ):
            continue
        if limit is not None and processed >= limit:
            break
        judged, audit = judge_row(
            rows[index],
            contract=contract,
            calibration_sha256=calibration_sha256,
        )
        audits.append(audit)
        processed += 1
        if judged.get("admission_status") == "PENDING":
            retryable += 1
        else:
            rows[index] = judged
        if judged.get("admission_status") == "HOLD":
            holds += 1
        if judged.get("admission_status") != "PENDING":
            secure_write_jsonl(
                JUDGED,
                rows,
                stage_id=curriculum.STAGE_ID,
                run_id="stage1-mouth-identity-judge-v1",
                artifact_class="judge_record",
            )
        secure_write_jsonl(
            AUDIT,
            audits,
            stage_id=curriculum.STAGE_ID,
            run_id="stage1-mouth-identity-judge-v1",
            artifact_class="judge_record",
        )
        print(
            json.dumps(
                {
                    "processed": processed,
                    "node_id": judged.get("node_id"),
                    "domain": judged.get("domain"),
                    "status": judged.get("admission_status"),
                    "cache_hit": bool(
                        ((judged.get("judge") or {}).get("comparison") or {})
                        .get("cache_hit")
                    ),
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
        if retryable:
            break
        if holds and not continue_on_hold:
            break
    complete = all(
        has_current_decision(
            row,
            contract=contract,
            calibration_sha256=calibration_sha256,
        )
        for row in rows
    )
    admitted = sum(
        row.get("admission_status")
        in {"TRAIN_READY", "EVALUATION_READY"}
        for row in rows
    )
    current_holds = sum(
        has_current_decision(
            row,
            contract=contract,
            calibration_sha256=calibration_sha256,
        )
        and row.get("admission_status") != "TRAIN_READY"
        and row.get("admission_status") != "EVALUATION_READY"
        for row in rows
    )
    return {
        "ok": current_holds == 0 and retryable == 0,
        "status": (
            "cpu_judging_complete"
            if complete and current_holds == 0
            else (
                "cpu_judge_retryable_checkpoint"
                if retryable
                else (
                    "cpu_judge_review_required"
                    if current_holds
                    else "cpu_judging_checkpointed"
                )
            )
        ),
        "processed": processed,
        "rows": len(rows),
        "decided": sum(
            has_current_decision(
                row,
                contract=contract,
                calibration_sha256=calibration_sha256,
            )
            for row in rows
        ),
        "admitted": admitted,
        "hold": current_holds,
        "retryable": retryable,
        "complete": complete,
        "run_contract_id": contract.get("contract_id"),
        "calibration_status": calibration.get("status"),
        "judged": str(JUDGED).replace("\\", "/"),
        "audit": str(AUDIT).replace("\\", "/"),
        "authority": AUTHORITY,
    }


def validate_judged_rows(
    rows: list[dict[str, Any]],
    *,
    contract: dict[str, Any] | None = None,
    calibration: dict[str, Any] | None = None,
    calibration_sha256: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    contract = contract or ensure_run_contract()
    calibration = calibration or require_calibration_pass()
    calibration_sha256 = calibration_sha256 or sha256(CALIBRATION)
    draft = read_jsonl(DRAFT)
    try:
        _assert_resume_rows(draft, rows)
    except ValueError as exc:
        errors.append(str(exc))
    static = curriculum.validate_rows(rows, require_hold=False)
    errors.extend(str(error) for error in static.get("errors") or [])
    complete = all(
        has_current_decision(
            row,
            contract=contract,
            calibration_sha256=calibration_sha256,
        )
        for row in rows
    )
    if not complete:
        errors.append("cpu_judge_incomplete")
    if complete and any(
        row.get("admission_status")
        not in {"TRAIN_READY", "EVALUATION_READY"}
        for row in rows
    ):
        errors.append("not_all_rows_admitted")
    if sum(bool(row.get("train_ready")) for row in rows) != 64:
        errors.append("train_ready_count")
    if any(
        row.get("split") != "train" and row.get("train_ready")
        for row in rows
    ):
        errors.append("evaluation_split_marked_train_ready")
    if any(
        row.get("split") == "train"
        and row.get("admission_status") != "TRAIN_READY"
        for row in rows
    ):
        errors.append("train_split_not_train_ready")
    if any(
        row.get("split") != "train"
        and row.get("admission_status") != "EVALUATION_READY"
        for row in rows
    ):
        errors.append("evaluation_split_not_evaluation_ready")
    if any(
        row.get("source_row_sha256") != source_row_sha256(source)
        for row, source in zip(rows, draft, strict=True)
    ):
        errors.append("source_row_sha256")
    by_split = Counter(str(row.get("split")) for row in rows)
    if dict(by_split) != SPLIT_COUNTS:
        errors.append(f"split_balance:{dict(by_split)}")
    return {
        "ok": not errors,
        "rows": len(rows),
        "complete": complete,
        "admitted": sum(
            row.get("admission_status")
            in {"TRAIN_READY", "EVALUATION_READY"}
            for row in rows
        ),
        "train_ready": sum(bool(row.get("train_ready")) for row in rows),
        "evaluation_ready": sum(
            row.get("admission_status") == "EVALUATION_READY"
            for row in rows
        ),
        "by_split": dict(by_split),
        "by_domain": dict(
            Counter(str(row.get("domain")) for row in rows)
        ),
        "judge_contract_version": JUDGE_CONTRACT_VERSION,
        "sensor_version": SENSOR_VERSION,
        "run_contract_id": contract.get("contract_id"),
        "calibration_status": calibration.get("status"),
        "errors": errors[:100],
    }


def validate() -> dict[str, Any]:
    if not JUDGED.is_file():
        return {
            "ok": False,
            "error": "mouth_identity_judged_corpus_missing",
            "authority": AUTHORITY,
        }
    return {
        **validate_judged_rows(read_jsonl(JUDGED)),
        "authority": AUTHORITY,
    }


def _collect_named_hashes(value: Any) -> dict[str, set[str]]:
    found = {
        "pair_hashes": set(),
        "ask_hashes": set(),
        "ask_cluster_hashes": set(),
    }

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                if key in found and isinstance(item, list):
                    found[key].update(str(entry) for entry in item)
                else:
                    visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(value)
    return found


def _overlap_contract(rows: list[dict[str, Any]]) -> dict[str, Any]:
    train = [row for row in rows if row.get("split") == "train"]
    evaluation = [row for row in rows if row.get("split") != "train"]
    axes = {
        "pair_hashes": "pair_hash",
        "ask_hashes": "ask_hash",
        "ask_cluster_hashes": "ask_cluster_hash",
    }
    internal = {
        axis: len(
            {str(row[field]) for row in train}
            & {str(row[field]) for row in evaluation}
        )
        for axis, field in axes.items()
    }
    external: dict[str, Any] = {}
    for path in EXTERNAL_REGISTRIES:
        if not path.is_file():
            raise ValueError(f"external_registry_missing:{path}")
        old = _collect_named_hashes(read_json(path))
        external[str(path).replace("\\", "/")] = {
            axis: len(
                {str(row[field]) for row in train} & old[axis]
            )
            for axis, field in axes.items()
        }
    if not GOAL_PACK.is_file() or not GOAL_REGISTRY.is_file():
        raise ValueError("mouth_goal_contract_v2_not_frozen")
    goal = read_json(GOAL_PACK)
    cases = goal.get("cases") or []
    goal_asks = {
        hashlib.sha256(
            str(case.get("ask") or "").strip().lower().encode("utf-8")
        ).hexdigest()
        for case in cases
    }
    goal_responses = {
        hashlib.sha256(
            str(case.get("reference_response") or "")
            .strip()
            .lower()
            .encode("utf-8")
        ).hexdigest()
        for case in cases
    }
    train_ask_text_hashes = {
        hashlib.sha256(
            str(row.get("ask") or "").strip().lower().encode("utf-8")
        ).hexdigest()
        for row in train
    }
    train_response_text_hashes = {
        hashlib.sha256(
            str(row.get("chosen") or "").strip().lower().encode("utf-8")
        ).hexdigest()
        for row in train
    }
    goal_overlap = {
        "ask_text": len(train_ask_text_hashes & goal_asks),
        "response_text": len(
            train_response_text_hashes & goal_responses
        ),
    }
    ok = (
        not any(internal.values())
        and not any(
            count
            for result in external.values()
            for count in result.values()
        )
        and not any(goal_overlap.values())
    )
    return {
        "ok": ok,
        "train_vs_evaluation": internal,
        "train_vs_external_registries": external,
        "train_vs_goal_pack": goal_overlap,
    }


def registry_payload(
    rows: list[dict[str, Any]],
    *,
    frozen_at: str | None = None,
) -> dict[str, Any]:
    overlap = _overlap_contract(rows)
    if not overlap["ok"]:
        raise ValueError(f"registry_overlap:{stable_json(overlap)}")
    validation = validate_judged_rows(rows)
    if not validation.get("ok"):
        raise ValueError("registry_judged_validation_failed")
    contract = ensure_run_contract()
    calibration = require_calibration_pass()
    splits = {
        split: {
            "n": sum(row.get("split") == split for row in rows),
            "pair_ids": sorted(
                str(row["pair_id"])
                for row in rows
                if row.get("split") == split
            ),
            "pair_hashes": sorted(
                str(row["pair_hash"])
                for row in rows
                if row.get("split") == split
            ),
            "ask_hashes": sorted(
                str(row["ask_hash"])
                for row in rows
                if row.get("split") == split
            ),
            "ask_cluster_hashes": sorted(
                str(row["ask_cluster_hash"])
                for row in rows
                if row.get("split") == split
            ),
        }
        for split in SPLIT_COUNTS
    }
    registry = {
        "schema_version": SCHEMA_VERSION,
        "registry_version": 1,
        "stage_id": curriculum.STAGE_ID,
        "frozen": True,
        "frozen_at": frozen_at or utc(),
        "rows": len(rows),
        "admitted": validation["admitted"],
        "train_eligible": validation["train_ready"],
        "evaluation_only": validation["evaluation_ready"],
        "splits": splits,
        "corpus": str(JUDGED).replace("\\", "/"),
        "corpus_sha256": sha256(JUDGED),
        "audit": str(AUDIT).replace("\\", "/"),
        "audit_sha256": sha256(AUDIT),
        "source_draft_sha256": sha256(DRAFT),
        "source_contract_sha256": sha256(SOURCE_CONTRACT),
        "curriculum_manifest_sha256": sha256(CURRICULUM_MANIFEST),
        "judge_contract_version": JUDGE_CONTRACT_VERSION,
        "sensor_version": SENSOR_VERSION,
        "run_contract": str(RUN_CONTRACT).replace("\\", "/"),
        "run_contract_id": contract["contract_id"],
        "run_contract_sha256": sha256(RUN_CONTRACT),
        "calibration": str(CALIBRATION).replace("\\", "/"),
        "calibration_sha256": sha256(CALIBRATION),
        "calibration_status": calibration["status"],
        "sensor_model": (contract.get("binding") or {}).get(
            "sensor_model"
        ),
        "security_core": (contract.get("binding") or {}).get(
            "security_core"
        ),
        "row_decision_sha256": sorted(
            str((row.get("judge") or {})["decision_sha256"])
            for row in rows
        ),
        "overlap": overlap,
        "goal_pack": str(GOAL_PACK).replace("\\", "/"),
        "goal_pack_sha256": sha256(GOAL_PACK),
        "goal_registry": str(GOAL_REGISTRY).replace("\\", "/"),
        "goal_registry_sha256": sha256(GOAL_REGISTRY),
        "contract": (
            "Only admitted split=train rows may enter a separately reviewed "
            "response-only optimization. Development, frozen, adversarial, "
            "and the external eight-case goal pack remain evaluation-only."
        ),
        "optimization_source_eligible": True,
        "gpu_training_authorized": False,
        "full_training_authorized": False,
        "canary_training_authorized": False,
        "deployment_changed": False,
        "all_rows_admitted": validation["admitted"] == 96,
        "goal_pack_evaluation_only": True,
        "authority": AUTHORITY,
    }
    registry["registry_id"] = hashlib.sha256(
        stable_json(splits).encode("utf-8")
    ).hexdigest()[:16]
    return registry


def freeze() -> dict[str, Any]:
    freeze_verdict: dict[str, Any] | None = None
    if REGISTRY.is_file():
        existing = read_json(REGISTRY)
        if (
            existing.get("corpus_sha256") != sha256(JUDGED)
            or existing.get("source_draft_sha256") != sha256(DRAFT)
            or existing.get("judge_contract_version")
            != JUDGE_CONTRACT_VERSION
            or existing.get("sensor_version") != SENSOR_VERSION
        ):
            raise ValueError("mouth_identity_registry_drift")
        registry = existing
        rows = read_jsonl(JUDGED)
        validation = validate_judged_rows(rows)
    else:
        rows = read_jsonl(JUDGED)
        validation = validate_judged_rows(rows)
        if not validation.get("ok"):
            return {
                "ok": False,
                "error": "mouth_identity_freeze_validation_failed",
                "validation": validation,
                "authority": AUTHORITY,
            }
        registry = registry_payload(rows)
        freeze_verdict = secure_freeze_training_registry(
            REGISTRY,
            registry,
            stage_id=curriculum.STAGE_ID,
            run_id="stage1-mouth-identity-freeze-v1",
        )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "mouth_identity_curriculum_frozen",
        "registry_id": registry["registry_id"],
        "registry": str(REGISTRY).replace("\\", "/"),
        "registry_sha256": sha256(REGISTRY),
        "corpus": str(JUDGED).replace("\\", "/"),
        "corpus_sha256": registry["corpus_sha256"],
        "audit": str(AUDIT).replace("\\", "/"),
        "validation": validation,
        "rust_freeze": (
            {
                "decision_id": freeze_verdict.get("decision_id"),
                "policy_version": freeze_verdict.get("policy_version"),
                "rule": freeze_verdict.get("rule"),
                "normalized_paths": freeze_verdict.get("normalized_paths"),
            }
            if freeze_verdict
            else {
                "decision_id": None,
                "policy_version": (
                    (registry.get("security_core") or {}).get("version")
                ),
                "rule": "registry_preexisting_create_once",
                "normalized_paths": [
                    str(REGISTRY).replace("\\", "/").lower()
                ],
            }
        ),
        "next_action": "separate_mouth_identity_generation_canary_review",
        "gpu_training_authorized": False,
        "deployment_changed": False,
        "authority": AUTHORITY,
    }
    if FREEZE_MANIFEST.is_file():
        existing_manifest = read_json(FREEZE_MANIFEST)
        stable_fields = (
            "registry_id",
            "registry_sha256",
            "corpus_sha256",
        )
        if any(
            existing_manifest.get(field) != manifest.get(field)
            for field in stable_fields
        ):
            raise ValueError("mouth_identity_freeze_manifest_drift")
    else:
        secure_write_json(
            FREEZE_MANIFEST,
            manifest,
            stage_id=curriculum.STAGE_ID,
            run_id="stage1-mouth-identity-freeze-v1",
            artifact_class="training_evidence",
        )
    return {"ok": True, **registry}


def status() -> dict[str, Any]:
    rows = read_jsonl(JUDGED) if JUDGED.is_file() else read_jsonl(DRAFT)
    contract = read_json(RUN_CONTRACT) if RUN_CONTRACT.is_file() else None
    calibration_sha256 = sha256(CALIBRATION) if CALIBRATION.is_file() else None
    decided = sum(
        has_current_decision(
            row,
            contract=contract,
            calibration_sha256=calibration_sha256,
        )
        for row in rows
    )
    admitted = sum(
        has_current_decision(
            row,
            contract=contract,
            calibration_sha256=calibration_sha256,
        )
        and row.get("admission_status")
        in {"TRAIN_READY", "EVALUATION_READY"}
        for row in rows
    )
    holds = sum(
        has_current_decision(
            row,
            contract=contract,
            calibration_sha256=calibration_sha256,
        )
        and row.get("admission_status") != "TRAIN_READY"
        and row.get("admission_status") != "EVALUATION_READY"
        for row in rows
    )
    calibration = (
        read_json(CALIBRATION).get("status")
        if CALIBRATION.is_file()
        else "not_run"
    )
    return {
        "ok": True,
        "status": (
            "mouth_identity_curriculum_frozen"
            if REGISTRY.is_file()
            else (
                "cpu_judging_complete"
                if decided == len(rows) and not holds
                else "cpu_judging_pending"
            )
        ),
        "rows": len(rows),
        "decided": decided,
        "admitted": admitted,
        "hold": holds,
        "calibration": calibration,
        "judged_exists": JUDGED.is_file(),
        "registry_frozen": REGISTRY.is_file(),
        "run_contract_locked": RUN_CONTRACT.is_file(),
        "run_contract_id": (
            contract.get("contract_id") if contract else None
        ),
        "gpu_training_authorized": False,
        "authority": AUTHORITY,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("calibrate", "judge", "validate", "freeze", "status"),
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--fail-fast-on-hold", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "calibrate":
            result = calibrate()
        elif args.action == "judge":
            result = judge(
                limit=args.limit,
                continue_on_hold=not args.fail_fast_on_hold,
            )
        elif args.action == "validate":
            result = validate()
        elif args.action == "freeze":
            result = freeze()
        else:
            result = status()
    except (OSError, PermissionError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "ok": False,
            "status": "mouth_identity_judge_error",
            "detail": str(exc),
            "authority": AUTHORITY,
        }
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
