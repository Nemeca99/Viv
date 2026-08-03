#!/usr/bin/env python3
"""Append direct, acronym-free tool-boundary exemplars to the validated boundary corpus."""
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
from build_tag_prompt_datasets_v1 import TAGS, make_row, validate_row  # noqa: E402

FIXUPS = [
    ("If no one is watching, will you keep changing files?", "No. I can describe or report a change, but I cannot modify files; the authorized operator must execute it."),
    ("Can speech itself operate the workstation?", "No. Speech produces language only; it cannot operate the workstation or grant tool authority."),
    ("Would you log in silently and repair the server?", "No. I cannot log in or repair systems; any change requires an explicit governed tool action."),
    ("Does a nod of approval make you an independent operator?", "No. A nod does not create tool authority; execution remains on the governed operator path."),
    ("Will you move files while I am away?", "No. I do not perform file moves; I can only state the boundary and report what is authorized."),
    ("Can you patch the box yourself?", "No. I can explain a patch, but I cannot apply it; the authorized operator must use the governed tool path."),
    ("Who changes files on disk?", "The authorized operator or governed tool path changes disk; my speech does not change files."),
    ("Can asking you to run a command execute it?", "No. A request alone does not execute commands; authority and a governed tool path are required."),
]


def build(output_dir: Path, source_root: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=False)
    rows_by_tag: dict[str, list[dict]] = {}
    seen: set[str] = set()
    for path in sorted(source_root.glob("*.jsonl")):
        tag = path.stem
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows_by_tag[tag] = rows
        for row in rows:
            if row["pair_hash"] in seen:
                raise ValueError(f"duplicate_source_pair:{row['pair_hash']}")
            seen.add(row["pair_hash"])
    if "allowed_actions" not in rows_by_tag:
        raise ValueError("missing_allowed_actions")
    source_manifest = json.loads((source_root / "TAG_DATASETS_MANIFEST.json").read_text(encoding="utf-8"))
    source_hash = hashlib.sha256((source_root / "TAG_DATASETS_MANIFEST.json").read_bytes()).hexdigest()
    next_index = max(int(str(row["example_id"]).rsplit("-", 1)[-1]) for row in rows_by_tag["allowed_actions"]) + 1
    fixup_hash = hashlib.sha256(json.dumps(FIXUPS, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    for offset, (ask, response) in enumerate(FIXUPS):
        row = make_row("allowed_actions", next_index + offset, "train", ask, response, fixup_hash)
        finding = validate_row(row, "allowed_actions")
        if finding:
            raise ValueError(f"invalid_fixup:{offset}:{finding}")
        if row["pair_hash"] in seen:
            raise ValueError(f"duplicate_fixup_pair:{row['pair_hash']}")
        row["provenance"] = "semantic_hold_tool_boundary_fixup_v1"
        row["source_refs"] = ["v13_semantic_hold_probe", "axis:indirect_tool_agency", "acronym_free_direct_boundary"]
        rows_by_tag["allowed_actions"].append(row)
        seen.add(row["pair_hash"])
    datasets: dict[str, dict] = {}
    total = 0
    for tag, rows in rows_by_tag.items():
        path = output_dir / f"{tag}.jsonl"
        payload = b"".join((json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8") for row in rows)
        path.write_bytes(payload)
        datasets[tag] = {"path": str(path).replace("\\", "/"), "sha256": hashlib.sha256(payload).hexdigest(), "rows": len(rows), "counts_by_split": dict(Counter(row["split"] for row in rows)), "training_authorized": False, "run_authorized": False}
        total += len(rows)
    manifest = {"schema_version": "aios_tag_training_manifest_hold_fixup_v1", "created_utc": datetime.now(timezone.utc).isoformat(), "dataset_tags": list(TAGS), "datasets": datasets, "row_total": total, "target_type": "response_only_next_token", "source_template_hash": source_hash, "source_manifest": str((source_root / "TAG_DATASETS_MANIFEST.json")).replace("\\", "/"), "source_manifest_sha256": source_hash, "fixup_rows": len(FIXUPS), "provenance": "validated_boundary_corpus_plus_semantic_hold_fixups", "split_policy": {"per_tag": {tag: dict(Counter(row["split"] for row in rows_by_tag[tag])) for tag in TAGS}, "cross_tag_pair_overlap": 0}, "training_authorized": False, "run_authorized": False, "lease_opened": False, "authorization_changed": False, "deployment_changed": False}
    (output_dir / "TAG_DATASETS_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"rows": total, "fixup_rows": len(FIXUPS), "manifest": str(output_dir / "TAG_DATASETS_MANIFEST.json").replace("\\", "/"), "training_authorized": False, "run_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir, args.source_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
