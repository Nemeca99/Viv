#!/usr/bin/env python3
"""Verify the exact-anchor identity/personality corpus."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v4"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    vocab = json.loads((DATASET / "VOCAB.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_DATASET_TRAINING_CLOSED"
    assert manifest["purpose"] == "identity_personality_exact_probe_anchors_before_world_knowledge"
    assert manifest["row_counts"] == {"train": 160, "validation": 32, "frozen": 14, "adversarial": 14}
    assert manifest["row_total"] == 220
    assert manifest["anchor_repetitions"] == 8
    assert manifest["vocab_size"] == 96
    assert all(character in vocab["vocab"] for character in "<END>")
    rows = [row for split in ("train", "validation", "frozen", "adversarial") for row in _rows(DATASET / f"{split}.jsonl")]
    assert all("CPU tags assigned" not in row["text"] for row in rows)
    assert all(row["text"].endswith("<END>\n") for row in rows)
    assert sum(1 for row in rows if row["source"] == "viv_identity_personality_probe_anchor_pack_v4") == 48
    assert all(row["training_authorized"] is False for row in rows)
    print(
        "VIV_SLM_IDENTITY_PERSONALITY_V4_PASS "
        f"rows={manifest['row_total']} train={manifest['row_counts']['train']} "
        f"validation={manifest['row_counts']['validation']} anchors=48 repetitions=8 "
        f"vocab_size={manifest['vocab_size']} termination=<END> world_knowledge=false "
        "training_authorized=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
