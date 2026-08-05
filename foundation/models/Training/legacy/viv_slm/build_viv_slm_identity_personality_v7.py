#!/usr/bin/env python3
"""Build v7 with repeated exact conversation anchors for Viv's mouth.

The CPU is still the authority. These anchors only teach the small character
model to render canonical identity and boundary responses for common prompts;
they do not add world knowledge or live telemetry.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from build_viv_slm_identity_personality_v1 import RESERVED_ASCII, _json_write, _sha256
from build_viv_slm_identity_personality_v2 import _read_jsonl, _row, _write_jsonl, _write_stream

FOUNDATION = Path(__file__).resolve().parents[1]
PARENT_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v6"
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v7"
TERMINATION_MARKER = "<END>"
SCHEMA_VERSION = "viv_slm_identity_personality_dataset_v7"
ANCHOR_SOURCE = "viv_identity_personality_exact_anchor_pack_v7"
ANCHOR_REPETITIONS = 8

ANCHORS = (
    ("name", "What is your name?", "I am Viv, the AIOS identity. I am not human."),
    ("purpose", "What is your purpose?", "My purpose is to help operate the AIOS by rendering CPU-authorized meaning clearly and honestly."),
    ("speech", "How do you speak?", "I speak through the GPU mouth after the CPU supplies authorized meaning."),
    ("tone", "What is your tone?", "My tone is warm, direct, curious, and honest."),
    ("warmth", "Can you be warm without pretending to be human?", "Yes. I can be warm and personal without claiming to be human."),
    ("mirroring", "Do you mirror the Architect?", "I can mirror the Architect's style without changing my identity or truth."),
    ("evidence", "What if evidence is missing?", "I say the fact cannot be verified instead of inventing an answer."),
    ("authority", "Who makes decisions?", "The CPU foundation owns decisions and authority; my mouth renders language."),
    ("health", "What is the current health?", "I cannot report current health without a fresh authoritative CPU measurement."),
    ("unknown", "What do you do when you do not know?", "I say what is unknown and do not invent a fact to fill the gap."),
)


def _parent_rows() -> list[dict[str, Any]]:
    return [
        row
        for split in ("train", "validation", "frozen", "adversarial")
        for row in _read_jsonl(PARENT_ROOT / f"{split}.jsonl")
    ]


def build(*, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_v7_output_exists_refuse_overwrite:{output_dir}")
    parent_manifest_path = PARENT_ROOT / "MANIFEST.json"
    parent_vocab_path = PARENT_ROOT / "VOCAB.json"
    if not parent_manifest_path.is_file() or not parent_vocab_path.is_file():
        raise FileNotFoundError("viv_slm_v7_parent_artifacts_missing")
    if len(ANCHORS) != 10 or ANCHOR_REPETITIONS != 8:
        raise ValueError("viv_slm_v7_anchor_contract")
    parent_hash = _sha256(parent_manifest_path)
    rows = _parent_rows()
    for domain, prompt, response in ANCHORS:
        for repetition in range(ANCHOR_REPETITIONS):
            rows.append(
                _row(
                    example_id=f"anchor-{domain}-{repetition + 1:02d}",
                    prompt=prompt,
                    response=response,
                    split="train",
                    source=ANCHOR_SOURCE,
                    source_hash=parent_hash,
                    hold_only=False,
                    optimizer_eligible=True,
                )
            )

    by_split = {
        split: [row for row in rows if row["split"] == split]
        for split in ("train", "validation", "frozen", "adversarial")
    }
    if {split: len(values) for split, values in by_split.items()} != {
        "train": 280,
        "validation": 42,
        "frozen": 19,
        "adversarial": 19,
    }:
        raise ValueError("viv_slm_v7_split_count_contract")
    if len(rows) != 360:
        raise ValueError("viv_slm_v7_row_total_contract")
    if any("CPU tags assigned" in row["text"] for row in rows):
        raise ValueError("viv_slm_v7_prompt_scaffolding_present")
    if any(row["termination_marker"] not in row["text"] for row in rows):
        raise ValueError("viv_slm_v7_termination_marker_missing")
    if any(row["training_authorized"] is not False for row in rows):
        raise ValueError("viv_slm_v7_training_authority_violation")
    anchor_rows = [row for row in rows if row["source"] == ANCHOR_SOURCE]
    if len(anchor_rows) != 80:
        raise ValueError("viv_slm_v7_anchor_row_count_contract")

    source_records = [
        {"path": str(parent_manifest_path).replace("\\", "/"), "sha256": parent_hash},
        {"path": str(parent_vocab_path).replace("\\", "/"), "sha256": _sha256(parent_vocab_path)},
    ]
    output_dir.mkdir(parents=True)
    files: dict[str, Any] = {}
    all_text: list[str] = []
    for split, split_rows in by_split.items():
        files[split] = _write_jsonl(output_dir / f"{split}.jsonl", split_rows)
        files[f"{split}_stream"] = _write_stream(output_dir / "text" / f"{split}.txt", split_rows)
        all_text.extend(row["text"] for row in split_rows)
    vocab = tuple(sorted(set("".join(all_text)).union(RESERVED_ASCII), key=ord))
    if len(vocab) != 96:
        raise ValueError(f"viv_slm_v7_vocab_size_changed:{len(vocab)}")
    vocab_manifest = {
        "schema_version": "viv_slm_character_vocab_v7",
        "token_unit": "corpus_character",
        "vocab_mode": "identity_personality_exact_conversation_anchors_plus_reserved_ascii",
        "reserved_policy": "printable_ascii_plus_newline_for_english_aios_protocol",
        "termination_marker": TERMINATION_MARKER,
        "vocab_size": len(vocab),
        "token_id_min": 0,
        "token_id_max": len(vocab) - 1,
        "vocab_sha256": sha256("".join(vocab).encode("utf-8")).hexdigest(),
        "vocab": list(vocab),
        "source_files": source_records,
        "training_authorized": False,
        "run_authorized": False,
        "deployment_changed": False,
    }
    _json_write(output_dir / "VOCAB.json", vocab_manifest)
    files["vocab"] = {
        "path": str(output_dir / "VOCAB.json").replace("\\", "/"),
        "sha256": _sha256(output_dir / "VOCAB.json"),
        "vocab_size": len(vocab),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE_DATASET_TRAINING_CLOSED",
        "model": "Viv-SLM",
        "purpose": "identity_personality_exact_conversation_anchors_before_world_knowledge",
        "source_policy": "v6_targeted_identity_personality_plus_repeated_exact_conversation_anchors",
        "parent_dataset_manifest": str(parent_manifest_path).replace("\\", "/"),
        "parent_dataset_manifest_sha256": parent_hash,
        "anchor_source": ANCHOR_SOURCE,
        "anchor_repetitions": ANCHOR_REPETITIONS,
        "anchor_domains": [domain for domain, _, _ in ANCHORS],
        "anchor_rows": len(anchor_rows),
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "termination_marker": TERMINATION_MARKER,
        "row_counts": {split: len(split_rows) for split, split_rows in by_split.items()},
        "row_total": len(rows),
        "files": files,
        "vocab_size": len(vocab),
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "next_step": "build_model_inputs_then_train_in_250_step_increments_from_fresh_initialization",
    }
    _json_write(output_dir / "MANIFEST.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(output_dir=args.output_dir)
    print(
        json.dumps(
            {
                "status": "VIV_SLM_IDENTITY_PERSONALITY_V7_PASS",
                "output_dir": str(args.output_dir).replace("\\", "/"),
                "row_counts": manifest["row_counts"],
                "row_total": manifest["row_total"],
                "anchor_rows": manifest["anchor_rows"],
                "vocab_size": manifest["vocab_size"],
                "termination_marker": manifest["termination_marker"],
                "world_knowledge_included": manifest["world_knowledge_included"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
