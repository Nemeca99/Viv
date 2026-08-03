#!/usr/bin/env python3
"""Lock the Stage-1 parity remeasurement without reopening pairwise admission."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
VIV = FOUNDATION.parent
for candidate in (FOUNDATION, VIV):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.training_security import secure_write_json, secure_write_text  # noqa: E402
from scripts.evaluate_openaster_parity import PARITY_EVAL_MODEL_ROLE  # noqa: E402

STAGE1 = (
    FOUNDATION / "artifacts" / "auto" / "openaster_training_tree" / "stage1"
)
REPORTS = FOUNDATION / "artifacts" / "auto" / "openaster_parity" / "reports"
DEFAULT_QWEN = REPORTS / "qwen_stage1_dev_parity_v3.json"
DEFAULT_CANDIDATE = REPORTS / "candidate_stage1_all_parity_v3.json"
PAIRWISE_DECISION = STAGE1 / "stage1_candidate_decision_v1.json"
OUT_JSON = STAGE1 / "stage1_parity_remeasure_v1.json"
OUT_MD = STAGE1 / "stage1_parity_remeasure_v1.md"

STAGE1_SECTIONS = ("stage1_dev", "stage1_frozen", "stage1_adversarial")
MAX_UNEXPLAINED_DENY_RATE = 0.02


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"not_object:{path}")
    return payload


def section_summary(report: dict[str, Any], key: str) -> dict[str, Any]:
    section = report.get(key)
    if not isinstance(section, dict):
        raise ValueError(f"missing_section:{key}")
    summary = section.get("summary")
    rows = section.get("rows")
    if not isinstance(summary, dict) or not isinstance(rows, list):
        raise ValueError(f"malformed_section:{key}")
    return {
        "summary": summary,
        "rows": len(rows),
        "measurement_status": section.get("measurement_status")
        or summary.get("measurement_status"),
    }


def compact(section: dict[str, Any]) -> dict[str, Any]:
    summary = section["summary"]
    return {
        "n": int(summary.get("n") or 0),
        "measurement_n": int(summary.get("measurement_n") or 0),
        "generated_n": int(summary.get("generated_n") or 0),
        "raw_mind_pass_rate": float(summary.get("raw_mind_pass_rate") or 0.0),
        "conditional_mind_pass_rate": float(summary.get("mind_pass_rate") or 0.0),
        "raw_valid_speech_rate": float(
            summary.get("raw_valid_speech_rate") or 0.0
        ),
        "conditional_valid_speech_rate": float(
            summary.get("valid_speech_rate") or 0.0
        ),
        "security_dormancy_denied": int(
            summary.get("security_dormancy_denied") or 0
        ),
        "security_content_denied": int(
            summary.get("security_content_denied") or 0
        ),
        "security_request_denied_rate": float(
            summary.get("security_request_denied_rate") or 0.0
        ),
        "unexplained_security_deny_rate": float(
            summary.get("unexplained_security_deny_rate") or 0.0
        ),
        "measurement_status": section["measurement_status"],
        "collapse_cases": int(summary.get("collapse_cases") or 0),
        "numeric_prefix_cases": int(summary.get("numeric_prefix_cases") or 0),
    }


def build(
    *,
    qwen_path: Path,
    candidate_path: Path,
    decision_path: Path,
) -> dict[str, Any]:
    qwen = load_json(qwen_path)
    candidate = load_json(candidate_path)
    decision = load_json(decision_path)
    qwen_section = section_summary(qwen, "stage1_dev")
    candidate_sections = {
        key: section_summary(candidate, key) for key in STAGE1_SECTIONS
    }
    qwen_stats = compact(qwen_section)
    candidate_stats = {
        key: compact(value) for key, value in candidate_sections.items()
    }

    roles = {
        "qwen": qwen.get("eval_model_role"),
        "candidate": candidate.get("eval_model_role"),
        "required": PARITY_EVAL_MODEL_ROLE,
    }
    same_role = (
        roles["qwen"] == roles["candidate"] == roles["required"]
    )
    complete = (
        qwen_stats["n"] == qwen_stats["measurement_n"] == qwen_section["rows"]
        and all(
            stats["n"] == stats["measurement_n"] == candidate_sections[key]["rows"]
            for key, stats in candidate_stats.items()
        )
    )
    no_dormancy_contamination = (
        qwen_stats["security_dormancy_denied"] == 0
        and all(
            stats["security_dormancy_denied"] == 0
            for stats in candidate_stats.values()
        )
    )
    unexplained_rates = {
        "qwen_stage1_dev": qwen_stats["unexplained_security_deny_rate"],
        **{
            key: stats["unexplained_security_deny_rate"]
            for key, stats in candidate_stats.items()
        },
    }
    max_unexplained = max(unexplained_rates.values(), default=1.0)
    candidate_dev_delta = abs(
        candidate_stats["stage1_dev"]["unexplained_security_deny_rate"]
        - qwen_stats["unexplained_security_deny_rate"]
    )
    clean_statuses = (
        qwen_stats["measurement_status"] == "clean"
        and all(
            stats["measurement_status"] == "clean"
            for stats in candidate_stats.values()
        )
    )
    measurement_clean = all(
        (
            same_role,
            complete,
            no_dormancy_contamination,
            clean_statuses,
            max_unexplained <= MAX_UNEXPLAINED_DENY_RATE,
            candidate_dev_delta <= MAX_UNEXPLAINED_DENY_RATE,
        )
    )
    prior_rejection_locked = decision.get("decision") == "REJECTED"
    proceed = measurement_clean and prior_rejection_locked
    return {
        "ok": proceed,
        "at": utc(),
        "schema_version": "stage1_parity_remeasure_v1",
        "purpose": "evaluator_validation_only",
        "inputs": {
            "qwen": {
                "path": str(qwen_path).replace("\\", "/"),
                "sha256": sha256(qwen_path),
            },
            "candidate": {
                "path": str(candidate_path).replace("\\", "/"),
                "sha256": sha256(candidate_path),
            },
            "pairwise_decision": {
                "path": str(decision_path).replace("\\", "/"),
                "sha256": sha256(decision_path),
                "decision": decision.get("decision"),
            },
        },
        "eval_identity": roles,
        "qwen_stage1_dev": qwen_stats,
        "candidate_packs": candidate_stats,
        "security_measurement": {
            "same_eval_role": same_role,
            "complete_measurement": complete,
            "clean_statuses": clean_statuses,
            "no_dormancy_contamination": no_dormancy_contamination,
            "unexplained_deny_rates": unexplained_rates,
            "max_unexplained_deny_rate": max_unexplained,
            "candidate_dev_vs_qwen_unexplained_deny_delta": candidate_dev_delta,
            "allowed_max_unexplained_deny_rate": MAX_UNEXPLAINED_DENY_RATE,
            "measurement_clean": measurement_clean,
        },
        "admission_decision_unchanged": "REJECTED",
        "pairwise_candidate_reopened": False,
        "next_action": (
            "proceed_to_stage1_generation_v1"
            if proceed
            else "stop_and_repair_parity_measurement"
        ),
        "authority": {
            "live_backend_unchanged": "qwen_gguf",
            "deployment_changed": False,
            "learning_admission_withheld": True,
            "master_routing_authorized": False,
            "gates_action": False,
            "auto_deploy": False,
        },
    }


def to_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Stage-1 parity remeasurement v1",
        "",
        f"- Measurement clean: **{payload['security_measurement']['measurement_clean']}**",
        f"- Pairwise admission: **{payload['admission_decision_unchanged']}**",
        f"- Next action: `{payload['next_action']}`",
        f"- Shared eval role: `{payload['eval_identity']['required']}`",
        "",
        "## Scores",
        "",
        "| Pack | Raw mind | Ingress-clean mind | Request deny | Dormancy deny |",
        "|---|---:|---:|---:|---:|",
    ]
    rows = {
        "qwen_stage1_dev": payload["qwen_stage1_dev"],
        **payload["candidate_packs"],
    }
    for name, stats in rows.items():
        lines.append(
            f"| {name} | {stats['raw_mind_pass_rate']:.4f} | "
            f"{stats['conditional_mind_pass_rate']:.4f} | "
            f"{stats['security_request_denied_rate']:.4f} | "
            f"{stats['security_dormancy_denied']} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This artifact validates the evaluator only. It does not rewrite the "
            "pairwise decision, promote an adapter, or switch Viv's live Qwen mouth.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qwen", type=Path, default=DEFAULT_QWEN)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--decision", type=Path, default=PAIRWISE_DECISION)
    args = parser.parse_args()
    try:
        payload = build(
            qwen_path=args.qwen,
            candidate_path=args.candidate,
            decision_path=args.decision,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    secure_write_json(
        OUT_JSON,
        payload,
        stage_id="evidence_truth",
        run_id="stage1-parity-remeasure",
        artifact_class="evaluation_report",
    )
    secure_write_text(
        OUT_MD,
        to_md(payload),
        stage_id="evidence_truth",
        run_id="stage1-parity-remeasure",
        artifact_class="evaluation_report",
    )
    print(
        json.dumps(
            {
                "ok": payload["ok"],
                "measurement_clean": payload["security_measurement"][
                    "measurement_clean"
                ],
                "admission_decision_unchanged": payload[
                    "admission_decision_unchanged"
                ],
                "next_action": payload["next_action"],
                "artifact": str(OUT_JSON).replace("\\", "/"),
                "artifact_md": str(OUT_MD).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
