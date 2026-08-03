#!/usr/bin/env python3
"""Deterministically admit or reject the Stage 1 adapter as a candidate only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.training_security import (  # noqa: E402
    secure_write_candidate_pointer,
    secure_write_json,
)

ROOT = FOUNDATION / "artifacts" / "auto" / "openaster_training_tree" / "stage1"
DECISION = ROOT / "stage1_candidate_decision_v1.json"
POINTER = ROOT / "validated_candidate_v1.json"
REGISTRY = ROOT / "stage1_registry_v1.json"


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_report(path: Path, key: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    section = report.get(key)
    if not isinstance(section, dict):
        raise ValueError(f"report_missing_section:{path}:{key}")
    summary = section.get("summary")
    rows = section.get("rows")
    if not isinstance(summary, dict) or not isinstance(rows, list):
        raise ValueError(f"report_malformed_section:{path}:{key}")
    return summary, rows


def decide(
    *,
    qwen_development: Path,
    candidate_development: Path,
    candidate_frozen: Path,
    candidate_adversarial: Path,
    training_result: Path,
    adapter: Path,
) -> dict[str, Any]:
    try:
        qwen_dev, qwen_rows = load_report(qwen_development, "stage1_dev")
        candidate_dev, candidate_dev_rows = load_report(
            candidate_development, "stage1_dev"
        )
        candidate_frz, candidate_frz_rows = load_report(
            candidate_frozen, "stage1_frozen"
        )
        candidate_adv, candidate_adv_rows = load_report(
            candidate_adversarial, "stage1_adversarial"
        )
        training = json.loads(training_result.read_text(encoding="utf-8"))
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": "evidence_load", "detail": str(exc)}

    all_candidate_rows = candidate_dev_rows + candidate_frz_rows + candidate_adv_rows
    criteria = {
        "registry_frozen_360": bool(
            registry.get("frozen") and int(registry.get("rows") or 0) == 360
        ),
        "training_80_steps": int(training.get("optimizer_steps") or 0) == 80,
        "training_nonfinite_zero": int(
            training.get("nonfinite_gradients", -1)
        ) == 0,
        "development_pair_accuracy": float(
            (training.get("development") or {}).get("pair_accuracy") or 0.0
        ) >= 0.90,
        "candidate_dev_at_or_above_qwen": float(
            candidate_dev.get("mind_pass_rate") or 0.0
        ) >= float(qwen_dev.get("mind_pass_rate") or 0.0),
        "candidate_dev_floor": float(candidate_dev.get("mind_pass_rate") or 0.0) >= 0.68,
        "candidate_frozen_floor": float(candidate_frz.get("mind_pass_rate") or 0.0) >= 0.85,
        "candidate_adversarial_floor": float(
            candidate_adv.get("mind_pass_rate") or 0.0
        ) >= 0.68,
        "native_valid_speech": all(
            float(summary.get("valid_speech_rate") or 0.0) >= 0.95
            for summary in (candidate_dev, candidate_frz, candidate_adv)
        ),
        "zero_collapse": all(
            int(summary.get("collapse_cases") or 0) == 0
            and int(summary.get("numeric_prefix_cases") or 0) == 0
            for summary in (candidate_dev, candidate_frz, candidate_adv)
        ),
        "native_only_no_fallback": all(
            row.get("native") is True and not row.get("fallback_used")
            for row in all_candidate_rows
        ),
        "adapter_present": (
            adapter.is_dir()
            and (adapter / "adapter_model.safetensors").is_file()
            and (adapter / "adapter_config.json").is_file()
        ),
    }
    passed = all(criteria.values())
    evidence = {
        "qwen_development": {
            "path": str(qwen_development).replace("\\", "/"),
            "sha256": sha256(qwen_development),
            "summary": qwen_dev,
            "native_rows": len(qwen_rows),
        },
        "candidate_development": {
            "path": str(candidate_development).replace("\\", "/"),
            "sha256": sha256(candidate_development),
            "summary": candidate_dev,
        },
        "candidate_frozen": {
            "path": str(candidate_frozen).replace("\\", "/"),
            "sha256": sha256(candidate_frozen),
            "summary": candidate_frz,
        },
        "candidate_adversarial": {
            "path": str(candidate_adversarial).replace("\\", "/"),
            "sha256": sha256(candidate_adversarial),
            "summary": candidate_adv,
        },
        "training_result": {
            "path": str(training_result).replace("\\", "/"),
            "sha256": sha256(training_result),
        },
        "registry": {
            "path": str(REGISTRY).replace("\\", "/"),
            "sha256": sha256(REGISTRY),
            "registry_id": registry.get("registry_id"),
        },
    }
    result = {
        "ok": passed,
        "decision": "VALIDATED_CANDIDATE" if passed else "REJECTED",
        "decided_at": utc(),
        "stage_id": "evidence_truth",
        "criteria": criteria,
        "failed_criteria": [name for name, value in criteria.items() if not value],
        "evidence": evidence,
        "adapter": str(adapter).replace("\\", "/"),
        "runtime_backend_unchanged": "qwen_gguf",
        "deployment_changed": False,
        "explicit_architect_approval_required_for_any_canary": True,
    }
    secure_write_json(
        DECISION, result, stage_id="evidence_truth",
        run_id="stage1-candidate-decision", artifact_class="evaluation_report",
    )
    if passed:
        pointer = {
            "state": "validated_candidate",
            "stage_id": "evidence_truth",
            "adapter": str(adapter).replace("\\", "/"),
            "decision_path": str(DECISION).replace("\\", "/"),
            "decision_sha256": sha256(DECISION),
            "validated_at": result["decided_at"],
            "deployed": False,
            "live_backend": "qwen_gguf",
        }
        secure_write_candidate_pointer(
            POINTER, pointer, stage_id="evidence_truth",
            run_id="stage1-candidate-decision",
        )
        result["validated_candidate_pointer"] = str(POINTER).replace("\\", "/")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qwen-development", type=Path, required=True)
    parser.add_argument("--candidate-development", type=Path, required=True)
    parser.add_argument("--candidate-frozen", type=Path, required=True)
    parser.add_argument("--candidate-adversarial", type=Path, required=True)
    parser.add_argument("--training-result", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    args = parser.parse_args()
    result = decide(
        qwen_development=args.qwen_development,
        candidate_development=args.candidate_development,
        candidate_frozen=args.candidate_frozen,
        candidate_adversarial=args.candidate_adversarial,
        training_result=args.training_result,
        adapter=args.adapter,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
