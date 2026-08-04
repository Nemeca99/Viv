"""GPU/API-free CPU cold-start and deterministic replay proof.

The harness consumes only a frozen fixture. It does not load a model, read live
RID state, write artifacts, call external services, render prose, or execute a
decision effect.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from lib.cpu_enterprise_policy import evaluate_request as evaluate_enterprise
from lib.cpu_infra_ops_judge import evaluate_slos
from lib.cpu_sandbox_boundary import evaluate_request as evaluate_sandbox
from lib.rid_recursive_shadow import verify as verify_rid_shadow

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fixtures" / "cpu_cold_start_v1.json"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != "cpu_cold_start_fixture_v1":
        raise ValueError("invalid_cpu_cold_start_fixture")
    required = {"fixture_id", "authoritative_state", "sandbox_request", "infra", "enterprise", "model_availability", "provenance"}
    if not required.issubset(data):
        raise ValueError("fixture_missing_required_sections")
    return data


def build_decision_envelope(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a frozen fixture and return a canonical machine envelope."""
    model = fixture["model_availability"]
    if model != {"gpu": False, "api": False, "model_loaded": False}:
        raise ValueError("gpu_or_api_must_be_unavailable_for_cold_start")

    state = fixture["authoritative_state"]
    rid = state["rid"]
    rid_result = verify_rid_shadow(
        rid["triad"],
        tick=int(rid["tick"]),
        phase=str(rid["phase"]),
        tolerance=float(rid.get("tolerance", 1e-10)),
    ).to_dict()
    sandbox_result = evaluate_sandbox(dict(fixture["sandbox_request"]))
    infra_cfg = fixture["infra"]
    infra_result = evaluate_slos(dict(infra_cfg["metrics"]), dict(infra_cfg["thresholds"]))
    enterprise_cfg = fixture["enterprise"]
    enterprise_read = evaluate_enterprise(
        enterprise_cfg["read_operation"],
        explicit_consent=bool(enterprise_cfg.get("explicit_consent", False)),
        authority=str(enterprise_cfg.get("authority", "none")),
        payload=enterprise_cfg.get("payload"),
        timestamp=str(enterprise_cfg["timestamp"]),
    )
    enterprise_external = evaluate_enterprise(
        enterprise_cfg["external_operation"],
        explicit_consent=bool(enterprise_cfg.get("explicit_consent", False)),
        authority=str(enterprise_cfg.get("authority", "none")),
        payload=enterprise_cfg.get("payload"),
        timestamp=str(enterprise_cfg["timestamp"]),
    )

    checks = {
        "rid_shadow": rid_result,
        "sandbox_policy": sandbox_result,
        "infra_policy": infra_result,
        "enterprise_read_policy": enterprise_read,
        "enterprise_external_policy": enterprise_external,
    }
    authorized = bool(
        rid_result.get("ok")
        and infra_result.get("state") == "PASS"
        and sandbox_result.get("state") == "VERIFIED_PLAN_ONLY"
        and enterprise_read.get("allowed") is True
        and enterprise_external.get("allowed") is False
    )
    body: dict[str, Any] = {
        "schema_version": "cpu_decision_envelope_v1",
        "mode": "cpu_cold_start_replay",
        "fixture_id": fixture["fixture_id"],
        "model_availability": model,
        "authoritative_state": state,
        "checks": checks,
        "decision": {
            "state": "AUTHORIZED_READ_ONLY_CPU_DECISION" if authorized else "DENIED",
            "action": "observe" if authorized else "abstain",
            "effect_authorized": False,
            "reason_codes": ["rid_verified", "heartbeat_verified", "sandbox_plan_only", "infra_slos_pass", "external_effect_denied"] if authorized else ["cpu_check_failed"],
        },
        "rendering": {"natural_language": False, "mouth_invoked": False, "gpu_invoked": False, "api_invoked": False},
        "side_effects": {"writes": False, "external_calls": False, "live_state_mutated": False, "master_rid_mutated": False, "training": False, "deployment": False},
        "provenance": {
            "fixture_source": fixture["provenance"],
            "fixture_sha256": digest(fixture),
            "authoritative_state_sha256": digest(state),
            "component_digests": {name: digest(value) for name, value in checks.items()},
        },
    }
    body["provenance"]["audit_digest"] = digest(body)
    return body


def replay_fixture(path: Path = FIXTURE_PATH) -> tuple[dict[str, Any], dict[str, Any]]:
    fixture = load_fixture(path)
    return build_decision_envelope(fixture), build_decision_envelope(fixture)
