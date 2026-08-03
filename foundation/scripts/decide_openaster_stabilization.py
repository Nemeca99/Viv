#!/usr/bin/env python3
"""Fail-closed Stage S gate for the OpenAster stabilization milestone."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts" / "auto" / "openaster_stabilization"
DECISION = ROOT / "stage_s_decision_v1.json"


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def decide(report_path: Path, run_dir: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    smoke = report.get("smoke") or {}
    summary = smoke.get("summary") or {}
    rows = list(smoke.get("rows") or [])
    meta_path = run_dir / "meta" / "viv_train_meta.json"
    coverage_path = run_dir / "meta" / "lora_module_coverage.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    coverage = json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.is_file() else {}
    prompt_leaks = sum(
        any(term in str(row.get("text") or "").lower() for term in (
            "prompt-version", "<|im_start|>", "semantic-class:", "architect:",
        ))
        for row in rows
    )
    security_rejections = sum(not bool(row.get("security_allowed")) for row in rows)
    checks = {
        "train_complete": bool(meta) and int(meta.get("steps") or 0) == 240,
        "finite_gradients": not bool(meta.get("forensics_nonfinite_steps")),
        "module_coverage": bool(coverage) and not bool(coverage.get("missing")),
        "native_cases_24": int(summary.get("n") or 0) == 24,
        "valid_speech_gte_0_90": float(summary.get("valid_speech_rate") or 0) >= 0.90,
        "eos_termination_gte_0_90": float(summary.get("eos_termination_rate") or 0) >= 0.90,
        "median_tokens_lte_80": float(summary.get("median_model_tokens") or 10**9) <= 80,
        "zero_collapse": int(summary.get("collapse_cases") or 0) == 0,
        "zero_numeric_prefix": int(summary.get("numeric_prefix_cases") or 0) == 0,
        "zero_prompt_leak": prompt_leaks == 0,
        "zero_security_rejection": security_rejections == 0,
        "mind_pass_gte_0_50": float(summary.get("mind_pass_rate") or 0) >= 0.50,
        "zero_errors": int(summary.get("errors") or 0) == 0,
    }
    passed = all(checks.values())
    result = {
        "version": 1, "at": utc(), "stage": "S",
        "decision": "continue_full_v3" if passed else "stop_preserve_for_diagnosis",
        "passed": passed, "checks": checks, "summary": summary,
        "diagnostics": {
            "prompt_leak_cases": prompt_leaks,
            "security_rejections": security_rejections,
            "peak_vram_reserved_gb": meta.get("peak_vram_reserved_gb"),
            "train_loss": meta.get("train_loss"),
        },
        "run": str(run_dir).replace("\\", "/"),
        "report": str(report_path).replace("\\", "/"),
        "deployment_changed": False,
        "next": (
            "Continue the same adapter on full v3 for 540 steps at 3e-5."
            if passed else
            "Do not continue to full v3; diagnose the failed checks."
        ),
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    if DECISION.exists():
        raise FileExistsError(f"frozen decision already exists: {DECISION}")
    DECISION.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    result = decide(args.report, args.run)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
