"""Audit candidate targets through the CPU entity and acronym boundaries."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.entity_we_contract import decide_entity_output  # noqa: E402
from voice_core.acronym_registry import repair_acronym_usage  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
SOURCE = ROOT / "campaigns/mouth_entity_we_candidate_v7/train_272_candidate_hold.jsonl"
OUT = ROOT / "campaigns/mouth_entity_we_candidate_v7/RUNTIME_BOUNDARY_AUDIT.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_overwrite:{OUT}")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()][256:]
    results = []
    errors = []
    for row in rows:
        entity = decide_entity_output(row["target"])
        acronym = repair_acronym_usage(row["target"])
        ok = entity["decision"] == "ACCEPT" and acronym["pass"] and not acronym["changed"]
        if not ok:
            errors.append({"candidate_id": row["candidate_id"], "entity": entity["decision"], "acronym_pass": acronym["pass"], "acronym_changed": acronym["changed"]})
        results.append({"candidate_id": row["candidate_id"], "entity_decision": entity["decision"], "entity_reason": entity["reason"], "acronym_pass": acronym["pass"], "acronym_changed": acronym["changed"]})
    report = {
        "schema_version": "mouth_entity_we_candidate_runtime_boundary_v1",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "RUNTIME_BOUNDARY_PASS_TRAINING_CLOSED" if not errors else "RUNTIME_BOUNDARY_FAIL",
        "source": str(SOURCE).replace("\\", "/"),
        "source_sha256": sha(SOURCE),
        "rows": len(rows),
        "errors": errors,
        "results": results,
        "optimizer_eligible": False,
        "training_authorized": False,
        "run_authorized": False,
        "admission_allowed": False,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("status", "rows", "errors", "optimizer_eligible", "training_authorized", "run_authorized", "admission_allowed")}, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
