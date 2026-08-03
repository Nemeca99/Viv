#!/usr/bin/env python3
"""Lock the bounded Stage-1 generation smoke result and authority boundary."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.training_security import secure_write_json, secure_write_text  # noqa: E402

TREE = (
    FOUNDATION
    / "artifacts"
    / "auto"
    / "openaster_training_tree"
    / "stage1_generation_v1"
)
SMOKE_4 = TREE / "stage1_generation_smoke_v1.json"
SMOKE_8 = TREE / "stage1_generation_smoke_8_v1.json"
OUT_JSON = TREE / "stage1_generation_smoke_review_v1.json"
OUT_MD = TREE / "stage1_generation_smoke_review_v1.md"


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"not_object:{path}")
    return payload


def metrics(payload: dict[str, Any]) -> dict[str, Any]:
    summary = ((payload.get("smoke_report") or {}).get("summary") or {})
    development = payload.get("development") or {}
    return {
        "optimizer_steps": int(payload.get("optimizer_steps") or 0),
        "smoke_status": payload.get("smoke_status"),
        "development_chosen_response_nll": float(
            development.get("chosen_response_nll") or 0.0
        ),
        "valid_speech_rate": float(summary.get("valid_speech_rate") or 0.0),
        "mind_pass_rate": float(summary.get("mind_pass_rate") or 0.0),
        "collapse_cases": int(summary.get("collapse_cases") or 0),
        "numeric_prefix_cases": int(summary.get("numeric_prefix_cases") or 0),
        "security_request_denied_rate": float(
            summary.get("security_request_denied_rate") or 0.0
        ),
        "eos_termination_rate": summary.get("eos_termination_rate"),
        "failures": list(payload.get("smoke_failures") or []),
        "adapter": payload.get("adapter"),
    }


def build() -> dict[str, Any]:
    smoke4 = load(SMOKE_4)
    smoke8 = load(SMOKE_8)
    lock4 = smoke4.get("lineage_lock") or {}
    lock8 = smoke8.get("lineage_lock") or {}
    same_lineage = lock4 == lock8
    four = metrics(smoke4)
    eight = metrics(smoke8)
    security_clean = (
        four["security_request_denied_rate"] == 0.0
        and eight["security_request_denied_rate"] == 0.0
    )
    final_pass = (
        smoke8.get("ok") is True and smoke8.get("smoke_status") == "PASS"
    )
    return {
        "ok": True,
        "at": utc(),
        "schema_version": "stage1_generation_smoke_review_v1",
        "lineage": "stage1_generation_v1",
        "inputs": {
            "smoke_4": {
                "path": str(SMOKE_4).replace("\\", "/"),
                "sha256": sha256(SMOKE_4),
            },
            "smoke_8": {
                "path": str(SMOKE_8).replace("\\", "/"),
                "sha256": sha256(SMOKE_8),
            },
        },
        "same_lineage_lock": same_lineage,
        "security_measurement_clean": security_clean,
        "smoke_4": four,
        "smoke_8": eight,
        "observed_learning": {
            "development_nll_delta_8_minus_4": round(
                eight["development_chosen_response_nll"]
                - four["development_chosen_response_nll"],
                6,
            ),
            "valid_speech_delta_8_minus_4": round(
                eight["valid_speech_rate"] - four["valid_speech_rate"], 4
            ),
            "collapse_delta_8_minus_4": (
                eight["collapse_cases"] - four["collapse_cases"]
            ),
            "numeric_prefix_delta_8_minus_4": (
                eight["numeric_prefix_cases"] - four["numeric_prefix_cases"]
            ),
            "interpretation": (
                "Pure response supervision is changing free generation in the "
                "desired direction, but eight steps do not yet establish "
                "complete valid speech or semantic mind behavior."
            ),
        },
        "verdict": (
            "generation_smoke_passed"
            if final_pass
            else "generation_smoke_failed_full_lease_withheld"
        ),
        "full_80_step_lease_authorized": bool(final_pass),
        "next_action": (
            "run_stage1_generation_80"
            if final_pass
            else "separate_stage1_generation_bootstrap_review_required"
        ),
        "authority": {
            "live_backend": "qwen_gguf",
            "deployment_changed": False,
            "learning_admission_withheld": True,
            "master_routing_authorized": False,
            "gates_action": False,
            "auto_deploy": False,
            "auto_rerun": False,
        },
    }


def to_md(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Stage-1 generation smoke review v1",
            "",
            f"- Verdict: **{payload['verdict']}**",
            f"- Full 80-step lease authorized: "
            f"**{payload['full_80_step_lease_authorized']}**",
            f"- Next action: `{payload['next_action']}`",
            f"- Same lineage lock: `{payload['same_lineage_lock']}`",
            f"- Security measurement clean: "
            f"`{payload['security_measurement_clean']}`",
            "",
            "| Smoke | Dev NLL | Valid speech | Mind pass | Collapse | Numeric |",
            "|---|---:|---:|---:|---:|---:|",
            f"| 4 steps | {payload['smoke_4']['development_chosen_response_nll']:.4f} "
            f"| {payload['smoke_4']['valid_speech_rate']:.4f} "
            f"| {payload['smoke_4']['mind_pass_rate']:.4f} "
            f"| {payload['smoke_4']['collapse_cases']} "
            f"| {payload['smoke_4']['numeric_prefix_cases']} |",
            f"| 8 steps | {payload['smoke_8']['development_chosen_response_nll']:.4f} "
            f"| {payload['smoke_8']['valid_speech_rate']:.4f} "
            f"| {payload['smoke_8']['mind_pass_rate']:.4f} "
            f"| {payload['smoke_8']['collapse_cases']} "
            f"| {payload['smoke_8']['numeric_prefix_cases']} |",
            "",
            payload["observed_learning"]["interpretation"],
            "",
            "Qwen remains Viv's live mouth. No adapter was deployed or admitted.",
            "",
        ]
    )


def main() -> int:
    try:
        payload = build()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    secure_write_json(
        OUT_JSON,
        payload,
        stage_id="evidence_truth",
        run_id="stage1-generation-smoke-review",
        artifact_class="training_evidence",
    )
    secure_write_text(
        OUT_MD,
        to_md(payload),
        stage_id="evidence_truth",
        run_id="stage1-generation-smoke-review",
        artifact_class="training_evidence",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "verdict": payload["verdict"],
                "full_80_step_lease_authorized": payload[
                    "full_80_step_lease_authorized"
                ],
                "next_action": payload["next_action"],
                "artifact": str(OUT_JSON).replace("\\", "/"),
                "artifact_md": str(OUT_MD).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
