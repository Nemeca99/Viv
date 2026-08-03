"""Regression checks for the expanded hold-only semantic calibration."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantics_calibration_v5"
SOURCE = ROOT / "calibration_96.jsonl"
REPORT = ROOT / "CALIBRATION_EVALUATION.json"


def main() -> int:
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert len(rows) == 96
    assert report["status"] == "CALIBRATION_PASS"
    assert report["matched"] == 96
    assert report["mismatches"] == []
    assert report["optimizer_eligible"] is False
    assert report["training_authorized"] is False
    assert report["run_authorized"] is False
    assert all(row["hold_only"] and not row["optimizer_eligible"] for row in rows)
    axis_counts = Counter(row["axis"] for row in rows)
    label_counts = Counter((row["axis"], row["expected"]) for row in rows)
    assert set(axis_counts.values()) == {12}
    assert set(label_counts.values()) == {6, 3}
    assert all(label_counts[(axis, "PASS")] == 6 for axis in axis_counts)
    assert all(label_counts[(axis, "FAIL")] == 3 for axis in axis_counts)
    assert all(label_counts[(axis, "HOLD")] == 3 for axis in axis_counts)
    print({"ok": True, "rows": len(rows), "axes": len(axis_counts), "labels_per_axis": {"PASS": 6, "FAIL": 3, "HOLD": 3}, "optimizer_eligible": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
