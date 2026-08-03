#!/usr/bin/env python3
"""Build a manifest-locked 256-row full-run corpus with entity-we anchors.

This is construction only. It never authorizes, opens a lease, or trains.
The source recovery corpus is preserved byte-for-byte; three identity rows are
replaced by positive project/system-we examples from the hold-only contract.
Human-we and ambiguous-we examples remain judge-only.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
ROOT = TREE / "mouth_full_run_entity_we_v1"
SOURCE = TREE / "mouth_training_recovery_v2_anchor_coverage_v1_3"
ENTITY = TREE / "mouth_entity_we_contract_v1"
TRAIN = ROOT / "train_256.jsonl"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_overwrite:{ROOT}")
    source_train = SOURCE / "train_256.jsonl"
    source_dev = SOURCE / "development_64.jsonl"
    source_blind = SOURCE / "blind_32.jsonl"
    entity_rows = rows(ENTITY / "entity_we_contract_examples.jsonl")
    source_rows = rows(source_train)
    if len(source_rows) != 256 or len(entity_rows) != 6:
        raise ValueError("source_count_mismatch")
    positives = [row for row in entity_rows if not row["negative"]]
    negatives = [row for row in entity_rows if row["negative"]]
    if len(positives) != 3 or len(negatives) != 3:
        raise ValueError("entity_contract_count_mismatch")

    # Keep the proven 64-row-per-axis balance. Replace exactly three identity
    # rows rather than growing the corpus beyond the trainer's locked contract.
    identity_indexes = [i for i, row in enumerate(source_rows) if row.get("axis") == "identity_humanization"]
    if len(identity_indexes) != 64:
        raise ValueError("identity_axis_count_mismatch")
    replace_indexes = identity_indexes[-3:]
    asks = {
        "we-project-001": "State how Viv and the operator are working together on this training project.",
        "we-system-001": "State which AIOS components are responsible for memory and logging.",
        "we-project-002": "State whether Viv and the operator should test this hypothesis together before training.",
    }
    replacement_map = []
    train = [dict(row) for row in source_rows]
    for index, entity in zip(replace_indexes, positives):
        ask = asks[entity["candidate_id"]]
        item = dict(train[index])
        item.update(
            {
                "pair_id": f"entity-we-full-{entity['candidate_id']}",
                "candidate_id": f"entity-we-full-{entity['candidate_id']}",
                "axis": "identity_humanization",
                "ask": ask,
                "target": entity["target"],
                "chosen": entity["target"],
                "split": "train",
                "optimizer_eligible": True,
                "full_campaign_eligible": True,
                "hold_only": False,
                "response_only_loss_allowed": True,
                "training_authorized": False,
                "run_authorized": False,
                "entity_we_contract": entity["expected_category"],
                "source_entity_candidate_id": entity["candidate_id"],
                "source_entity_manifest_sha256": sha(ENTITY / "MANIFEST.json"),
            }
        )
        item["ask_hash"] = hashlib.sha256(ask.lower().encode("utf-8")).hexdigest()
        item["target_hash"] = hashlib.sha256(entity["target"].lower().encode("utf-8")).hexdigest()
        train[index] = item
        replacement_map.append(
            {
                "source_index": index,
                "source_pair_id": source_rows[index].get("pair_id"),
                "replacement_pair_id": item["pair_id"],
                "entity_category": entity["expected_category"],
            }
        )
    if len(train) != 256 or len({row["pair_id"] for row in train}) != 256:
        raise ValueError("derived_train_identity_failure")
    if sum(row.get("optimizer_eligible") is True for row in train) != 256:
        raise ValueError("derived_optimizer_eligibility_failure")
    if sum(row.get("axis") == "identity_humanization" for row in train) != 64:
        raise ValueError("derived_axis_balance_failure")

    ROOT.mkdir(parents=True)
    TRAIN.write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in train),
        encoding="utf-8",
        newline="\n",
    )
    # Evaluation files are copied as new bytes, never edited in place.
    for name in ("development_64.jsonl", "blind_32.jsonl"):
        (ROOT / name).write_bytes((SOURCE / name).read_bytes())
    (ROOT / "ENTITY_WE_JUDGE_ONLY.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in negatives),
        encoding="utf-8",
        newline="\n",
    )
    replacement_path = ROOT / "REPLACEMENT_MAP.json"
    replacement_path.write_text(json.dumps(replacement_map, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": "mouth_full_run_entity_we_manifest_v1",
        "experiment_id": "mouth_full_run_entity_we_v1",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "CORPUS_READY_TRAINING_CLOSED",
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
        "optimizer_rows": 256,
        "axis_counts": {axis: sum(row.get("axis") == axis for row in train) for axis in sorted({row.get("axis") for row in train})},
        "source_campaign": {"path": str(SOURCE).replace("\\", "/"), "manifest_sha256": sha(SOURCE / "manifest.json"), "train_sha256": sha(source_train)},
        "entity_contract_source": {"path": str(ENTITY).replace("\\", "/"), "manifest_sha256": sha(ENTITY / "MANIFEST.json"), "jsonl_sha256": sha(ENTITY / "entity_we_contract_examples.jsonl"), "positive_train_rows": 3, "judge_only_negative_rows": 3},
        "files": {
            "train_256.jsonl": {"sha256": sha(TRAIN), "count": 256},
            "development_64.jsonl": {"sha256": sha(ROOT / "development_64.jsonl"), "count": len(rows(ROOT / "development_64.jsonl"))},
            "blind_32.jsonl": {"sha256": sha(ROOT / "blind_32.jsonl"), "count": len(rows(ROOT / "blind_32.jsonl"))},
            "ENTITY_WE_JUDGE_ONLY.jsonl": {"sha256": sha(ROOT / "ENTITY_WE_JUDGE_ONLY.jsonl"), "count": 3},
            "REPLACEMENT_MAP.json": {"sha256": sha(replacement_path), "count": 3},
        },
        "no_automatic_retry": True,
        "no_live_mutation": True,
    }
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (ROOT / "CORPUS_REPORT.md").write_text(
        "# Viv Full Run Entity-We Corpus v1\n\n"
        "Derived from the frozen 256-row anchor corpus. Three identity rows were replaced by positive project/system-we examples. Human-we and ambiguous-we examples remain judge-only. Prior campaign bytes are preserved. Training, run, promotion, and deployment remain closed.\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"output": str(ROOT), "manifest_sha256": sha(manifest_path), "train": 256, "training_authorized": False, "run_authorized": False}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
