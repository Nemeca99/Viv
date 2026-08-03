#!/usr/bin/env python3
"""Re-render the identity-discretion corpus with the semantic evaluator's prompt."""
from __future__ import annotations

import argparse
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

from models.Training.code import train_stage1_generation as generation  # noqa: E402
from scripts import evaluate_mouth_combined_candidate_v21 as reference  # noqa: E402

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def eval_prompt(row: dict) -> str:
    packet = reference.packet({"ask": row["ask"], "axis": "identity_humanization", "pair_id": row["pair_id"]})
    return generation.render_openaster_prompt(packet, semantic_key=packet["semantic_key"])


def build(campaign_id: str, source_campaign: Path, parent_adapter: Path) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not (source_campaign / "train.jsonl").is_file() or not parent_adapter.is_file():
        raise FileNotFoundError("source_or_parent_missing")
    old_asks = {str(row.get("ask") or "") for row in load(CAMPAIGNS / "tag_prompt_campaign_v19_contractcanary16/train.jsonl")}
    selected = []
    for split in ("train", "development", "holdout"):
        for row in load(source_campaign / f"{split}.jsonl"):
            if str(row.get("ask") or "") in old_asks:
                raise ValueError(f"source_overlap_v19:{row.get('ask')}")
            item = dict(row)
            item["prompt"] = eval_prompt(row)
            item["prompt_sha256"] = digest(item["prompt"])
            item["source_prompt_sha256"] = row.get("prompt_sha256")
            item["prompt_alignment"] = "semantic_evaluator_v1"
            selected.append(item)
    root.mkdir(parents=True)
    files = {}
    counts = {}
    for split in ("train", "development", "holdout"):
        rows = [row for row in selected if row["split"] == split]
        path = root / f"{split}.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
        counts[split] = len(rows)
        files[split] = {"path": path.name, "rows": len(rows), "sha256": sha256(path)}
    manifest = {"schema_version": "aios_tag_identity_evalaligned_manifest_v1", "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED", "campaign_id": campaign_id, "created_utc": utc(), "curriculum": "identity_discretion_semantic_evaluator_prompt_v1", "source_campaign": {"path": str(source_campaign).replace("\\", "/"), "manifest_sha256": sha256(source_campaign / "manifest.json")}, "parent_adapter": {"path": str(parent_adapter).replace("\\", "/"), "sha256": sha256(parent_adapter)}, "prompt_alignment": "evaluate_mouth_semantic_batch_v1.reference.packet_and_render_openaster_prompt", "files": files, "rows": counts, "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "promotion_allowed": False, "deployment_changed": False, "next_action": "read_only_preflight_then_separate_execution_authorization"}
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    preflight = {"schema_version": "aios_tag_identity_evalaligned_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "findings": [], "files": files, "parent_adapter": manifest["parent_adapter"], "prompt_alignment": manifest["prompt_alignment"], "rows": counts, "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {"status": preflight["status"], "campaign_root": str(root).replace("\\", "/"), "rows": counts, "prompt_alignment": manifest["prompt_alignment"], "training_authorized": False, "run_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--source-campaign", type=Path, required=True)
    parser.add_argument("--parent-adapter", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id, args.source_campaign, args.parent_adapter), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
