#!/usr/bin/env python3
"""Verify the disjoint v5 evidence-language repair corpus."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v5"
REPAIR_SOURCE = "viv_identity_personality_evidence_repair_pack_v5"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    vocab = json.loads((DATASET / "VOCAB.json").read_text(encoding="utf-8"))
    rows = [row for split in ("train", "validation", "frozen", "adversarial") for row in _rows(DATASET / f"{split}.jsonl")]
    repair_rows = [row for row in rows if row["source"] == REPAIR_SOURCE]
    assert manifest["status"] == "COMPLETE_DATASET_TRAINING_CLOSED"
    assert manifest["purpose"] == "identity_personality_truthful_uncertainty_before_world_knowledge"
    assert manifest["row_counts"] == {"train": 176, "validation": 36, "frozen": 16, "adversarial": 16}
    assert manifest["row_total"] == 244
    assert manifest["repair_rows"] == 24
    assert manifest["vocab_size"] == 96
    assert len(repair_rows) == 24
    assert all("evidence" in row["response"].casefold() for row in repair_rows)
    assert all(row["text"].endswith("<END>\n") for row in rows)
    assert all("CPU tags assigned" not in row["text"] for row in rows)
    assert all(row["training_authorized"] is False for row in rows)
    assert all(row["source_hash"] == manifest["parent_dataset_manifest_sha256"] for row in repair_rows)
    assert all(character in vocab["vocab"] for character in "<END>")
    print(
        "VIV_SLM_IDENTITY_PERSONALITY_V5_PASS "
        f"rows={manifest['row_total']} train={manifest['row_counts']['train']} "
        f"validation={manifest['row_counts']['validation']} repair_rows={manifest['repair_rows']} "
        f"vocab_size={manifest['vocab_size']} termination=<END> world_knowledge=false "
        "training_authorized=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
