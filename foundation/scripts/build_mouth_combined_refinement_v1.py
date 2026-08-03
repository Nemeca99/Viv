#!/usr/bin/env python3
"""Combine verified hold-only mouth refinements without opening authority.

This is packaging only.  It deliberately emits a hold-only source pack; the
normal campaign admission step is responsible for projecting rows into the
optimizer contract and must be followed by named preflight.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGNS = ROOT / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
PACK = CAMPAIGNS / "mouth_memory_and_cpu_gpu_refinement_v1"
SOURCES = (
    CAMPAIGNS / "mouth_memory_attribution_refinement_v1",
    CAMPAIGNS / "mouth_cpu_gpu_role_refinement_v2",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pack(root: Path) -> tuple[dict, list[dict], Path]:
    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "REFINEMENT_PACK_HOLD_ONLY":
        raise ValueError(f"source_not_hold_only:{root.name}")
    path = root / Path(str(manifest["jsonl"])).name
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != int(manifest["rows"]):
        raise ValueError(f"source_row_count:{root.name}")
    if sha256(path) != manifest.get("jsonl_sha256"):
        raise ValueError(f"source_hash_mismatch:{root.name}")
    if any(row.get("hold_only") is not True or row.get("optimizer_eligible") is not False for row in rows):
        raise ValueError(f"source_row_contract:{root.name}")
    return manifest, rows, path


def main() -> int:
    if PACK.exists():
        raise FileExistsError(f"refuse_to_overwrite:{PACK}")
    manifests: list[dict] = []
    rows: list[dict] = []
    source_paths: list[Path] = []
    seen: set[str] = set()
    for source in SOURCES:
        manifest, source_rows, source_path = load_pack(source)
        manifests.append(manifest)
        source_paths.append(source_path)
        for row in source_rows:
            pair_id = str(row.get("pair_id") or "")
            if not pair_id or pair_id in seen:
                raise ValueError(f"duplicate_pair_id:{pair_id}")
            seen.add(pair_id)
            rows.append(dict(row))

    PACK.mkdir(parents=True)
    output = PACK / "combined_refinement_hold.jsonl"
    output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "schema_version": "mouth_memory_and_cpu_gpu_refinement_v1",
        "status": "REFINEMENT_PACK_HOLD_ONLY",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows": len(rows),
        "source_packs": [
            {
                "manifest": str(source / "MANIFEST.json").replace("\\", "/"),
                "manifest_schema": item["schema_version"],
                "jsonl": str(path).replace("\\", "/"),
                "jsonl_sha256": sha256(path),
                "rows": item["rows"],
            }
            for source, item, path in zip(SOURCES, manifests, source_paths)
        ],
        "jsonl": str(output).replace("\\", "/"),
        "jsonl_sha256": sha256(output),
        "unique_pair_ids": len(seen),
        "all_targets_cpu_judge_pass": all(item.get("all_targets_cpu_judge_pass") is True for item in manifests),
        "optimizer_eligible_any": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
        "deployment_changed": False,
        "next_action": "separate_review_before_admission",
    }
    (PACK / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "status": manifest["status"], "rows": len(rows), "sha256": manifest["jsonl_sha256"], "output": str(PACK)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
