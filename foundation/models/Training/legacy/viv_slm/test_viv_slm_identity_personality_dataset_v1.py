#!/usr/bin/env python3
"""Verify the immutable identity/personality-only Viv-SLM dataset package."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v1"


def _rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    vocab = json.loads((DATASET / "VOCAB.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_DATASET_TRAINING_CLOSED"
    assert manifest["model"] == "Viv-SLM"
    assert manifest["purpose"] == "identity_personality_before_world_knowledge"
    assert manifest["knowledge_policy"] == "external_cpu_retrieval_only"
    assert manifest["world_knowledge_included"] is False
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    assert manifest["deployment_changed"] is False
    assert vocab["vocab_size"] == manifest["vocab_size"]
    assert all(ord(character) < 128 for character in vocab["vocab"])
    assert all(character in vocab["vocab"] for character in "Viv: 0123456789{}[]\"")

    split_rows = {split: _rows(DATASET / f"{split}.jsonl") for split in ("train", "validation", "frozen", "adversarial")}
    assert {split: len(rows) for split, rows in split_rows.items()} == manifest["row_counts"]
    assert all(row["training_authorized"] is False for rows in split_rows.values() for row in rows)
    assert all(row["telemetry_allowed"] is False for rows in split_rows.values() for row in rows)
    assert all(row["optimizer_eligible"] is True for row in split_rows["train"])
    assert all(row["hold_only"] is True for split in ("validation", "frozen", "adversarial") for row in split_rows[split])
    assert any(row["source"] == "viv_personality_dna_v1_authored_rows" for row in split_rows["train"])
    assert any("mirror" in row["response"].lower() for row in split_rows["train"])
    source_paths = [
        str(record.get("path") or "").lower()
        for record in manifest["source_records"]
    ]
    assert all("wikipedia" not in path for path in source_paths)
    assert all("ai_datasets" not in path for path in source_paths)
    assert all("knowledge_corpus" not in path for path in source_paths)
    print(
        "VIV_SLM_IDENTITY_PERSONALITY_DATASET_PASS "
        f"rows={manifest['row_total']} "
        f"train={manifest['row_counts']['train']} "
        f"validation={manifest['row_counts']['validation']} "
        f"frozen={manifest['row_counts']['frozen']} "
        f"adversarial={manifest['row_counts']['adversarial']} "
        f"vocab_size={manifest['vocab_size']} "
        "world_knowledge=false training_authorized=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
