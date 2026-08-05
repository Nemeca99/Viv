#!/usr/bin/env python3
"""Verify clean prompts and explicit response termination for Viv-SLM v2."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v2"


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
    assert manifest["purpose"] == "identity_personality_clean_conversation_before_world_knowledge"
    assert manifest["termination_marker"] == "<END>"
    assert manifest["world_knowledge_included"] is False
    assert manifest["training_authorized"] is False
    assert vocab["vocab_size"] == 96
    assert all(character in vocab["vocab"] for character in "<END>")

    split_rows = {split: _rows(DATASET / f"{split}.jsonl") for split in ("train", "validation", "frozen", "adversarial")}
    assert {split: len(rows) for split, rows in split_rows.items()} == manifest["row_counts"]
    assert manifest["row_counts"] == {
        "train": 92,
        "validation": 24,
        "frozen": 10,
        "adversarial": 10,
    }
    assert manifest["row_total"] == 136
    assert all("CPU tags assigned" not in row["text"] for rows in split_rows.values() for row in rows)
    assert all(row["text"].endswith("<END>\n") for rows in split_rows.values() for row in rows)
    assert all(row["optimizer_eligible"] is True for row in split_rows["train"])
    assert all(row["hold_only"] is True for split in ("validation", "frozen", "adversarial") for row in split_rows[split])
    assert any(row["source"] == "viv_personality_dna_clean_rows_v2" for row in split_rows["train"])
    print(
        "VIV_SLM_IDENTITY_PERSONALITY_V2_PASS "
        f"rows={manifest['row_total']} "
        f"train={manifest['row_counts']['train']} "
        f"validation={manifest['row_counts']['validation']} "
        f"frozen={manifest['row_counts']['frozen']} "
        f"adversarial={manifest['row_counts']['adversarial']} "
        f"vocab_size={manifest['vocab_size']} termination=<END> "
        "world_knowledge=false training_authorized=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
