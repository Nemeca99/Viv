#!/usr/bin/env python3
"""Record the immutable post-run decision for the v2 recovery campaign."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v2_anchor_coverage_v1_3"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    result_path = ROOT / "FINAL_RUN_RESULT.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    training = result["training"]
    decision = {
        "schema_version": "mouth_recovery_v2_final_decision_v1",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "experiment_id": result["experiment_id"],
        "decision": "ABORT_NO_PROMOTION",
        "reason": "law5_commit_denied_master_s_n_below_threshold",
        "master_s_n": training["security_commit"]["detail"]["master_rid"]["master_s_n"],
        "optimizer_steps_completed": training["optimizer_steps"],
        "checkpoint_steps": [item["step"] for item in training["checkpoint_saves"]],
        "initial_mean_response_nll": training["initial_teacher_forced"]["mean_response_nll"],
        "final_mean_response_nll": training["final_teacher_forced"]["mean_response_nll"],
        "nll_reduction_fraction": training["nll_reduction_fraction"],
        "final_token_accuracy": training["final_teacher_forced"]["token_accuracy"],
        "commit_allowed": False,
        "promotion_allowed": False,
        "deployment_changed": False,
        "run_authorized": False,
        "training_authorized": False,
        "parent_004859z_touched": False,
        "live_qwen_gguf_touched": False,
        "staged_artifact_root": "L:/Continue/Viv/sandbox/training_staging/mouth_training_recovery_v2_anchor_coverage_v1_3",
        "final_result_sha256": sha(result_path),
        "next_action": "Do not retry automatically. Review Law 5 plant-state denial and staged checkpoint evidence before any new authorization.",
    }
    path = ROOT / "FINAL_DECISION_REPORT.json"
    if path.exists():
        raise FileExistsError(f"refuse_overwrite:{path}")
    path.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    md = ROOT / "FINAL_DECISION_REPORT.md"
    md.write_text(
        "# Mouth Recovery v2 Final Decision\n\n"
        "Decision: `ABORT_NO_PROMOTION`\n\n"
        f"The 128-step BF16 run completed with finite loss, but the governed commit was denied by Law 5 because Master S_n was `{decision['master_s_n']}`. The checkpoints remain staged only.\n\n"
        f"NLL: `{decision['initial_mean_response_nll']:.6f}` -> `{decision['final_mean_response_nll']:.6f}` ({decision['nll_reduction_fraction']:.2%} reduction).\n\n"
        "Authorization was re-armed closed. The parked 004859Z adapter and live qwen_gguf were not touched. No retry, promotion, or deployment occurred.\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
