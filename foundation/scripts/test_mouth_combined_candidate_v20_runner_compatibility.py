#!/usr/bin/env python3
"""Test the read-only v20 runner compatibility audit."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
SCRIPT = FOUNDATION / "scripts/audit_mouth_combined_candidate_v20_runner_compatibility.py"
CAMPAIGN = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_combined_candidate_v20"
REPORT = CAMPAIGN / "RUNNER_COMPATIBILITY_AUDIT_V2.json"


def main() -> int:
    if not REPORT.exists():
        command = [sys.executable, str(SCRIPT)]
        completed = subprocess.run(command, cwd=str(FOUNDATION), capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise AssertionError(completed.stdout + completed.stderr)
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["status"] == "TRAINER_ACCEPTS_256_BASE_52_POSITIVE_HOLD_ROWS_REQUIRE_ADMISSION_RUNNER_ADAPTER_REQUIRED"
    assert report["candidate_rows"] == 368
    assert report["admitted_compatible_rows"] == 256
    assert report["positive_hold_rows"] == 52
    assert report["negative_hold_rows"] == 60
    assert report["production_row_validator"] == "accepted_expected_rows_256_existing_admission"
    assert report["model_loaded"] is False
    assert report["cuda_touched"] is False
    assert report["lease_called"] is False
    assert report["optimizer_steps_executed"] == 0
    assert report["execution_authorized"] is False
    assert report["training_authorized"] is False
    assert len(report["legacy_256_wrappers"]) == 2
    print({"ok": True, "candidate_rows": 368, "trainer_accepts": True, "gpu_steps": 0, "run_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
