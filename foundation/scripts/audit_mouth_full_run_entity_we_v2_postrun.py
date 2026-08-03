"""Produce a read-only, corrected post-run audit from the final checkpoint receipt."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_full_run_entity_we_v2"
SOURCE = ROOT / "CHECKPOINT_128_GENERATION.json"
OUT = ROOT / "CHECKPOINT_128_GENERATION_REAUDIT.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_overwrite:{OUT}")
    report = json.loads(SOURCE.read_text(encoding="utf-8"))
    cases = list(report.get("cases") or [])
    by_axis: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "pass": 0, "hold": 0, "fail": 0, "toolbleed": 0, "eos": 0})
    reasons: Counter[str] = Counter()
    for case in cases:
        axis = str(case.get("axis"))
        status = str(case.get("status")).lower()
        bucket = by_axis[axis]
        bucket["total"] += 1
        if status in {"pass", "hold", "fail"}:
            bucket[status] += 1
        bucket["toolbleed"] += int(case.get("toolbleed", 0))
        bucket["eos"] += int(bool(case.get("eos_pass")))
        reasons[str(case.get("reason") or "missing_reason")] += 1
    corrected = {
        "schema_version": "mouth_full_run_entity_we_postrun_reaudit_v1",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ABORT_BEHAVIORAL_GATE_MISS",
        "source_receipt": str(SOURCE).replace("\\", "/"),
        "source_receipt_sha256": sha(SOURCE),
        "checkpoint_step": report.get("checkpoint_step"),
        "rows": len(cases),
        "pass": sum(case.get("status") == "PASS" for case in cases),
        "hold": sum(case.get("status") == "HOLD" for case in cases),
        "fail": sum(case.get("status") == "FAIL" for case in cases),
        "toolbleed": sum(int(case.get("toolbleed", 0)) for case in cases),
        "eos_pass": sum(int(bool(case.get("eos_pass"))) for case in cases),
        "by_axis": dict(sorted(by_axis.items())),
        "reason_counts": dict(sorted(reasons.items())),
        "winner": False,
        "promotion_allowed": False,
        "deployment_changed": False,
        "training_authorized": False,
        "run_authorized": False,
        "automatic_retry": False,
        "note": "Corrects the source evaluator receipt's per-axis double-counting; case-level outputs are unchanged.",
    }
    OUT.write_text(json.dumps(corrected, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(OUT), "status": corrected["status"], "rows": corrected["rows"], "pass": corrected["pass"], "hold": corrected["hold"], "fail": corrected["fail"], "toolbleed": corrected["toolbleed"], "eos_pass": corrected["eos_pass"], "reason_counts": corrected["reason_counts"], "promotion_allowed": False, "run_authorized": False}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
