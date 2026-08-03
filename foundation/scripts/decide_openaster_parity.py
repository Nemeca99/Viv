#!/usr/bin/env python3
"""Freeze the OpenAster parity selection and admission decision from evidence."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts" / "auto" / "openaster_parity"
REPORTS = ROOT / "reports"
CORPUS = FOUNDATION / "artifacts" / "models" / "viv_judge_sft_v2.jsonl"
OUT = ROOT / "candidate_decision_v1.json"

A_RUN = FOUNDATION / "models" / "Training" / "runs" / "lora_judge_openaster_parity_a_80_20260723T094400Z"
B_RUN = FOUNDATION / "models" / "Training" / "runs" / "lora_judge_openaster_parity_b_160_20260723T094700Z"


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summary(report: dict[str, Any], key: str) -> dict[str, Any]:
    return dict((report.get(key) or {}).get("summary") or {})


def main() -> int:
    import sys

    for value in (FOUNDATION, FOUNDATION.parent):
        if str(value) not in sys.path:
            sys.path.insert(0, str(value))
    from lib.aifl_parity_contracts import validate_corpus_file

    paths = {
        "qwen_dev_multiturn": REPORTS / "qwen_native_dev_multiturn.json",
        "qwen_deploy": REPORTS / "qwen_native_deploy.json",
        "candidate_a_dev": REPORTS / "candidate_a_dev.json",
        "candidate_b_dev": REPORTS / "candidate_b_dev.json",
        "candidate_b_deploy_multiturn": REPORTS / "candidate_b_deploy_multiturn.json",
        "candidate_b_continuity": REPORTS / "candidate_b_continuity_diagnostic.json",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        print(json.dumps({"ok": False, "error": "missing_evidence", "paths": missing}, indent=2))
        return 1

    reports = {name: read(path) for name, path in paths.items()}
    a_dev = summary(reports["candidate_a_dev"], "dev")
    b_dev = summary(reports["candidate_b_dev"], "dev")
    qwen_dev = summary(reports["qwen_dev_multiturn"], "dev")
    qwen_deploy = summary(reports["qwen_deploy"], "deploy")
    b_deploy = summary(reports["candidate_b_deploy_multiturn"], "deploy")
    b_multi = summary(reports["candidate_b_deploy_multiturn"], "multiturn")
    b_continuity = summary(reports["candidate_b_continuity"], "continuity")

    def selection_key(item: dict[str, Any]) -> tuple[float, float, float, float]:
        return (
            float(item.get("mind_pass_rate") or 0.0),
            float(item.get("valid_speech_rate") or 0.0),
            -float(item.get("collapse_cases") or 0.0),
            -float(item.get("median_model_tokens") or 1e9),
        )

    selected = "candidate_b" if selection_key(b_dev) > selection_key(a_dev) else "candidate_a"
    if selected != "candidate_b":
        print(json.dumps({"ok": False, "error": "selected_candidate_missing_deciding_pack", "selected": selected}, indent=2))
        return 1

    corpus_check = validate_corpus_file(
        CORPUS,
        registry_paths=(
            FOUNDATION / "artifacts" / "auto" / "shadow_judge" / "holdout_registry.json",
            FOUNDATION / "artifacts" / "auto" / "shadow_judge" / "deploy_test_registry.json",
            ROOT / "development_registry_v1.json",
            ROOT / "multiturn_registry_v1.json",
        ),
    )
    deploy_floor = max(0.68, float(qwen_deploy.get("mind_pass_rate") or 0.0))
    mind_gate = float(b_deploy.get("mind_pass_rate") or 0.0) >= deploy_floor
    speech_gate = float(b_deploy.get("valid_speech_rate") or 0.0) >= 0.95
    collapse_gate = int(b_deploy.get("collapse_cases") or 0) == 0
    multiturn_gate = int(b_multi.get("passing_scripts") or 0) >= 11
    qwen_tokens = qwen_deploy.get("median_model_tokens")
    candidate_tokens = b_deploy.get("median_model_tokens")
    token_observation = (
        qwen_tokens is not None
        and candidate_tokens is not None
        and float(candidate_tokens) <= float(qwen_tokens)
    )
    quality_parity = mind_gate and speech_gate and collapse_gate and multiturn_gate
    token_gate = quality_parity and token_observation
    gates = {
        "corpus_disjoint_and_valid": bool(corpus_check.get("ok")),
        "deploy_mind_at_least_qwen_and_0_68": mind_gate,
        "native_valid_speech_at_least_0_95": speech_gate,
        "zero_numeric_or_repetition_collapse": collapse_gate,
        "at_least_11_of_12_multiturn_scripts": multiturn_gate,
        "median_tokens_no_higher_after_quality_parity": token_gate,
    }
    accepted = all(gates.values())
    try:
        gpu_probe = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version,power.limit",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        gpu_resource = {
            "probe": gpu_probe.stdout.strip(),
            "probe_returncode": gpu_probe.returncode,
            "exclusive_8gb_policy": True,
        }
    except (OSError, subprocess.SubprocessError) as exc:
        gpu_resource = {"probe": None, "error": str(exc), "exclusive_8gb_policy": True}
    artifact = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "milestone": "openaster_train_to_runtime_parity",
        "roles": {
            "live_baseline": "qwen_gguf",
            "teacher": "qwen_gguf",
            "trainable_target": "openaster_hf_lora",
            "alignment_authority": "cpu_shadow_judge",
            "fallback_in_native_scores": False,
        },
        "corpus": {
            "path": str(CORPUS).replace("\\", "/"),
            "sha256": digest(CORPUS),
            "contract": corpus_check,
        },
        "baseline": {
            "qwen_dev": qwen_dev,
            "qwen_deploy": qwen_deploy,
            "qwen_multiturn": summary(reports["qwen_dev_multiturn"], "multiturn"),
        },
        "candidates": {
            "candidate_a": {
                "run": str(A_RUN).replace("\\", "/"),
                "adapter": str(A_RUN / "adapter").replace("\\", "/"),
                "training": read(A_RUN / "meta" / "viv_train_meta.json"),
                "dev": a_dev,
            },
            "candidate_b": {
                "run": str(B_RUN).replace("\\", "/"),
                "adapter": str(B_RUN / "adapter").replace("\\", "/"),
                "training": read(B_RUN / "meta" / "viv_train_meta.json"),
                "dev": b_dev,
                "deploy": b_deploy,
                "multiturn": b_multi,
                "continuity_diagnostic": b_continuity,
            },
        },
        "selection": {
            "selected": selected,
            "rule": "development mind pass, then valid speech, then fewer collapses, then fewer tokens",
        },
        "acceptance": {
            "accepted": accepted,
            "required_deploy_mind_rate": deploy_floor,
            "gates": gates,
            "token_cost_observation": {
                "qwen_median": qwen_tokens,
                "candidate_median": candidate_tokens,
                "non_higher": token_observation,
                "decision_applicable": quality_parity,
            },
            "energy": {
                "blocking": False,
                "observed": False,
                "power_samples_watts": [],
                "estimated_joules": None,
                "note": "Power and joules remain observational until calibrated.",
            },
        },
        "resource_observation": gpu_resource,
        "state_change": {
            "candidate_adapter": str(B_RUN / "adapter").replace("\\", "/"),
            "validated_candidate": str(B_RUN / "adapter").replace("\\", "/") if accepted else None,
            "live_backend_changed": False,
            "deployment_attempted": False,
        },
        "decision": "validated_candidate" if accepted else "rejected_candidate",
        "rollback": {
            "current_action": "No runtime switch occurred; Qwen remains live.",
            "future_canary": "Requires explicit Architect approval and all acceptance gates.",
            "automatic_revert_conditions": [
                "malformed_speech",
                "repeated_fallback",
                "security_rejection",
                "judge_regression",
            ],
        },
        "evidence": {
            name: {"path": str(path).replace("\\", "/"), "sha256": digest(path)}
            for name, path in paths.items()
        },
    }
    OUT.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": True, "artifact": str(OUT).replace("\\", "/"), "decision": artifact["decision"], "gates": gates}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
