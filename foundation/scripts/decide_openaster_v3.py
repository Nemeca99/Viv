#!/usr/bin/env python3
"""Final fail-closed admission decision for the OpenAster v3 candidate."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aifl_parity_contracts import validate_corpus_file

ROOT = FOUNDATION / "artifacts" / "auto" / "openaster_stabilization"
OUT = ROOT / "candidate_decision_v3.json"
CORPUS = FOUNDATION / "artifacts" / "models" / "viv_judge_sft_v3.jsonl"
CONFIG = FOUNDATION / "model_config.json"
REGISTRIES = (
    FOUNDATION / "artifacts" / "auto" / "openaster_parity" / "development_registry_v1.json",
    FOUNDATION / "artifacts" / "auto" / "openaster_parity" / "multiturn_registry_v1.json",
    ROOT / "smoke_registry_v1.json",
)


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path, required=True)
    parser.add_argument("--qwen-deploy-report", type=Path, required=True)
    parser.add_argument("--continuity-report", type=Path)
    args = parser.parse_args()
    selection = load(args.selection)
    selected = selection.get("selected") or {}
    candidate = load(args.candidate_report)
    qwen = load(args.qwen_deploy_report)
    adapter_raw = str(candidate.get("adapter") or "")
    selected_raw = str(selected.get("adapter") or "")
    if not selected or Path(adapter_raw) != Path(selected_raw):
        raise ValueError("candidate report does not match selected development checkpoint")
    adapter_path = Path(adapter_raw)
    if not adapter_path.is_absolute():
        adapter_path = FOUNDATION.parent / adapter_path
    adapter = str(adapter_path.resolve()).replace("\\", "/")
    deploy = (candidate.get("deploy") or {}).get("summary") or {}
    multiturn = (candidate.get("multiturn") or {}).get("summary") or {}
    qwen_deploy = (qwen.get("deploy") or {}).get("summary") or {}
    disjoint = validate_corpus_file(CORPUS, registry_paths=REGISTRIES)
    qwen_floor = max(0.68, float(qwen_deploy.get("mind_pass_rate") or 0))
    quality_parity = float(deploy.get("mind_pass_rate") or 0) >= qwen_floor
    checks = {
        "corpus_disjoint_and_valid": bool(disjoint.get("ok")),
        "deploy_mind_at_baseline_and_floor": quality_parity,
        "native_valid_speech_gte_0_95": float(deploy.get("valid_speech_rate") or 0) >= 0.95,
        "zero_collapse": int(deploy.get("collapse_cases") or 0) == 0,
        "zero_numeric_prefix": int(deploy.get("numeric_prefix_cases") or 0) == 0,
        "multiturn_gte_11_of_12": int(multiturn.get("passing_scripts") or 0) >= 11,
        "token_cost_no_higher_than_qwen": (
            quality_parity
            and float(deploy.get("median_model_tokens") or 10**9)
            <= float(qwen_deploy.get("median_model_tokens") or -1)
        ),
        "zero_errors": int(deploy.get("errors") or 0) == 0,
    }
    accepted = all(checks.values())
    continuity = load(args.continuity_report) if args.continuity_report else None
    result = {
        "version": 3, "at": utc(),
        "decision": "validated_candidate" if accepted else "rejected_candidate",
        "accepted": accepted, "checks": checks,
        "selected_adapter": adapter,
        "development_summary": selected.get("summary"),
        "deploy_summary": deploy, "qwen_deploy_summary": qwen_deploy,
        "deploy_mind_floor": qwen_floor, "multiturn_summary": multiturn,
        "continuity_diagnostic": (
            (continuity.get("continuity") or {}).get("summary") if continuity else None
        ),
        "disjoint": disjoint,
        "runtime": {
            "live_backend": "qwen_gguf",
            "validated_candidate": adapter if accepted else None,
            "auto_deploy": False, "deployment_changed": False,
        },
        "rollback": (
            "No runtime switch occurred. If an approved canary later fails, restore "
            "Qwen live_backend and clear the runtime OpenAster adapter pointer."
        ),
    }
    if OUT.exists():
        raise FileExistsError(f"frozen decision already exists: {OUT}")
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    config = load(CONFIG)
    training = config.setdefault("openaster_training", {})
    training["candidate_adapter"] = adapter
    training["validated_candidate"] = adapter if accepted else None
    training["auto_deploy"] = False
    CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
