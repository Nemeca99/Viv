#!/usr/bin/env python3
"""Build a disjoint, CPU-judged residual curriculum for a parent-v19 canary."""
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
AXES = ("identity_humanization", "architecture_cpu_gpu_role", "memory_ownership_and_service_attribution")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canonical_row(source: dict, *, split: str, index: int) -> dict:
    ask = str(source["ask"])
    response = str(source.get("chosen") or source["target"])
    axis = str(source["axis"])
    prompt = render_targeted_patch_prompt(ask=ask, pair_id=f"residual-{axis}-{index:03d}", semantic_key=axis)
    pair_hash = text_sha(f"{axis}\n{ask}\n{response}")
    return {
        "schema_version": "aios_tag_residual_campaign_row_v1",
        "dataset_tag": axis,
        "example_id": f"residual-{axis}-{index:03d}",
        "pair_id": f"residual-{axis}-{index:03d}",
        "pair_hash": pair_hash,
        "split": split,
        "axis": axis,
        "ask": ask,
        "prompt": prompt,
        "prompt_sha256": text_sha(prompt),
        "response": response,
        "target": response,
        "source_pair_id": source.get("pair_id"),
        "source_role": source.get("source_role"),
        "source_hash": text_sha(json.dumps(source, sort_keys=True, ensure_ascii=False)),
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


def build(campaign_id: str, source_path: Path, parent_adapter: Path) -> dict:
    if not campaign_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in campaign_id):
        raise ValueError("campaign_id_must_be_simple_token")
    if not source_path.is_file() or not parent_adapter.is_file():
        raise FileNotFoundError("source_or_parent_missing")
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    v19_path = CAMPAIGNS / "tag_prompt_campaign_v19_contractcanary16" / "train.jsonl"
    v19_rows = load_rows(v19_path)
    v19_asks = {str(row.get("ask") or "") for row in v19_rows}
    v19_pairs = {str(row.get("pair_hash") or "") for row in v19_rows}
    grouped: dict[str, list[dict]] = {axis: [] for axis in AXES}
    rejected: list[dict] = []
    for source in load_rows(source_path):
        axis = str(source.get("axis") or "")
        if axis not in AXES or str(source.get("ask") or "") in v19_asks:
            continue
        verdict = judge(str(source.get("target") or source.get("chosen") or ""), axis=axis, ask=str(source.get("ask") or ""), use_cpu_sensor=False)
        if verdict.get("status") != "PASS":
            rejected.append({"pair_id": source.get("pair_id"), "axis": axis, "status": verdict.get("status")})
            continue
        grouped[axis].append(source)
    if any(len(grouped[axis]) < 16 for axis in AXES):
        raise ValueError({axis: len(grouped[axis]) for axis in AXES})
    selected: list[dict] = []
    counts = {"train": 0, "development": 0, "holdout": 0}
    for axis in AXES:
        for index, source in enumerate(grouped[axis][:16]):
            split = "train" if index < 8 else "development" if index < 12 else "holdout"
            row = canonical_row(source, split=split, index=len(selected))
            if row["pair_hash"] in v19_pairs:
                raise ValueError(f"pair_overlap_v19:{row['example_id']}")
            selected.append(row)
            counts[split] += 1
    root.mkdir(parents=True)
    files = {}
    for split in ("train", "development", "holdout"):
        path = root / f"{split}.jsonl"
        rows = [row for row in selected if row["split"] == split]
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
        files[split] = {"path": path.name, "rows": len(rows), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_residual_campaign_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "identity_architecture_memory_residual_v1",
        "source": {"path": str(source_path).replace("\\", "/"), "sha256": sha256(source_path), "judge": "evaluator_v2_3_hybrid"},
        "parent_adapter": {"path": str(parent_adapter).replace("\\", "/"), "sha256": sha256(parent_adapter)},
        "files": files,
        "rows": counts,
        "axes": list(AXES),
        "rejected_source_rows": rejected,
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
    preflight = {
        "schema_version": "aios_tag_residual_preflight_v1",
        "status": "PREFLIGHT_PASS_TRAINING_CLOSED",
        "recorded_utc": utc(),
        "campaign_root": str(root).replace("\\", "/"),
        "manifest_sha256": sha256(manifest_path),
        "findings": [],
        "files": files,
        "parent_adapter": manifest["parent_adapter"],
        "rows": counts,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "model_loaded": False,
        "next_action": "separate_execution_authorization",
    }
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {"status": preflight["status"], "campaign_root": str(root).replace("\\", "/"), "rows": counts, "axes": list(AXES), "rejected_source_rows": len(rejected), "training_authorized": False, "run_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--parent-adapter", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.campaign_id, args.source, args.parent_adapter), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
