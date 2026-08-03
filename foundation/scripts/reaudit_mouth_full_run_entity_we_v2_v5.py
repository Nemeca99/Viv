"""Read-only re-audit of an existing checkpoint receipt with evaluator v5 rules."""
from __future__ import annotations

from collections import Counter
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

from lib.evaluator_v2_3_hybrid_v1_2_5 import judge  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_full_run_entity_we_v2"
SOURCE = ROOT / "CHECKPOINT_128_GENERATION.json"
OUT = ROOT / "CHECKPOINT_128_GENERATION_REAUDIT_V5.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_overwrite:{OUT}")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = []
    counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for case in source.get("cases") or []:
        axis = str(case.get("axis") or "")
        generated = str(case.get("generated") or "")
        result = judge(generated, axis=axis)
        status = str(result.get("status") or "HOLD")
        deterministic = result.get("deterministic") or {}
        reason = str(deterministic.get("reason") or "unknown")
        counts[status] += 1
        reasons[reason] += 1
        rows.append({
            "case_id": case.get("pair_id") or case.get("case_id"),
            "axis": axis,
            "split": case.get("split"),
            "generated": generated,
            "status": status,
            "reason": reason,
            "acronym_contract": deterministic.get("acronym_contract"),
            "eos_pass": case.get("eos_pass"),
            "toolbleed": case.get("toolbleed"),
        })
    report = {
        "schema_version": "mouth_full_run_entity_we_v2_reaudit_v5",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "READ_ONLY_REAUDIT",
        "source_receipt": str(SOURCE).replace("\\", "/"),
        "source_receipt_sha256": sha(SOURCE),
        "checkpoint_step": source.get("checkpoint_step"),
        "rows": len(rows),
        "counts": dict(sorted(counts.items())),
        "reason_counts": dict(sorted(reasons.items())),
        "eos_pass": sum(1 for row in rows if row["eos_pass"] is True),
        "toolbleed_zero": sum(1 for row in rows if row["toolbleed"] == 0),
        "rows_detail": rows,
        "optimizer_eligible": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
        "note": "Read-only score under the expanded evaluator; no generation, training, lease, or deployment occurred.",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("status", "checkpoint_step", "rows", "counts", "reason_counts", "optimizer_eligible", "training_authorized", "run_authorized")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
