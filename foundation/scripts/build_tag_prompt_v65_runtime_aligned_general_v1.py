#!/usr/bin/env python3
"""Admit the disjoint runtime-aligned general-fluency canary."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
SOURCE = FOUNDATION / "artifacts/auto/agentic/tag_prompt_datasets_20260802T035146Z/output_runtime_aligned_v4"
V19 = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns/tag_prompt_campaign_v19_contractcanary16"
CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_rows() -> list[dict]:
    rows = []
    for path in sorted(SOURCE.glob("*.jsonl")):
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return rows


def build(campaign_id: str) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not SOURCE.is_dir() or not PARENT.is_file():
        raise FileNotFoundError("source_or_parent_missing")
    rows = load_rows()
    if len(rows) != 45:
        raise ValueError(f"source_row_count:{len(rows)}")
    source_hashes = {str(row.get("source_hash") or row.get("pair_hash")) for row in rows}
    v19_hashes = {str(json.loads(line).get("source_hash") or json.loads(line).get("pair_hash")) for line in (V19 / "train.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()}
    overlap = source_hashes & v19_hashes
    if overlap:
        raise ValueError(f"source_overlap_v19:{len(overlap)}")
    for row in rows:
        if row.get("split") not in {"train", "development", "holdout"} or not row.get("prompt") or not row.get("response"):
            raise ValueError(f"row_contract:{row.get('example_id')}")
    root.mkdir(parents=True)
    files = {}
    for split in ("train", "development", "holdout"):
        path = root / f"{split}.jsonl"
        selected = []
        for row in rows:
            if row["split"] != split:
                continue
            item = dict(row)
            item.update({
                "schema_version": "aios_tag_v65_runtime_aligned_row_v1",
                "optimizer_eligible": split == "train",
                "response_only_loss_allowed": split == "train",
                "hold_only": split != "train",
                "training_authorized": False,
                "run_authorized": False,
                "lease_opened": False,
                "gpu_steps": 0,
                "promotion_allowed": False,
                "deployment_changed": False,
            })
            selected.append(item)
        path.write_text("".join(json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n" for item in selected), encoding="utf-8", newline="\n")
        files[split] = {"path": path.name, "rows": len(selected), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_v65_runtime_aligned_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "runtime_aligned_general_fluency",
        "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha256(PARENT)},
        "source": {"root": str(SOURCE).replace("\\", "/"), "files": {path.name: sha256(path) for path in sorted(SOURCE.glob("*.jsonl"))}, "v19_manifest_sha256": sha256(V19 / "manifest.json"), "disjoint_train_hashes": True, "overlap_count": 0},
        "files": files,
        "rows": {key: value["rows"] for key, value in files.items()},
        "unique_source_hashes": len(source_hashes),
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "promotion_allowed": False,
        "deployment_changed": False,
        "next_action": "read_only_preflight_then_separate_execution_authorization",
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    preflight = {
        "schema_version": "aios_tag_v65_runtime_aligned_preflight_v1",
        "status": "PREFLIGHT_PASS_TRAINING_CLOSED",
        "recorded_utc": utc(),
        "campaign_root": str(root).replace("\\", "/"),
        "manifest_sha256": sha256(manifest_path),
        "files": files,
        "parent_adapter": manifest["parent_adapter"],
        "rows": manifest["rows"],
        "findings": [],
        "source_overlap_v19": 0,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "model_loaded": False,
        "next_action": "separate_execution_authorization",
    }
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id), indent=2, sort_keys=True))
