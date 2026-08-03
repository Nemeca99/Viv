#!/usr/bin/env python3
"""Build a preparation-only fresh-base tag campaign from a validated source."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGNS = Path(__file__).resolve().parents[1] / "artifacts/auto/agentic/tag_training_campaigns"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build(campaign_id: str, source: Path, base_config: Path) -> dict:
    if not campaign_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in campaign_id):
        raise ValueError("campaign_id_must_be_simple_token")
    if not source.is_dir() or not (source / "manifest.json").is_file():
        raise FileNotFoundError(f"source_campaign_missing:{source}")
    if not base_config.is_file():
        raise FileNotFoundError(f"base_config_missing:{base_config}")
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    source_manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if source_manifest.get("status") not in {"CAMPAIGN_EXECUTED_NO_PROMOTION", "CAMPAIGN_ADMITTED_TRAINING_CLOSED", "CAMPAIGN_EXECUTION_AUTHORIZED"}:
        raise ValueError(f"source_campaign_not_validated:{source_manifest.get('status')}")
    root.mkdir(parents=True)
    files = {}
    counts = {}
    for split in ("train", "development", "holdout"):
        src = source / f"{split}.jsonl"
        if not src.is_file():
            raise FileNotFoundError(f"source_split_missing:{split}")
        data = src.read_bytes()
        dst = root / f"{split}.jsonl"
        dst.write_bytes(data)
        parsed = rows(dst)
        counts[split] = len(parsed)
        if split == "train" and any(r.get("optimizer_eligible") is not True or r.get("split") != "train" for r in parsed):
            raise ValueError("source_train_contract_invalid")
        if split != "train" and any(r.get("hold_only") is not True or r.get("split") != split for r in parsed):
            raise ValueError(f"source_{split}_contract_invalid")
        files[split] = {"path": dst.name, "rows": len(parsed), "sha256": sha256(dst)}
    manifest = {
        "schema_version": "aios_fresh_base_tag_campaign_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "parent_mode": "fresh_base",
        "parent_adapter": None,
        "base_model_config": {"path": str(base_config).replace("\\", "/"), "sha256": sha256(base_config)},
        "source_campaign": {"path": str(source).replace("\\", "/"), "manifest_sha256": sha256(source / "manifest.json")},
        "source_provenance": source_manifest.get("source_manifest") or source_manifest.get("source_campaign"),
        "files": files,
        "rows": counts,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "promotion_allowed": False,
        "deployment_changed": False,
        "next_action": "read_only_preflight_then_separate_execution_authorization",
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    preflight = {
        "schema_version": "aios_fresh_base_tag_preflight_v1",
        "status": "PREFLIGHT_PASS_TRAINING_CLOSED",
        "recorded_utc": utc(),
        "campaign_root": str(root).replace("\\", "/"),
        "manifest_sha256": sha256(root / "manifest.json"),
        "findings": [],
        "parent_mode": "fresh_base",
        "base_model_config": manifest["base_model_config"],
        "files": files,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "model_loaded": False,
        "next_action": "separate_execution_authorization",
    }
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {"status": preflight["status"], "campaign_root": str(root).replace("\\", "/"), "rows": counts, "training_authorized": False, "run_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--source-campaign", type=Path, required=True)
    parser.add_argument("--base-config", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id, args.source_campaign, args.base_config), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
