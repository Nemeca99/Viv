"""Issue the corrected immutable acronym-surface regression pack."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from scripts.build_mouth_acronym_surface_regression_v2 import CASES  # noqa: E402

ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_acronym_surface_regression_v3"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_overwrite:{ROOT}")
    rows = []
    seen = set()
    for group in CASES:
        for case_id, text, expected in group:
            digest = hashlib.sha256(text.lower().encode("utf-8")).hexdigest()
            if digest in seen:
                raise ValueError(f"duplicate_text:{text}")
            seen.add(digest)
            rows.append({"case_id": f"acronym-surface-v3-{case_id}", "text": text, "expected": expected, "split": "hold_only", "optimizer_eligible": False, "training_authorized": False, "run_authorized": False, "text_sha256": digest})
    if len(rows) != 48:
        raise ValueError(f"count:{len(rows)}")
    categories = Counter(row["expected"] for row in rows)
    ROOT.mkdir(parents=True)
    source = ROOT / "regression_48.jsonl"
    source.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {"schema_version": "mouth_acronym_surface_regression_manifest_v3", "experiment_id": "mouth_acronym_surface_regression_v3", "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "HOLD_ONLY_TRAINING_CLOSED", "rows": len(rows), "categories": dict(sorted(categories.items())), "optimizer_eligible_any": False, "training_authorized": False, "run_authorized": False, "files": {"regression_48.jsonl": {"sha256": sha(source), "count": len(rows)}}, "supersedes": "mouth_acronym_surface_regression_v2"}
    manifest_path = ROOT / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(ROOT), "manifest_sha256": sha(manifest_path), "rows": len(rows), "categories": dict(sorted(categories.items())), "training_authorized": False, "run_authorized": False}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
