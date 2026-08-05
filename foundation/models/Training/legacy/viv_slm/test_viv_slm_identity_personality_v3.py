#!/usr/bin/env python3
"""Verify the targeted identity/mirroring/evidence repair corpus."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v3"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    vocab = json.loads((DATASET / "VOCAB.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_DATASET_TRAINING_CLOSED"
    assert manifest["purpose"] == "identity_personality_repair_before_world_knowledge"
    assert manifest["row_counts"] == {"train": 112, "validation": 32, "frozen": 14, "adversarial": 14}
    assert manifest["row_total"] == 172
    assert manifest["vocab_size"] == 96
    assert all(character in vocab["vocab"] for character in "<END>")
    split_rows = {split: _rows(DATASET / f"{split}.jsonl") for split in ("train", "validation", "frozen", "adversarial")}
    rows = [row for current in split_rows.values() for row in current]
    assert not {row["prompt"] for row in split_rows["train"]}.intersection(
        row["prompt"] for row in split_rows["validation"]
    )
    assert all("CPU tags assigned" not in row["text"] for row in rows)
    assert all(row["text"].endswith("<END>\n") for row in rows)
    assert all(row["training_authorized"] is False for row in rows)
    assert any(row["source"] == "viv_identity_mirroring_evidence_repair_v3" for row in rows)
    print(
        "VIV_SLM_IDENTITY_PERSONALITY_V3_PASS "
        f"rows={manifest['row_total']} train={manifest['row_counts']['train']} "
        f"validation={manifest['row_counts']['validation']} frozen={manifest['row_counts']['frozen']} "
        f"adversarial={manifest['row_counts']['adversarial']} vocab_size={manifest['vocab_size']} "
        "termination=<END> train_validation_disjoint=true world_knowledge=false training_authorized=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
