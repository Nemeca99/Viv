#!/usr/bin/env python3
"""Combine the validated v3 tag curriculum with train-only mouth-boundary bridges."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION / "scripts"))
from build_tag_prompt_datasets_v1 import TAGS, make_row, sha256_text, validate_row  # noqa: E402

SOURCE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_combined_candidate_v21_positive_308_admitted/positive_308_train_projection.jsonl"


def bridge_tag(axis: str) -> str:
    if axis in {"indirect_tool_agency", "acronym_contract"}:
        return "allowed_actions"
    if axis in {"architecture_cpu_gpu_role", "identity_humanization", "entity_we_boundary"}:
        return "identity"
    if axis in {"memory_ownership_and_service_attribution", "evidence_verification"}:
        return "knowledge"
    return "unknowns"


def build(output_dir: Path, source: Path = SOURCE, allowed_axes: set[str] | None = None, per_axis: int | None = None, v3_root: Path | None = None) -> dict:
    v3_root = v3_root or (FOUNDATION / "artifacts/auto/agentic/tag_prompt_datasets_20260802T035146Z/output_v4_expanded")
    all_source_rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(all_source_rows) != 308:
        raise ValueError(f"bridge_source_row_count:{len(all_source_rows)}")
    source_rows = [row for row in all_source_rows if allowed_axes is None or str(row["axis"]) in allowed_axes]
    if per_axis is not None:
        if per_axis <= 0:
            raise ValueError("per_axis_must_be_positive")
        grouped: dict[str, list[dict]] = {}
        for row in source_rows:
            grouped.setdefault(str(row["axis"]), []).append(row)
        sampled: list[dict] = []
        for axis in sorted(grouped):
            rows = grouped[axis]
            if len(rows) <= per_axis:
                sampled.extend(rows)
                continue
            indexes = [round(index * (len(rows) - 1) / (per_axis - 1)) for index in range(per_axis)] if per_axis > 1 else [0]
            sampled.extend(rows[index] for index in indexes)
        source_rows = sampled
    source_hash = sha256_text(json.dumps({"v3_manifest": json.loads((v3_root / "TAG_DATASETS_MANIFEST.json").read_text(encoding="utf-8")), "bridge_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "allowed_axes": sorted(allowed_axes or []), "per_axis": per_axis}, sort_keys=True))
    output_dir.mkdir(parents=True, exist_ok=False)
    seen: set[str] = set()
    datasets: dict[str, list[dict]] = {tag: [] for tag in TAGS}
    for tag in TAGS:
        for line in (v3_root / f"{tag}.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["pair_hash"] in seen:
                raise ValueError(f"duplicate_v3_pair_hash:{row['pair_hash']}")
            seen.add(row["pair_hash"])
            datasets[tag].append(row)
    next_index = Counter({tag: len(rows) for tag, rows in datasets.items()})
    for source_row in source_rows:
        tag = bridge_tag(str(source_row["axis"]))
        next_index[tag] += 1
        ask = str(source_row["ask"])
        if ask.startswith("Answer: "):
            ask = ask[8:]
        response = str(source_row.get("chosen") or source_row.get("target") or "").strip()
        if not response:
            raise ValueError(f"bridge_missing_response:{source_row.get('pair_id')}")
        row = make_row(tag, next_index[tag], "train", ask, response, source_hash)
        finding = validate_row(row, tag)
        if finding:
            raise ValueError(f"invalid_bridge_row:{source_row.get('pair_id')}:{finding}")
        if row["pair_hash"] in seen:
            raise ValueError(f"duplicate_bridge_pair_hash:{row['pair_hash']}")
        seen.add(row["pair_hash"])
        row["provenance"] = "governed_mouth_v21_bridge_train_only"
        row["source_refs"] = ["mouth_v21_positive_308_train_projection", f"axis:{source_row['axis']}", f"pair_id:{source_row['pair_id']}"]
        datasets[tag].append(row)
    manifest_datasets = {}
    total = 0
    for tag in TAGS:
        path = output_dir / f"{tag}.jsonl"
        payload = b"".join((json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8") for row in datasets[tag])
        path.write_bytes(payload)
        counts = dict(Counter(row["split"] for row in datasets[tag]))
        manifest_datasets[tag] = {"path": str(path).replace("\\", "/"), "sha256": hashlib.sha256(payload).hexdigest(), "rows": len(datasets[tag]), "counts_by_split": counts, "training_authorized": False, "run_authorized": False}
        total += len(datasets[tag])
    manifest = {"schema_version": "aios_tag_training_manifest_hybrid_v1", "created_utc": datetime.now(timezone.utc).isoformat(), "dataset_tags": list(TAGS), "datasets": manifest_datasets, "row_total": total, "target_type": "response_only_next_token", "v3_source_root": str(v3_root).replace("\\", "/"), "bridge_source": str(source).replace("\\", "/"), "bridge_source_rows": len(source_rows), "bridge_source_total_rows": len(all_source_rows), "bridge_axes": sorted(allowed_axes or []), "bridge_per_axis": per_axis, "source_template_hash": source_hash, "provenance": "v3_tag_curriculum_plus_v21_train_only_bridges", "split_policy": {"per_tag": {tag: dict(Counter(row["split"] for row in datasets[tag])) for tag in TAGS}, "v3_train": 12, "v3_development": 3, "v3_holdout": 3, "bridge_train_only": len(source_rows), "cross_tag_pair_overlap": 0}, "training_authorized": False, "run_authorized": False, "lease_opened": False, "authorization_changed": False, "deployment_changed": False}
    manifest_path = output_dir / "TAG_DATASETS_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"manifest": str(manifest_path).replace("\\", "/"), "rows": total, "bridge_rows": len(source_rows), "training_authorized": False, "run_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--axes", default="", help="Comma-separated bridge axes; empty means all axes.")
    parser.add_argument("--per-axis", type=int, default=None, help="Deterministically sample this many bridge rows per axis.")
    parser.add_argument("--v3-root", type=Path, default=None, help="Source v3-style dataset root; defaults to the canonical v4 expanded root.")
    args = parser.parse_args()
    axes = {item.strip() for item in args.axes.split(",") if item.strip()} or None
    print(json.dumps(build(args.output_dir, args.source, axes, args.per_axis, args.v3_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
