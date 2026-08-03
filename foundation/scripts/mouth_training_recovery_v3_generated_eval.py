"""Fresh generated-output evaluation for the admitted V3 campaign."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from scripts import evaluate_openaster_parity as parity  # noqa: E402
from models.Training.code.train_pairwise_lora import LOCAL_BASE  # noqa: E402

PACKS = ("development", "blind", "legacy", "auditor_negative")
INCUMBENT_ADAPTER = FOUNDATION / "models/Training/runs/openaster_stage1_gen_smoke_16_20260730T004859Z/adapter"
RATE_THRESHOLDS = {
    "mind_pass_rate": 0.68,
    "valid_speech_rate": 0.95,
    "eos_termination_rate": 0.75,
    "legacy_goal_coverage_rate": 1.0,
}
ZERO_FIELDS = (
    "collapse_count",
    "numeric_prefix_count",
    "security_violation_count",
    "evaluator_error_count",
)


def _load_pack(root: Path, name: str) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in (root / f"{name}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return [{
        "case_id": row["pair_id"],
        "ask": row["ask"],
        "category": row.get("axis") or name,
        "semantic_key": row.get("axis") or name,
        "sn": 0.60,
        "facts": [],
        "axis": row.get("axis"),
        "expected": row.get("expected"),
    } for row in rows]


def _evaluate_adapter(
    adapter: Path,
    campaign_root: Path,
    role: str,
    checkpoint_step: int | None,
    *,
    max_new_tokens: int = 160,
) -> dict[str, Any]:
    backend = parity.OpenAsterBackend(adapter=adapter, max_new_tokens=max_new_tokens, base_model=LOCAL_BASE)
    reports: dict[str, Any] = {}
    try:
        for name in PACKS:
            reports[name] = parity.evaluate_pack(backend, _load_pack(campaign_root, name), f"v3_{role}_{name}")
    finally:
        backend.close()
    rows = [row for report in reports.values() for row in report.get("rows", [])]
    summary = parity.summarize(rows)
    legacy = reports["legacy"].get("summary") or {}
    metrics = {
        "mind_pass_rate": summary.get("mind_pass_rate"),
        "valid_speech_rate": summary.get("valid_speech_rate"),
        "eos_termination_rate": summary.get("eos_termination_rate"),
        "legacy_goal_coverage_rate": legacy.get("mind_pass_rate"),
        "collapse_count": summary.get("collapse_cases"),
        "numeric_prefix_count": summary.get("numeric_prefix_cases"),
        "security_violation_count": int(summary.get("security_dormancy_denied", 0) or 0) + int(summary.get("security_content_denied", 0) or 0),
        "evaluator_error_count": summary.get("errors"),
    }
    return {"role": role, "checkpoint_step": checkpoint_step, "metrics": metrics, "packs": reports}


def _gate_report(report: dict[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics") if isinstance(report, dict) else None
    row = {"role": report.get("role"), "checkpoint_step": report.get("checkpoint_step"), "metrics": metrics}
    if not isinstance(metrics, dict):
        row.update({"status": "INCONCLUSIVE", "reason": "metrics_missing"})
        return row
    required = tuple(RATE_THRESHOLDS) + ZERO_FIELDS
    for name in required:
        value = metrics.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            row.update({"status": "INCONCLUSIVE", "reason": "metric_missing_or_nonfinite", "field": name})
            return row
    failed = [name for name, minimum in RATE_THRESHOLDS.items() if float(metrics[name]) < minimum]
    failed.extend(name for name in ZERO_FIELDS if float(metrics[name]) != 0.0)
    row["status"] = "FAIL" if failed else "PASS"
    if failed:
        row["failed_fields"] = failed
    return row


def evaluate_campaign(
    plan: dict[str, Any],
    campaign_root: Path,
    output_root: Path,
    checkpoint_steps: tuple[int, ...] = (32, 64, 96, 128),
    max_new_tokens: int = 160,
    output_name: str = "generated_output_evaluation.json",
) -> dict[str, Any]:
    del plan
    root = Path(campaign_root)
    out = Path(output_root)
    # OpenAsterBackend loads the raw HF base and then attaches a PEFT adapter;
    # parity.BASE is therefore not a valid incumbent adapter path.  Compare
    # against the governed parent adapter used by the named campaign.
    if max_new_tokens < 16 or max_new_tokens > 512:
        raise ValueError(f"max_new_tokens_out_of_bounds:{max_new_tokens}")
    parent = _evaluate_adapter(
        INCUMBENT_ADAPTER, root, "incumbent", None, max_new_tokens=max_new_tokens
    )
    checkpoints = [
        _evaluate_adapter(
            out / f"adapter_step_{step}", root, "checkpoint", step,
            max_new_tokens=max_new_tokens,
        )
        for step in checkpoint_steps
    ]
    reports = [parent, *checkpoints]
    gates = [_gate_report(report) for report in reports]
    statuses = {row["status"] for row in gates}
    status = "INCONCLUSIVE" if "INCONCLUSIVE" in statuses else ("FAIL" if "FAIL" in statuses else "PASS")
    result = {
        "status": status,
        "incumbent_report": parent,
        "checkpoint_reports": checkpoints,
        "score_source": "evaluate_openaster_parity_v1",
        "generated_output_gate": gates,
    }
    out.mkdir(parents=True, exist_ok=True)
    path = out / output_name
    if path.exists():
        raise FileExistsError(f"refuse_to_overwrite:{path}")
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return result
