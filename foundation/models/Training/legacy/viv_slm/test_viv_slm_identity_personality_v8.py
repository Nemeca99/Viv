#!/usr/bin/env python3
"""Verify the v8 paraphrase corpus and tensor inputs."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v8"
INPUTS = FOUNDATION.parent / "models" / "viv_slm_identity_personality_v8" / "inputs"
PARAPHRASE_SOURCE = "viv_identity_personality_paraphrase_pack_v8"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    manifest = json.loads((DATASET / "MANIFEST.json").read_text(encoding="utf-8"))
    vocab = json.loads((DATASET / "VOCAB.json").read_text(encoding="utf-8"))
    rows = [row for split in ("train", "validation", "frozen", "adversarial") for row in _rows(DATASET / f"{split}.jsonl")]
    paraphrases = [row for row in rows if row["source"] == PARAPHRASE_SOURCE]
    input_manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE_DATASET_TRAINING_CLOSED"
    assert manifest["purpose"] == "identity_personality_paraphrase_generalization_before_world_knowledge"
    assert manifest["row_counts"] == {"train": 310, "validation": 48, "frozen": 21, "adversarial": 21}
    assert manifest["row_total"] == 400
    assert manifest["paraphrase_rows"] == 40
    assert manifest["paraphrase_split_counts"] == {"train": 30, "validation": 6, "frozen": 2, "adversarial": 2}
    assert len(paraphrases) == 40
    assert manifest["vocab_size"] == 96
    assert all(row["text"].endswith("<END>\n") for row in rows)
    assert all("CPU tags assigned" not in row["text"] for row in rows)
    assert all(row["training_authorized"] is False for row in rows)
    assert all(row["telemetry_allowed"] is False for row in rows)
    assert all(character in vocab["vocab"] for character in "<END>")
    assert input_manifest["dataset_manifest_sha256"] == _sha256(DATASET / "MANIFEST.json")
    assert input_manifest["vocab_size"] == 96
    assert input_manifest["train_examples"] == 36624
    assert input_manifest["validation_examples"] == 5981
    assert input_manifest["world_knowledge_included"] is False
    assert input_manifest["training_authorized"] is False
    print(
        "VIV_SLM_IDENTITY_PERSONALITY_V8_PASS "
        f"rows={manifest['row_total']} train={manifest['row_counts']['train']} "
        f"validation={manifest['row_counts']['validation']} paraphrase_rows={manifest['paraphrase_rows']} "
        f"train_examples={input_manifest['train_examples']} validation_examples={input_manifest['validation_examples']} "
        "vocab_size=96 termination=<END> world_knowledge=false training_authorized=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
