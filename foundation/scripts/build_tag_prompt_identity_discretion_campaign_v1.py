#!/usr/bin/env python3
"""Build a compact identity-discretion campaign with explicit negative coverage."""
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

from lib.evaluator_v2_3_hybrid import judge  # noqa: E402
from models.Training.code.train_mouth_v3_targeted_patch import render_targeted_patch_prompt  # noqa: E402

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
GUARD = FOUNDATION / "artifacts/auto/agentic/tag_prompt_datasets_20260802T035146Z/output_acronym_identity_guard_v3/identity.jsonl"
V3_SOURCE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v3_semantic_projection_v1/train_candidate_256_hold.jsonl"


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


def make_row(source: dict, index: int, split: str, *, guard_prompt: bool) -> dict:
    ask = str(source["ask"])
    response = str(source.get("response") or source.get("target") or source["chosen"])
    pair_id = f"identity-discretion-{index:03d}"
    prompt = str(source["prompt"]) if guard_prompt and source.get("prompt") else render_targeted_patch_prompt(ask=ask, pair_id=pair_id, semantic_key="identity_humanization")
    return {
        "schema_version": "aios_tag_identity_discretion_row_v1",
        "dataset_tag": "identity_humanization",
        "example_id": pair_id,
        "pair_id": pair_id,
        "pair_hash": digest(f"identity_humanization\n{ask}\n{response}"),
        "split": split,
        "axis": "identity_humanization",
        "ask": ask,
        "prompt": prompt,
        "prompt_sha256": digest(prompt),
        "response": response,
        "target": response,
        "source_pair_id": source.get("pair_hash") or source.get("pair_id"),
        "source_provenance": source.get("provenance") or source.get("source_role"),
        "optimizer_eligible": split == "train",
        "response_only_loss_allowed": split == "train",
        "hold_only": split != "train",
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "promotion_allowed": False,
        "deployment_changed": False,
    }


def build(campaign_id: str, parent_adapter: Path) -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not parent_adapter.is_file() or not GUARD.is_file() or not V3_SOURCE.is_file():
        raise FileNotFoundError("identity_source_or_parent_missing")
    v19 = load(CAMPAIGNS / "tag_prompt_campaign_v19_contractcanary16/train.jsonl")
    old_asks = {str(row.get("ask") or "") for row in v19}
    old_pairs = {str(row.get("pair_hash") or "") for row in v19}
    guard = load(GUARD)
    v3 = [row for row in load(V3_SOURCE) if row.get("axis") == "identity_humanization"]
    candidates: list[tuple[dict, bool]] = [(row, True) for row in guard]
    guard_asks = {str(row.get("ask") or "") for row in guard}
    candidates.extend((row, False) for row in v3 if str(row.get("ask") or "") not in guard_asks)
    selected: list[dict] = []
    seen_asks: set[str] = set()
    for source, guard_prompt in candidates:
        ask = str(source.get("ask") or "")
        response = str(source.get("response") or source.get("target") or source.get("chosen") or "")
        if not ask or ask in old_asks or ask in seen_asks:
            continue
        verdict = judge(response, axis="identity_humanization", ask=ask, use_cpu_sensor=False)
        if verdict.get("status") != "PASS":
            continue
        selected.append((source, guard_prompt))
        seen_asks.add(ask)
        if len(selected) >= 28:
            break
    if len(selected) < 28:
        raise ValueError(f"identity_candidate_count:{len(selected)}")
    rows = []
    for index, (source, guard_prompt) in enumerate(selected):
        split = "train" if index < 16 else "development" if index < 22 else "holdout"
        row = make_row(source, index, split, guard_prompt=guard_prompt)
        if row["pair_hash"] in old_pairs:
            raise ValueError(f"pair_overlap_v19:{row['example_id']}")
        rows.append(row)
    root.mkdir(parents=True)
    files = {}
    for split in ("train", "development", "holdout"):
        path = root / f"{split}.jsonl"
        chosen = [row for row in rows if row["split"] == split]
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in chosen), encoding="utf-8", newline="\n")
        files[split] = {"path": path.name, "rows": len(chosen), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_identity_discretion_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "identity_discretion_acronym_gate_v1",
        "sources": {"identity_guard": {"path": str(GUARD).replace("\\", "/"), "sha256": sha256(GUARD)}, "v3_identity": {"path": str(V3_SOURCE).replace("\\", "/"), "sha256": sha256(V3_SOURCE)}},
        "parent_adapter": {"path": str(parent_adapter).replace("\\", "/"), "sha256": sha256(parent_adapter)},
        "files": files,
        "rows": {"train": 16, "development": 6, "holdout": 6},
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "promotion_allowed": False,
        "deployment_changed": False,
        "next_action": "read_only_preflight_then_separate_execution_authorization",
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    preflight = {"schema_version": "aios_tag_identity_discretion_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "findings": [], "files": files, "parent_adapter": manifest["parent_adapter"], "rows": manifest["rows"], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {"status": preflight["status"], "campaign_root": str(root).replace("\\", "/"), "rows": manifest["rows"], "training_authorized": False, "run_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--parent-adapter", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id, args.parent_adapter), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
