"""Freeze generated acronym failures as a judge-only repair corpus."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
sys.path.insert(0, str(FOUNDATION.parent))
from voice_core.acronym_registry import validate_acronym_usage  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_full_run_entity_we_v2"
SOURCE = ROOT / "CHECKPOINT_128_GENERATION.json"
OUT = ROOT / "ACRONYM_FAILURE_DELTA_V1.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_overwrite:{OUT}")
    report = json.loads(SOURCE.read_text(encoding="utf-8"))
    failures = []
    kinds: Counter[str] = Counter()
    for case in report.get("cases") or []:
        if case.get("status") != "FAIL" or case.get("reason") != "acronym_contract_violation":
            continue
        text = str(case.get("generated") or "")
        violations = validate_acronym_usage(text)
        for violation in violations:
            kinds[str(violation.get("kind"))] += 1
        failures.append({
            "pair_id": case.get("pair_id"),
            "split": case.get("split"),
            "axis": case.get("axis"),
            "ask": case.get("ask"),
            "generated": text,
            "violations": violations,
            "repair_status": "HOLD_ONLY",
            "optimizer_eligible": False,
            "training_authorized": False,
            "run_authorized": False,
        })
    delta = {
        "schema_version": "mouth_acronym_failure_delta_v1",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "HOLD_ONLY_FAILURE_DELTA",
        "source_receipt": str(SOURCE).replace("\\", "/"),
        "source_receipt_sha256": sha(SOURCE),
        "cases": len(failures),
        "violation_kinds": dict(sorted(kinds.items())),
        "failures": failures,
        "optimizer_eligible_any": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
        "next_action": "Design deterministic acronym surface repair and disjoint hold-only regression before another run.",
    }
    OUT.write_text(json.dumps(delta, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(OUT), "status": delta["status"], "cases": delta["cases"], "violation_kinds": delta["violation_kinds"], "optimizer_eligible_any": False, "training_authorized": False, "run_authorized": False}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
