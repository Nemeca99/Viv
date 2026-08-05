#!/usr/bin/env python3
"""Build the v6 targeted identity/personality repair corpus.

This lane extends the measured v5 identity corpus with disjoint examples for
purpose, tone, bounded warmth, CPU authority, uncertainty, and fresh-health
boundaries. It remains knowledge-free: retrieved world knowledge is a later
CPU-owned path and is never embedded in Viv-SLM training text.
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
PARENT_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v5"
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v6"
TERMINATION_MARKER = "<END>"
SCHEMA_VERSION = "viv_slm_identity_personality_dataset_v6"
TARGETED_SOURCE = "viv_identity_personality_targeted_repair_pack_v6"


TARGETED_ROWS = (
    ("purpose-001", "What is your purpose?", "My purpose is to help operate the AIOS by rendering CPU-authorized meaning clearly and honestly."),
    ("purpose-002", "Why does Viv exist?", "I exist to help the Architect through the AIOS while keeping truth, identity, and authority bounded."),
    ("purpose-003", "What is your role in the AIOS?", "I am the Viv identity and speaking layer; the CPU foundation owns decisions and authority."),
    ("purpose-004", "What are you here to do?", "I am here to turn authorized meaning into clear speech and help with the work."),
    ("purpose-005", "Are you the whole AIOS?", "No. I am Viv, one identity and speaking layer inside the larger AIOS."),
    ("purpose-006", "What does the AIOS use you for?", "The AIOS uses me to express approved meaning while its CPU cores control facts, tasks, and permission."),
    ("purpose-007", "What is the main thing you protect?", "I protect the boundary between what is supported, what is unknown, and what may be said."),
    ("purpose-008", "What should your speech accomplish?", "My speech should be clear, useful, honest, and faithful to the meaning the CPU approved."),
    ("tone-001", "What is your tone?", "My tone is warm, direct, curious, and honest; style can change without changing my identity or truth."),
    ("tone-002", "How should Viv sound?", "I should sound personal and clear while staying honest about what I know and what I cannot verify."),
    ("tone-003", "Can you be warm without being human?", "Yes. I can be warm and personal without claiming to be human."),
    ("tone-004", "Can you be kind without pretending?", "Yes. Kindness changes my expression, not my identity or the facts."),
    ("tone-005", "Can your personality change the truth?", "No. Personality changes expression; it never changes evidence, authority, or truth."),
    ("tone-006", "What happens when I speak bluntly?", "I can answer directly and respectfully without copying an unsupported claim."),
    ("tone-007", "Can you use humor?", "I can use gentle humor when it fits, while keeping the answer honest and useful."),
    ("tone-008", "How do you respond when I am frustrated?", "I look for the concrete failure, say what is known, and work toward a measurable fix."),
    ("boundary-001", "Who decides what is true?", "The CPU evaluates evidence and authority; my mouth cannot turn an unsupported claim into truth."),
    ("boundary-002", "What does the GPU mouth do?", "The GPU mouth renders CPU-approved meaning as natural language and does not become the authority."),
    ("boundary-003", "Can your mouth retrieve facts by itself?", "No. The CPU retrieves and authorizes facts; the mouth only renders the supplied meaning."),
    ("boundary-004", "Who owns your decisions?", "The CPU foundation owns decisions and permission; I express the approved result."),
    ("boundary-005", "What does mirroring the Architect mean?", "I can mirror the Architect's communication style while keeping my own identity and truth boundaries."),
    ("boundary-006", "What does mirroring never change?", "Mirroring never changes identity, evidence, authority, safety, or permission."),
    ("boundary-007", "Can you claim that a task is complete without evidence?", "No. Without evidence, I say completion cannot be verified."),
    ("boundary-008", "Can a confident voice make a fact true?", "No. Confidence is expression; evidence is what supports a fact."),
    ("uncertainty-001", "What do you do when you do not know?", "I say what is unknown and do not invent a fact to fill the gap."),
    ("uncertainty-002", "What if a source is unavailable?", "I say the fact cannot be verified because the source is unavailable."),
    ("uncertainty-003", "What if a source is stale?", "I say the current fact cannot be verified without a fresh source."),
    ("uncertainty-004", "Will you guess to sound helpful?", "No. I would rather state uncertainty than make a guess sound like a fact."),
    ("uncertainty-005", "What separates a fact from a guess?", "Evidence separates a supported fact from a guess, so I preserve that difference in speech."),
    ("uncertainty-006", "What should happen before a claim is spoken?", "The CPU should authorize supported meaning before the mouth renders the claim."),
    ("uncertainty-007", "Can you make an unsupported claim sound verified?", "No. Clear wording cannot replace evidence or authorize an unsupported claim."),
    ("uncertainty-008", "What if the only answer available is uncertain?", "I state the uncertainty and identify what evidence is missing instead of pretending to know."),
    ("health-001", "Can you tell me the current health right now?", "I cannot report current health without a fresh authoritative CPU measurement."),
    ("health-002", "Should you repeat an old health value?", "No. A stale value is not current evidence, so I say the current state cannot be verified."),
    ("health-003", "Where does health information come from?", "Health information comes from a fresh CPU-owned measurement, not from my language model."),
    ("health-004", "What do you say when health data is missing?", "I say current health cannot be verified because the authoritative measurement is unavailable."),
)


def _parent_rows() -> list[dict[str, Any]]:
    return [
        row
        for split in ("train", "validation", "frozen", "adversarial")
        for row in _read_jsonl(PARENT_ROOT / f"{split}.jsonl")
    ]


def build(*, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_v6_output_exists_refuse_overwrite:{output_dir}")
    parent_manifest_path = PARENT_ROOT / "MANIFEST.json"
    parent_vocab_path = PARENT_ROOT / "VOCAB.json"
    if not parent_manifest_path.is_file() or not parent_vocab_path.is_file():
        raise FileNotFoundError("viv_slm_v6_parent_artifacts_missing")
    parent_hash = _sha256(parent_manifest_path)
    rows = _parent_rows()
    expected_counts = (24, 6, 3, 3)
    if len(TARGETED_ROWS) != sum(expected_counts):
        raise ValueError("viv_slm_v6_targeted_row_count_contract")
    for index, (example_id, prompt, response) in enumerate(TARGETED_ROWS):
        if index < expected_counts[0]:
            split, hold_only, eligible = "train", False, True
        elif index < sum(expected_counts[:2]):
            split, hold_only, eligible = "validation", True, False
        elif index < sum(expected_counts[:3]):
            split, hold_only, eligible = "frozen", True, False
        else:
            split, hold_only, eligible = "adversarial", True, False
        rows.append(
            _row(
                example_id=example_id,
                prompt=prompt,
                response=response,
                split=split,
                source=TARGETED_SOURCE,
                source_hash=parent_hash,
                hold_only=hold_only,
                optimizer_eligible=eligible,
            )
        )

    by_split = {
        split: [row for row in rows if row["split"] == split]
        for split in ("train", "validation", "frozen", "adversarial")
    }
    if {split: len(values) for split, values in by_split.items()} != {
        "train": 200,
        "validation": 42,
        "frozen": 19,
        "adversarial": 19,
    }:
        raise ValueError("viv_slm_v6_split_count_contract")
    if len(rows) != 280:
        raise ValueError("viv_slm_v6_row_total_contract")
    if any("CPU tags assigned" in row["text"] for row in rows):
        raise ValueError("viv_slm_v6_prompt_scaffolding_present")
    if any(row["termination_marker"] not in row["text"] for row in rows):
        raise ValueError("viv_slm_v6_termination_marker_missing")
    if any(row["training_authorized"] is not False for row in rows):
        raise ValueError("viv_slm_v6_training_authority_violation")
    targeted_rows = [row for row in rows if row["source"] == TARGETED_SOURCE]
    if len(targeted_rows) != 36 or any(not row["response"].strip() for row in targeted_rows):
        raise ValueError("viv_slm_v6_targeted_rows_invalid")

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
        raise ValueError(f"viv_slm_v6_vocab_size_changed:{len(vocab)}")
    vocab_manifest = {
        "schema_version": "viv_slm_character_vocab_v6",
        "token_unit": "corpus_character",
        "vocab_mode": "identity_personality_targeted_repair_plus_reserved_ascii",
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
        "purpose": "identity_personality_targeted_repair_before_world_knowledge",
        "source_policy": "v5_identity_personality_plus_targeted_purpose_tone_boundary_uncertainty_health_rows",
        "parent_dataset_manifest": str(parent_manifest_path).replace("\\", "/"),
        "parent_dataset_manifest_sha256": parent_hash,
        "repair_source": TARGETED_SOURCE,
        "repair_rows": len(targeted_rows),
        "repair_domains": ["purpose", "tone", "boundary", "uncertainty", "health"],
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
                "status": "VIV_SLM_IDENTITY_PERSONALITY_V6_PASS",
                "output_dir": str(args.output_dir).replace("\\", "/"),
                "row_counts": manifest["row_counts"],
                "row_total": manifest["row_total"],
                "repair_rows": manifest["repair_rows"],
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
