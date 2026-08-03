#!/usr/bin/env python3
"""Package the seven tag datasets into a closed, preflightable campaign.

This module is preparation-only. It never loads a model, opens a lease, changes
authorization, trains, promotes, or deploys. The resulting campaign is not
accepted by a trainer until a separate governed runner is written and a named
execution authorization is issued.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET_ROOT = FOUNDATION / "artifacts/auto/agentic/tag_prompt_datasets_20260802T035146Z/output_v2"
CAMPAIGN_ROOT = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
TAGS = ("identity", "knowledge", "telemetry", "user_request", "allowed_actions", "unknowns", "rendering_rules")
EOS = "<|im_end|>"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_source(manifest: dict[str, Any], dataset_root: Path = DATASET_ROOT) -> tuple[list[str], dict[str, Any]]:
    findings: list[str] = []
    if manifest.get("dataset_tags") != list(TAGS):
        findings.append("dataset_tags")
    if manifest.get("target_type") != "response_only_next_token":
        findings.append("target_type")
    source_rows: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = {}
    seen_pairs: set[str] = set()
    for tag in TAGS:
        path = dataset_root / f"{tag}.jsonl"
        if not path.is_file():
            findings.append(f"missing:{tag}")
            continue
        spec = (manifest.get("datasets") or {}).get(tag) or {}
        if sha256(path) != spec.get("sha256"):
            findings.append(f"hash:{tag}")
        rows = load_jsonl(path)
        counts[tag] = dict(Counter(str(row.get("split")) for row in rows))
        policy = manifest.get("split_policy") or {}
        per_tag_policy = (policy.get("per_tag") or {}).get(tag) or {}
        expected_counts = {"train": int(per_tag_policy.get("train", policy.get("train", 0))), "development": int(per_tag_policy.get("development", policy.get("development", 0))), "holdout": int(per_tag_policy.get("holdout", policy.get("holdout", 0)))}
        if len(rows) != sum(expected_counts.values()) or counts[tag] != expected_counts:
            findings.append(f"split_counts:{tag}")
        for row in rows:
            prompt = str(row.get("prompt") or "")
            response = str(row.get("response") or "")
            text = str(row.get("text") or "")
            if row.get("dataset_tag") != tag or row.get("target_type") != "response_only_next_token":
                findings.append(f"row_identity:{tag}:{row.get('example_id')}")
            if text != prompt + response + EOS:
                findings.append(f"roundtrip:{tag}:{row.get('example_id')}")
            if row.get("response_start_char") != len(prompt) or row.get("response_end_char") != len(prompt) + len(response):
                findings.append(f"boundaries:{tag}:{row.get('example_id')}")
            pair_hash = str(row.get("pair_hash") or "")
            if not pair_hash or pair_hash in seen_pairs:
                findings.append(f"pair_overlap:{tag}:{row.get('example_id')}")
            seen_pairs.add(pair_hash)
            source_rows.append({"tag": tag, **row})
    summary = {"counts_by_tag": counts, "rows": len(source_rows), "unique_pair_hashes": len(seen_pairs)}
    policy = manifest.get("split_policy") or {}
    if policy.get("per_tag"):
        expected_total = sum(sum(int((policy["per_tag"].get(tag) or {}).get(key, 0)) for key in ("train", "development", "holdout")) for tag in TAGS)
    else:
        expected_total = len(TAGS) * sum(int(policy.get(key, 0)) for key in ("train", "development", "holdout"))
    if len(source_rows) != expected_total or len(seen_pairs) != expected_total:
        findings.append("row_total_or_pair_total")
    return findings, {"summary": summary, "rows": source_rows}


def canonical_row(row: dict[str, Any], *, optimizer_eligible: bool, hold_only: bool) -> dict[str, Any]:
    tag = str(row["tag"])
    return {
        "schema_version": "aios_tag_campaign_row_v1",
        "dataset_tag": tag,
        "example_id": row["example_id"],
        "split": row["split"],
        "target_type": "response_only_next_token",
        "prompt": row["prompt"],
        "response": row["response"],
        "text": row["text"],
        "response_start_char": row["response_start_char"],
        "response_end_char": row["response_end_char"],
        "response_eos_token": row["response_eos_token"],
        "pair_hash": row["pair_hash"],
        "prompt_sha256": row["prompt_sha256"],
        "source_hash": row["source_hash"],
        "provenance": row["provenance"],
        "source_refs": row["source_refs"],
        "optimizer_eligible": optimizer_eligible,
        "response_only_loss_allowed": optimizer_eligible,
        "hold_only": hold_only,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "promotion_allowed": False,
        "deployment_changed": False,
    }


def build_campaign(campaign_id: str, parent_adapter: Path, dataset_root: Path = DATASET_ROOT) -> dict[str, Any]:
    if not campaign_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in campaign_id):
        raise ValueError("campaign_id_must_be_simple_token")
    if not parent_adapter.is_file():
        raise FileNotFoundError(f"parent_adapter_missing:{parent_adapter}")
    manifest_path = dataset_root / "TAG_DATASETS_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    findings, loaded = validate_source(manifest, dataset_root)
    if findings:
        raise ValueError(json.dumps({"status": "SOURCE_VALIDATION_FAIL", "findings": findings}, sort_keys=True))
    root = CAMPAIGN_ROOT / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    root.mkdir(parents=True)
    rows = loaded["rows"]
    files: dict[str, Any] = {}
    for split, optimizer_eligible, hold_only in (("train", True, False), ("development", False, True), ("holdout", False, True)):
        selected = [canonical_row(row, optimizer_eligible=optimizer_eligible, hold_only=hold_only) for row in rows if row["split"] == split]
        path = root / f"{split}.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in selected), encoding="utf-8", newline="\n")
        files[split] = {"path": path.name, "rows": len(selected), "sha256": sha256(path), "optimizer_eligible": optimizer_eligible, "hold_only": hold_only}
    output_manifest = {
        "schema_version": "aios_tag_campaign_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "source_manifest": {"path": str(manifest_path).replace("\\", "/"), "sha256": sha256(manifest_path)},
        "source_template_hash": manifest["source_template_hash"],
        "parent_adapter": {"path": str(parent_adapter).replace("\\", "/"), "sha256": sha256(parent_adapter)},
        "dataset_tags": list(TAGS),
        "files": files,
        "rows": {"train": files["train"]["rows"], "development": files["development"]["rows"], "holdout": files["holdout"]["rows"]},
        "source_summary": loaded["summary"],
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "promotion_allowed": False,
        "deployment_changed": False,
        "next_action": "read_only_preflight_then_separate_execution_authorization",
    }
    (root / "manifest.json").write_text(json.dumps(output_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    preflight = {"schema_version": "aios_tag_campaign_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "findings": [], "manifest_sha256": sha256(root / "manifest.json"), "parent_adapter": output_manifest["parent_adapter"], "files": files, "source_summary": loaded["summary"], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {"status": preflight["status"], "campaign_root": str(root).replace("\\", "/"), "files": files, "training_authorized": False, "run_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--parent-adapter", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    args = parser.parse_args()
    print(json.dumps(build_campaign(args.campaign_id, args.parent_adapter, args.dataset_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
