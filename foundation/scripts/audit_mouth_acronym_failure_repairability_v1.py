"""Audit safe CPU repairability of a frozen acronym failure delta."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
sys.path.insert(0, str(FOUNDATION.parent))
from voice_core.acronym_registry import repair_acronym_usage  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_full_run_entity_we_v2"
SOURCE = ROOT / "ACRONYM_FAILURE_DELTA_V1.json"
OUT = ROOT / "ACRONYM_FAILURE_REPAIRABILITY_V1.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_overwrite:{OUT}")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = []
    status_counts: Counter[str] = Counter()
    unresolved_kinds: Counter[str] = Counter()
    for failure in source.get("failures") or []:
        repair = repair_acronym_usage(str(failure.get("generated") or ""))
        status = "SAFE_REPAIR" if repair["changed"] and repair["pass"] else "UNRESOLVED_HOLD"
        status_counts[status] += 1
        for item in repair.get("unresolved") or []:
            unresolved_kinds[str(item.get("kind") or "unknown")] += 1
        rows.append({
            "pair_id": failure.get("pair_id"),
            "split": failure.get("split"),
            "axis": failure.get("axis"),
            "status": status,
            "generated": failure.get("generated"),
            "repair": repair,
            "optimizer_eligible": False,
            "training_authorized": False,
            "run_authorized": False,
        })
    report = {
        "schema_version": "mouth_acronym_failure_repairability_v1",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "HOLD_ONLY_REPAIRABILITY_AUDIT",
        "source_delta": str(SOURCE).replace("\\", "/"),
        "source_delta_sha256": sha(SOURCE),
        "cases": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "unresolved_kinds": dict(sorted(unresolved_kinds.items())),
        "rows": rows,
        "optimizer_eligible_any": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
        "next_action": "Keep unresolved compounds as hard failures; use safe repair only at the governed CPU speech boundary.",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "target": str(OUT),
        "status": report["status"],
        "cases": report["cases"],
        "status_counts": report["status_counts"],
        "unresolved_kinds": report["unresolved_kinds"],
        "optimizer_eligible_any": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
