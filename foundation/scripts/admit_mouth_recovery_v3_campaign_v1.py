#!/usr/bin/env python3
"""Create a closed campaign copy from the frozen train candidate and rebuilt evals.

This is admission/package construction only.  It does not authorize training,
open a lease, load a model, or invoke a trainer.
"""
from __future__ import annotations

import hashlib
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
TRAIN_SOURCE = TREE / "mouth_training_recovery_v3_semantic_projection_v1/train_candidate_256_hold.jsonl"
EVAL_ROOT = TREE / "mouth_training_recovery_v3_eval_rebuild_v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def dump_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a closed V3 campaign package; never authorizes execution.")
    parser.add_argument("--campaign-id", default="mouth_training_recovery_v3_campaign_v1")
    parser.add_argument("--refinement-root", type=Path, default=None, help="Optional hold-only refinement pack to append to the frozen train candidate.")
    args = parser.parse_args()
    campaign_id = str(args.campaign_id)
    if not campaign_id.startswith("mouth_training_recovery_v3_campaign_"):
        raise ValueError("campaign_id_namespace")
    ROOT = TREE / campaign_id
    if ROOT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{ROOT}")
    train_source = load_jsonl(TRAIN_SOURCE)
    if len(train_source) != 256:
        raise ValueError(f"train_source_count:{len(train_source)}")
    if any(row.get("optimizer_eligible") is not False or row.get("hold_only") is not True for row in train_source):
        raise ValueError("train_source_not_hold_only")

    refinement_rows = []
    refinement_manifest = None
    if args.refinement_root is not None:
        refinement_root = args.refinement_root.resolve()
        refinement_manifest = json.loads((refinement_root / "MANIFEST.json").read_text(encoding="utf-8"))
        refinement_path = refinement_root / Path(str(refinement_manifest["jsonl"])).name
        refinement_rows = load_jsonl(refinement_path)
        if refinement_manifest.get("status") != "REFINEMENT_PACK_HOLD_ONLY":
            raise ValueError("refinement_not_hold_only")
        if refinement_manifest.get("rows") != len(refinement_rows):
            raise ValueError("refinement_row_count")
        if any(row.get("hold_only") is not True or row.get("optimizer_eligible") is not False for row in refinement_rows):
            raise ValueError("refinement_row_contract")

    train_source = train_source + refinement_rows
    train_rows = []
    for index, source in enumerate(train_source):
        row = dict(source)
        row.update({
            "admission_status": "ADMITTED_TRAIN_READY",
            "hold_only": False,
            "optimizer_eligible": True,
            "response_only_loss_allowed": True,
            "split": "train",
            "admitted_index": index,
            "training_authorized": False,
            "run_authorized": False,
            "lora_authorized": False,
            "dpo_authorized": False,
        })
        train_rows.append(row)

    eval_names = ("development", "blind", "legacy", "auditor_negative")
    eval_rows = {name: load_jsonl(EVAL_ROOT / f"{name}.jsonl") for name in eval_names}
    expected = {"development": 64, "blind": 32, "legacy": 64, "auditor_negative": 20}
    if {name: len(rows) for name, rows in eval_rows.items()} != expected:
        raise ValueError(f"eval_counts:{ {name: len(rows) for name, rows in eval_rows.items()} }")
    if any(row.get("optimizer_eligible") is not False or row.get("hold_only") is not True for rows in eval_rows.values() for row in rows):
        raise ValueError("eval_not_hold_only")

    train_keys = {(row["pair_id"], row["ask"], row["target"]) for row in train_rows}
    eval_keys = set()
    for name, rows in eval_rows.items():
        for row in rows:
            key = (row["pair_id"], row["ask"], row["target"])
            if key in train_keys or key in eval_keys:
                raise ValueError(f"campaign_overlap:{name}:{row['pair_id']}")
            eval_keys.add(key)

    ROOT.mkdir(parents=True)
    files = {}
    train_filename = f"train_{len(train_rows)}.jsonl"
    dump_jsonl(ROOT / train_filename, train_rows)
    files["train"] = {"path": train_filename, "rows": len(train_rows), "sha256": sha256(ROOT / train_filename), "optimizer_eligible": True}
    for name, rows in eval_rows.items():
        dump_jsonl(ROOT / f"{name}.jsonl", rows)
        files[name] = {"path": f"{name}.jsonl", "rows": len(rows), "sha256": sha256(ROOT / f"{name}.jsonl"), "optimizer_eligible": False}

    manifest = {
        "schema_version": campaign_id,
        "campaign_id": campaign_id,
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "created_utc": utc(),
        "source_train_candidate": {"path": str(TRAIN_SOURCE).replace("\\", "/"), "sha256": sha256(TRAIN_SOURCE), "rows": 256},
        "source_eval_rebuild": {"path": str(EVAL_ROOT).replace("\\", "/"), "manifest_sha256": sha256(EVAL_ROOT / "manifest.json")},
        "files": files,
        "train_rows": len(train_rows),
        "eval_rows": {name: len(rows) for name, rows in eval_rows.items()},
        "training_authorized": False,
        "run_authorized": False,
        "lora_authorized": False,
        "dpo_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "promotion_allowed": False,
        "deployment_allowed": False,
        "next_action": "preflight_only_then_separate_execution_authorization",
    }
    if refinement_manifest is not None:
        manifest["source_train_refinement"] = {
            "path": str((args.refinement_root.resolve() / Path(str(refinement_manifest["jsonl"])).name)).replace("\\", "/"),
            "sha256": sha256(args.refinement_root.resolve() / Path(str(refinement_manifest["jsonl"])).name),
            "rows": len(refinement_rows),
        }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "status": manifest["status"], "output": str(ROOT), "files": files}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
