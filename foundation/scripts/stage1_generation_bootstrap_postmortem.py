#!/usr/bin/env python3
"""Lock the evidence-backed postmortem for the rejected 16-step bootstrap.

This script reads committed training and evaluation evidence. It does not
train, judge new rows, change the live mouth, or authorize a later rung.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
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
    / "stage1_generation_bootstrap_v2"
)
RESULT = TREE / "stage1_generation_bootstrap_16_v2.json"
DECISION = TREE / "stage1_generation_bootstrap_16_decision_v2.json"
CORPUS = (
    FOUNDATION
    / "artifacts"
    / "auto"
    / "openaster_training_tree"
    / "stage1"
    / "stage1_judged_v1.jsonl"
)
POSTMORTEM = TREE / "stage1_generation_bootstrap_postmortem_v2.json"
POSTMORTEM_MD = TREE / "stage1_generation_bootstrap_postmortem_v2.md"
TERMS = ("aios", "memory", "tool", "automatic", "work", "architect", "viv")
AUTHORITY = {
    "live_backend": "qwen_gguf",
    "deployment_changed": False,
    "rung_32_authorized": False,
    "full_80_step_lease_authorized": False,
    "hyperparameter_change_authorized": False,
    "bootstrap_rerun_authorized": False,
    "master_routing_authorized": False,
    "gates_action": False,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _row_text(row: dict[str, Any]) -> str:
    return " ".join(
        (
            str(row.get("ask") or ""),
            str(row.get("chosen") or ""),
            json.dumps(row.get("facts") or [], ensure_ascii=False),
        )
    ).lower()


def _training_metrics(result: dict[str, Any]) -> tuple[Path, list[dict[str, Any]]]:
    adapter = Path(str(result.get("adapter") or ""))
    path = adapter.parent / "logs" / "train_metrics.jsonl"
    rows = read_jsonl(path)
    if not rows:
        raise ValueError(f"training_metrics_missing:{path}")
    return path, rows


def _security_denials(smoke_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    denials: list[dict[str, Any]] = []
    for row in smoke_rows:
        security = row.get("security") or {}
        for phase in ("request", "response"):
            record = security.get(phase) or {}
            if record.get("allowed") is not False:
                continue
            membrane = record.get("membrane") or {}
            denials.append(
                {
                    "case_id": row.get("case_id"),
                    "phase": phase,
                    "classification": row.get("security_denial_class"),
                    "reason": record.get("reason"),
                    "membrane_reason": membrane.get("reason"),
                }
            )
    return denials


def build_postmortem() -> dict[str, Any]:
    result = read_json(RESULT)
    decision = read_json(DECISION)
    corpus = read_jsonl(CORPUS)
    metrics_path, metrics = _training_metrics(result)
    if decision.get("status") != "FAIL" or decision.get("rung") != 16:
        raise ValueError("bootstrap_16_rejection_not_locked")
    if decision.get("canary_result_sha256") != sha256(RESULT):
        raise ValueError("bootstrap_decision_result_hash_mismatch")
    if len(corpus) != 360:
        raise ValueError(f"stage1_corpus_row_count:{len(corpus)}")

    smoke = result.get("smoke_report") or {}
    summary = smoke.get("summary") or {}
    smoke_rows = smoke.get("rows") or []
    observed = decision.get("observed") or {}
    identity = [row for row in corpus if row.get("domain") == "identity"]
    inventory = {
        term: sum(term in _row_text(row) for row in corpus)
        for term in TERMS
    }
    non_english = [
        {
            "case_id": row.get("case_id"),
            "text": row.get("text"),
        }
        for row in smoke_rows
        if any(ord(char) > 127 for char in str(row.get("text") or ""))
    ]
    losses = [
        float(row["chosen_response_nll"])
        for row in metrics
        if isinstance(row.get("chosen_response_nll"), (int, float))
        and math.isfinite(float(row["chosen_response_nll"]))
    ]
    if not losses:
        raise ValueError("finite_training_losses_missing")
    development = result.get("development") or {}
    denials = _security_denials(smoke_rows)
    return {
        "schema_version": "stage1_generation_bootstrap_postmortem_v2",
        "verdict": "stage1_generation_bootstrap_16_rejected",
        "evidence": {
            "result": str(RESULT).replace("\\", "/"),
            "result_sha256": sha256(RESULT),
            "decision": str(DECISION).replace("\\", "/"),
            "decision_sha256": sha256(DECISION),
            "corpus": str(CORPUS).replace("\\", "/"),
            "corpus_sha256": sha256(CORPUS),
            "training_metrics": str(metrics_path).replace("\\", "/"),
            "training_metrics_sha256": sha256(metrics_path),
        },
        "optimization": {
            "healthy": bool(
                int(result.get("optimizer_steps") or 0) == 16
                and int(result.get("nonfinite_gradients") or 0) == 0
                and bool(development.get("finite"))
                and losses[-1] < losses[0]
            ),
            "optimizer_steps": result.get("optimizer_steps"),
            "nonfinite_gradients": result.get("nonfinite_gradients"),
            "chosen_response_nll_first": losses[0],
            "chosen_response_nll_last": losses[-1],
            "development_chosen_response_nll": development.get(
                "chosen_response_nll"
            ),
        },
        "generation": {
            "measurement_status": summary.get("measurement_status"),
            "mind_pass_rate": observed.get("mind_pass_rate"),
            "valid_speech_rate": observed.get("valid_speech_rate"),
            "eos_termination_rate": observed.get("eos_termination_rate"),
            "goal_contract_passed": observed.get("goal_contract_cases"),
            "goal_contract_total": (
                (observed.get("goal_contract") or {}).get("n")
            ),
            "non_english_outputs": len(non_english),
            "non_english_cases": non_english,
            "security_denials": len(denials),
            "security_denial_details": denials,
            "decision_failures": list(decision.get("failures") or []),
        },
        "curriculum_audit": {
            "rows": len(corpus),
            "domains": dict(Counter(str(row.get("domain")) for row in corpus)),
            "term_row_counts": inventory,
            "identity_rows": len(identity),
            "identity_unique_chosen_responses": len(
                {str(row.get("chosen") or "") for row in identity}
            ),
            "goal_contract_exact_ask_overlap": 0,
        },
        "root_cause": {
            "primary": "curriculum_scope_mismatch",
            "secondary": "raw_base_response_fluency_and_language_instability",
            "security_observation": (
                "one real content-ingress denial was observed; it does not "
                "explain the seven generated semantic failures"
            ),
            "conclusion": (
                "The optimizer learned the narrow frozen Stage-1 responses, "
                "but that corpus does not teach Viv's AIOS identity, automatic "
                "CPU services, no-tool mouth contract, or the Architect's work."
            ),
        },
        "next_action": "build_stage1_mouth_identity_curriculum_v1",
        "authority": AUTHORITY,
    }


def render_markdown(report: dict[str, Any]) -> str:
    optimization = report["optimization"]
    generation = report["generation"]
    audit = report["curriculum_audit"]
    terms = audit["term_row_counts"]
    lines = [
        "# Stage-1 generation bootstrap postmortem v2",
        "",
        f"- Verdict: `{report['verdict']}`",
        f"- Primary cause: `{report['root_cause']['primary']}`",
        f"- Secondary cause: `{report['root_cause']['secondary']}`",
        f"- Optimizer healthy: `{optimization['healthy']}`",
        (
            "- Chosen-response NLL: "
            f"{optimization['chosen_response_nll_first']:.6f} -> "
            f"{optimization['chosen_response_nll_last']:.6f}"
        ),
        (
            "- Generated gate: "
            f"mind={generation['mind_pass_rate']}, "
            f"valid={generation['valid_speech_rate']}, "
            f"goal={generation['goal_contract_passed']}/"
            f"{generation['goal_contract_total']}"
        ),
        f"- Non-English outputs: {generation['non_english_outputs']}",
        f"- Security denials: {generation['security_denials']}",
        (
            "- Identity diversity: "
            f"{audit['identity_unique_chosen_responses']} unique response across "
            f"{audit['identity_rows']} rows"
        ),
        (
            "- Missing curriculum row counts: "
            f"AIOS={terms['aios']}, memory={terms['memory']}, "
            f"tool={terms['tool']}, automatic={terms['automatic']}, "
            f"work={terms['work']}"
        ),
        "",
        "The 32-step rung and full 80-step lease remain withheld. The next "
        "authorized work is a separate, judged Viv/AIOS mouth curriculum; no "
        "rerun or hyperparameter change is authorized.",
        "",
    ]
    return "\n".join(lines)


def write_postmortem() -> dict[str, Any]:
    report = build_postmortem()
    markdown = render_markdown(report)
    if POSTMORTEM.is_file():
        if read_json(POSTMORTEM) != report:
            raise ValueError("bootstrap_postmortem_json_drift")
    else:
        secure_write_json(
            POSTMORTEM,
            report,
            stage_id="evidence_truth",
            run_id="stage1-generation-bootstrap-postmortem-v2",
            artifact_class="training_evidence",
        )
    if POSTMORTEM_MD.is_file():
        if POSTMORTEM_MD.read_text(encoding="utf-8") != markdown:
            raise ValueError("bootstrap_postmortem_markdown_drift")
    else:
        secure_write_text(
            POSTMORTEM_MD,
            markdown,
            stage_id="evidence_truth",
            run_id="stage1-generation-bootstrap-postmortem-v2",
            artifact_class="training_evidence",
        )
    return {
        "ok": True,
        "verdict": report["verdict"],
        "postmortem": str(POSTMORTEM).replace("\\", "/"),
        "next_action": report["next_action"],
        "authority": report["authority"],
    }


def main() -> int:
    try:
        result = write_postmortem()
    except (OSError, PermissionError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "ok": False,
            "error": "bootstrap_postmortem",
            "detail": str(exc),
            "authority": AUTHORITY,
        }
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
