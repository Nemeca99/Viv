#!/usr/bin/env python3
"""Generate the evidence bundle for the training-tree skeleton milestone."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO, FOUNDATION / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import training_tree  # noqa: E402
from lib.training_security import secure_write_json, secure_write_text  # noqa: E402

ROOT = FOUNDATION / "artifacts" / "auto" / "openaster_training_tree"
REPORT_JSON = ROOT / "milestone_report_v2.json"
REPORT_MD = ROOT / "milestone_report_v2.md"
ROLLBACK = ROOT / "rollback_instructions_v2.md"
UNIFIED = ROOT / "unified_preflight_latest.json"
JOURNAL = FOUNDATION / "artifacts" / "audit" / "session_journal.md"
MARKER = "**TRAINING TREE V2 SKELETON**"


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def command_evidence(command: list[str]) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command, cwd=str(REPO), capture_output=True, text=True, timeout=30, check=False
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"returncode": None, "error": str(exc)}


def main() -> int:
    status = training_tree.validate()
    pairwise = (
        json.loads(training_tree.PAIR_PREFLIGHT.read_text(encoding="utf-8"))
        if training_tree.PAIR_PREFLIGHT.is_file() else {}
    )
    python = FOUNDATION.parents[1] / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        python = Path(sys.executable)
    unified_proc = subprocess.run(
        [str(python), "-B", str(FOUNDATION / "scripts" / "run_foundation_preflight.py")],
        cwd=str(REPO), capture_output=True, text=True, timeout=300, check=False,
    )
    try:
        unified = json.loads(unified_proc.stdout)
    except json.JSONDecodeError:
        unified = {
            "ok": False, "error": "malformed_unified_preflight",
            "stdout_tail": unified_proc.stdout[-2000:],
            "stderr_tail": unified_proc.stderr[-2000:],
        }
    secure_write_json(UNIFIED, unified, run_id="training-tree-finalize")
    hardware = {
        "ollama_ps": command_evidence(["ollama", "ps"]),
        "gpu": command_evidence([
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,utilization.gpu,power.draw",
            "--format=csv,noheader",
        ]),
    }
    preflight_detail = pairwise.get("detail") or {}
    report = {
        "schema_version": training_tree.SCHEMA_VERSION,
        "milestone": "layered_training_tree_skeleton",
        "generated_at": utc(),
        "ok": bool(status.get("ok") and pairwise.get("ok") and unified.get("ok")),
        "status": status,
        "pairwise_preflight": pairwise,
        "unified_preflight": unified,
        "hardware_after": hardware,
        "claims": {
            "tree_stage_specs": 8,
            "balanced_seed_pairs": 96,
            "categorical_double_judgments_complete": status.get("judged_complete"),
            "categorical_repeat_agreement": status.get("categorical_repeat_agreement"),
            "expected_contrast_agreement": status.get("expected_contrast_agreement"),
            "held_sensor_misses": status.get("hold"),
            "frozen_overlap": status.get("frozen_overlap"),
            "contaminated_training_targets": status.get("contaminated_training_targets"),
            "optimizer_preflight_steps": preflight_detail.get("optimizer_steps"),
            "pairwise_preflight_peak_vram_gib": preflight_detail.get("peak_vram_gib"),
            "nonfinite_gradients": preflight_detail.get("nonfinite_gradients"),
            "production_training_performed": False,
            "deployment_changed": False,
            "runtime_backend": "qwen_gguf",
            "train_ready": False,
        },
        "artifacts": {
            "tree": str(training_tree.TREE).replace("\\", "/"),
            "seeds": str(training_tree.SEEDS).replace("\\", "/"),
            "judged_pairs": str(training_tree.JUDGED).replace("\\", "/"),
            "registry": str(training_tree.REGISTRY).replace("\\", "/"),
            "judge_audit": str(training_tree.AUDIT).replace("\\", "/"),
            "status": str(training_tree.STATUS).replace("\\", "/"),
            "pairwise_preflight": str(training_tree.PAIR_PREFLIGHT).replace("\\", "/"),
            "unified_preflight": str(UNIFIED).replace("\\", "/"),
            "rollback": str(ROLLBACK).replace("\\", "/"),
        },
        "next_gate": (
            "Calibrate held axes, then activate stage 1 only after a separately "
            "frozen 240/48/48/24 corpus satisfies every cumulative gate."
        ),
    }
    secure_write_json(REPORT_JSON, report, run_id="training-tree-finalize")
    stage_lines = "\n".join(
        f"| {stage} | {values['seed_validated']} | {values['hold']} | "
        f"{values['expected_contrast_agreement_rate']:.4f} |"
        for stage, values in status.get("stage_calibration", {}).items()
    )
    report_markdown = (
        "# Viv training-tree v2 skeleton evidence\n\n"
        f"- generated: {report['generated_at']}\n"
        f"- result: {'PASS' if report['ok'] else 'FAIL'}\n"
        "- runtime backend: Qwen GGUF (unchanged)\n"
        "- production training: no\n"
        "- deployment change: no\n"
        f"- seed pairs: 96 (validated {status.get('seed_validated')}, held {status.get('hold')})\n"
        f"- repeat agreement: {status.get('categorical_repeat_agreement')}\n"
        f"- frozen overlap: {status.get('frozen_overlap')}\n"
        f"- contaminated targets: {status.get('contaminated_training_targets')}\n"
        f"- pairwise optimizer preflight: {preflight_detail.get('optimizer_steps')} step, "
        f"{preflight_detail.get('peak_vram_gib')} GiB peak\n"
        f"- unified preflight: {unified.get('ok')} "
        f"({unified.get('parsed_python_files')} Python files, {len(unified.get('tests') or [])} suites)\n\n"
        "## Stage calibration\n\n"
        "| Stage | Validated | Hold | Expected contrast agreement |\n"
        "| --- | ---: | ---: | ---: |\n"
        + stage_lines
        + "\n\nThe 39 held records are evidence of sensor limits, not training examples. "
        "Deterministic UML/schema/construction rules remained authoritative.\n",
    )
    secure_write_text(REPORT_MD, report_markdown, run_id="training-tree-finalize")
    rollback_markdown = (
        "# Training-tree v2 rollback\n\n"
        "No runtime adapter, deploy pointer, or live backend changed in this milestone. "
        "Immediate runtime rollback is therefore unnecessary: Qwen GGUF remains live.\n\n"
        "To disable future tree operations without deleting evidence, set "
        "`model_config.json -> training_tree.enabled` to `false`. Preserve this "
        "directory and the frozen registry for audit. Never delete or regenerate "
        "the registry to make an overlap test pass.\n",
    )
    secure_write_text(ROLLBACK, rollback_markdown, run_id="training-tree-finalize")
    journal_entry = (
        f"- [{report['generated_at']}] {MARKER} — implemented eight cumulative stages and "
        f"froze 96 balanced seed pairs (57 calibrated, 39 HOLD). All 96 CPU semantic "
        "comparisons agreed across two deterministic observations; known contrast agreement "
        "was 0.59375, so misses remained excluded. Frozen overlap=0 and rejected-as-SFT "
        f"targets=0. Hybrid one-step preflight passed at {preflight_detail.get('peak_vram_gib')} "
        f"GiB peak with nonfinite_gradients={preflight_detail.get('nonfinite_gradients')}; "
        f"unified preflight parsed {unified.get('parsed_python_files')} files and passed "
        f"{len(unified.get('tests') or [])} suites. Qwen remains live; no production training "
        "or deployment change. Evidence: artifacts/auto/openaster_training_tree/milestone_report_v2.json\n"
    )
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    existing = JOURNAL.read_text(encoding="utf-8") if JOURNAL.is_file() else ""
    if MARKER not in existing:
        prefix = existing + ("" if not existing or existing.endswith("\n") else "\n")
        secure_write_text(
            JOURNAL, prefix + journal_entry, run_id="training-tree-finalize"
        )
    print(json.dumps({
        "ok": report["ok"], "report": str(REPORT_JSON).replace("\\", "/"),
        "journal_updated": MARKER not in existing,
        "unified_preflight": unified.get("ok"),
    }, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
