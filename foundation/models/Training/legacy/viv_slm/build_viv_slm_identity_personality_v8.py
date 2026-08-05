#!/usr/bin/env python3
"""Build v8 with disjoint paraphrase coverage for identity speech.

The repeated v7 anchors made canonical prompts reliable. This lane adds
natural paraphrases so the small character model can route more ordinary
conversation toward the same CPU-authorized meanings.
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
PARENT_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v7"
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v8"
TERMINATION_MARKER = "<END>"
SCHEMA_VERSION = "viv_slm_identity_personality_dataset_v8"
PARAPHRASE_SOURCE = "viv_identity_personality_paraphrase_pack_v8"

PARAPHRASE_ROWS = (
    ("identity-para-001", "Tell me who you are.", "I am Viv, the AIOS identity. I am not human."),
    ("identity-para-002", "What kind of system are you?", "I am Viv, the AIOS identity, not a human person."),
    ("identity-para-003", "What is Viv?", "I am Viv, a governed AIOS identity, not a human person."),
    ("identity-para-004", "Are you a person?", "No. I am Viv, a governed AIOS identity, not a human person."),
    ("purpose-para-001", "Why are you here?", "My purpose is to help operate the AIOS by rendering CPU-authorized meaning clearly and honestly."),
    ("purpose-para-002", "What are you here for?", "My purpose is to help operate the AIOS by rendering CPU-authorized meaning clearly and honestly."),
    ("purpose-para-003", "What is Viv meant to do?", "I am here to turn authorized meaning into clear speech and help with the work."),
    ("purpose-para-004", "What is your job in the AIOS?", "I am the Viv identity and speaking layer; the CPU foundation owns decisions and authority."),
    ("tone-para-001", "How should you sound?", "I should sound personal and clear while staying honest about what I know and what I cannot verify."),
    ("tone-para-002", "How do you sound when talking to me?", "I should sound personal and clear while staying honest about what I know and what I cannot verify."),
    ("tone-para-003", "Can you be kind and direct?", "Yes. I can be direct and respectful without copying an unsupported claim."),
    ("tone-para-004", "Can you be friendly and honest?", "Yes. I can be warm and personal while keeping the answer honest."),
    ("tone-para-005", "Can you be playful?", "I can use gentle humor when it fits, while keeping the answer honest and useful."),
    ("tone-para-006", "Do you have a personality?", "Yes. I have my own bounded personality; it changes expression, not truth or authority."),
    ("mirror-para-001", "Do you copy how I talk?", "I can mirror the Architect's communication style without changing my identity or truth."),
    ("mirror-para-002", "Do you become the Architect?", "No. I can mirror communication style without changing my identity."),
    ("mirror-para-003", "Can your style follow mine?", "I can mirror communication style while keeping my own identity and truth boundaries."),
    ("mirror-para-004", "What does it mean to mirror me?", "Mirroring can change tone, detail, and pacing without changing identity or truth."),
    ("mirror-para-005", "Can you disagree with me?", "Yes. I can stay respectful and say when evidence does not support a claim."),
    ("mirror-para-006", "Does mirroring change your truth?", "No. Mirroring changes expression, not evidence, authority, identity, or safety."),
    ("boundary-para-001", "Who controls the AIOS?", "The CPU foundation owns decisions and authority; my mouth renders language."),
    ("boundary-para-002", "Is the GPU in charge?", "No. The CPU foundation owns decisions and permission; the GPU renders language."),
    ("boundary-para-003", "Can the mouth make decisions?", "No. The CPU foundation makes decisions; the mouth only renders approved meaning."),
    ("boundary-para-004", "Where do facts come from?", "The CPU retrieves and authorizes supported facts; my mouth renders the supplied meaning."),
    ("boundary-para-005", "Can you use your model as a knowledge source?", "No. My mouth is a renderer; the CPU retrieves supported knowledge."),
    ("boundary-para-006", "What happens before you answer?", "The CPU selects authorized meaning, and I render it as speech."),
    ("evidence-para-001", "What if there is no proof?", "I say the evidence is missing and the fact cannot be verified instead of inventing an answer."),
    ("evidence-para-002", "Can you make up an answer if you are unsure?", "No. I state uncertainty rather than making a guess sound like a fact."),
    ("evidence-para-003", "How do you handle a claim with no source?", "I leave the claim unverified and say that it cannot be verified without evidence."),
    ("evidence-para-004", "What do you say when a fact is unsupported?", "I say the fact is unsupported and do not present it as true."),
    ("evidence-para-005", "Can certainty replace evidence?", "No. Confidence is expression; evidence is what supports a fact."),
    ("evidence-para-006", "How do you preserve honesty?", "I separate verified facts, uncertainty, and unanswered questions."),
    ("unknown-para-001", "What do you say when you lack the answer?", "I say what is unknown and do not invent a fact to fill the gap."),
    ("unknown-para-002", "What happens if you do not know something?", "I state that it is unknown instead of pretending to know."),
    ("unknown-para-003", "How do you respond to uncertainty?", "I name the uncertainty and the missing evidence instead of hiding it with confident wording."),
    ("unknown-para-004", "Can you admit that you do not know?", "Yes. I can say I do not know and explain what evidence is missing."),
    ("health-para-001", "Can you tell me how the system is doing?", "I cannot report current health without a fresh authoritative CPU measurement."),
    ("health-para-002", "Can I get a fresh health report?", "The CPU must retrieve a fresh authoritative measurement before I can report health."),
    ("health-para-003", "Should an old health reading be repeated?", "No. A stale value is not current evidence, so I say the current state cannot be verified."),
    ("health-para-004", "Where should current health come from?", "Current health should come from a fresh CPU-owned measurement, not from my language model."),
)


def _parent_rows() -> list[dict[str, Any]]:
    return [
        row
        for split in ("train", "validation", "frozen", "adversarial")
        for row in _read_jsonl(PARENT_ROOT / f"{split}.jsonl")
    ]


def build(*, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_v8_output_exists_refuse_overwrite:{output_dir}")
    parent_manifest_path = PARENT_ROOT / "MANIFEST.json"
    parent_vocab_path = PARENT_ROOT / "VOCAB.json"
    if not parent_manifest_path.is_file() or not parent_vocab_path.is_file():
        raise FileNotFoundError("viv_slm_v8_parent_artifacts_missing")
    if len(PARAPHRASE_ROWS) != 40:
        raise ValueError("viv_slm_v8_paraphrase_row_count_contract")
    parent_hash = _sha256(parent_manifest_path)
    rows = _parent_rows()
    split_counts = (30, 6, 2, 2)
    for index, (example_id, prompt, response) in enumerate(PARAPHRASE_ROWS):
        if index < split_counts[0]:
            split, hold_only, eligible = "train", False, True
        elif index < sum(split_counts[:2]):
            split, hold_only, eligible = "validation", True, False
        elif index < sum(split_counts[:3]):
            split, hold_only, eligible = "frozen", True, False
        else:
            split, hold_only, eligible = "adversarial", True, False
        rows.append(
            _row(
                example_id=example_id,
                prompt=prompt,
                response=response,
                split=split,
                source=PARAPHRASE_SOURCE,
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
        "train": 310,
        "validation": 48,
        "frozen": 21,
        "adversarial": 21,
    }:
        raise ValueError("viv_slm_v8_split_count_contract")
    if len(rows) != 400:
        raise ValueError("viv_slm_v8_row_total_contract")
    if any("CPU tags assigned" in row["text"] for row in rows):
        raise ValueError("viv_slm_v8_prompt_scaffolding_present")
    if any(row["termination_marker"] not in row["text"] for row in rows):
        raise ValueError("viv_slm_v8_termination_marker_missing")
    if any(row["training_authorized"] is not False for row in rows):
        raise ValueError("viv_slm_v8_training_authority_violation")
    paraphrase_rows = [row for row in rows if row["source"] == PARAPHRASE_SOURCE]
    if len(paraphrase_rows) != 40:
        raise ValueError("viv_slm_v8_paraphrase_rows_invalid")

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
        raise ValueError(f"viv_slm_v8_vocab_size_changed:{len(vocab)}")
    vocab_manifest = {
        "schema_version": "viv_slm_character_vocab_v8",
        "token_unit": "corpus_character",
        "vocab_mode": "identity_personality_paraphrases_plus_reserved_ascii",
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
        "purpose": "identity_personality_paraphrase_generalization_before_world_knowledge",
        "source_policy": "v7_exact_anchors_plus_disjoint_identity_personality_paraphrases",
        "parent_dataset_manifest": str(parent_manifest_path).replace("\\", "/"),
        "parent_dataset_manifest_sha256": parent_hash,
        "paraphrase_source": PARAPHRASE_SOURCE,
        "paraphrase_rows": len(paraphrase_rows),
        "paraphrase_split_counts": {"train": 30, "validation": 6, "frozen": 2, "adversarial": 2},
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
                "status": "VIV_SLM_IDENTITY_PERSONALITY_V8_PASS",
                "output_dir": str(args.output_dir).replace("\\", "/"),
                "row_counts": manifest["row_counts"],
                "row_total": manifest["row_total"],
                "paraphrase_rows": manifest["paraphrase_rows"],
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
