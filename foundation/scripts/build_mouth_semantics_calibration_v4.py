"""Issue a corrected immutable calibration pack from the v3 design."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from scripts.build_mouth_semantics_calibration_v3 import GROUPS  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantics_calibration_v4"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_overwrite:{ROOT}")
    rows = []
    seen = set()
    for group, cases in GROUPS.items():
        for index, (ask, target, expected) in enumerate(cases):
            ask_hash = hashlib.sha256(ask.lower().encode("utf-8")).hexdigest()
            if ask_hash in seen:
                raise ValueError(f"duplicate_ask:{ask}")
            seen.add(ask_hash)
            rows.append({
                "case_id": f"sem-cal-v4-{group}-{index:02d}",
                "axis": group,
                "ask": ask,
                "target": target,
                "expected": expected,
                "split": "calibration",
                "optimizer_eligible": False,
                "hold_only": True,
                "training_authorized": False,
                "run_authorized": False,
                "ask_hash": ask_hash,
                "target_hash": hashlib.sha256(target.lower().encode("utf-8")).hexdigest(),
            })
    if len(rows) != 64:
        raise ValueError(f"final_count:{len(rows)}")
    ROOT.mkdir(parents=True)
    source = ROOT / "calibration_64.jsonl"
    source.write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "schema_version": "mouth_semantics_calibration_manifest_v4",
        "experiment_id": "mouth_semantics_calibration_v4",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "CALIBRATION_HOLD_ONLY",
        "rows": len(rows),
        "groups": {group: len(cases) for group, cases in GROUPS.items()},
        "optimizer_eligible_any": False,
        "training_authorized": False,
        "run_authorized": False,
        "files": {"calibration_64.jsonl": {"sha256": sha(source), "count": len(rows)}},
        "supersedes": "mouth_semantics_calibration_v3",
    }
    manifest_path = ROOT / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(ROOT), "manifest_sha256": sha(manifest_path), "rows": len(rows), "training_authorized": False, "run_authorized": False}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
