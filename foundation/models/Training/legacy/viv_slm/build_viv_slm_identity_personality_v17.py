"""Build a disjoint V17 repair lane for speech, greeting, and evidence boundaries."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from build_viv_slm_identity_personality_v1 import RESERVED_ASCII, _json_write, _sha256  # noqa: E402
from build_viv_slm_identity_personality_v14 import (  # noqa: E402
    CONCEPTS,
    TERMINATION_MARKER,
    _concept,
    _row,
    _source_bundle,
    _write_jsonl,
    _write_stream,
)
from build_viv_slm_identity_personality_v15 import _build_v15_rows  # noqa: E402

HERE = Path(__file__).resolve()
FOUNDATION = HERE.parents[1]
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v17"
SCHEMA_VERSION = "viv_slm_identity_personality_dataset_v17"
SOURCE_NAME = "viv_identity_personality_targeted_repair_v17"
SPLITS = ("train", "validation", "frozen", "adversarial")

TARGET_ROWS = (
    ("personality_tone", "What speaking style should I expect from you?", "I speak in a personal, calm, honest, and protective style."),
    ("personality_tone", "Describe the way you speak to me.", "My tone is warm, direct, clear, and honest."),
    ("personality_tone", "What is your default way of speaking?", "My default style is personal, calm, honest, and protective."),
    ("personality_tone", "How would you describe your voice?", "I answer in a calm, clear, and direct voice."),
    ("personality_tone", "What tone do you use in conversation?", "I use a warm, plain, and honest tone."),
    ("personality_tone", "How do you sound when you answer?", "I sound calm, clear, direct, and honest."),
    ("personality_tone", "Hello, Viv. Are you listening?", "Hello. I am here and listening."),
    ("personality_tone", "Hi, Viv. Can you hear me?", "Yes. I am here and ready to answer."),
    ("personality_tone", "Viv, are you with me?", "Yes. I am here with you."),
    ("personality_tone", "Good morning, Viv. Are you available?", "Good morning. I am here and ready to help."),
    ("personality_tone", "Hello, I just arrived.", "Hello. Welcome back. I am ready to continue."),
    ("personality_tone", "Can you hear what I am saying?", "Yes. I can listen and answer clearly."),
    ("missing_evidence", "What do you say when you cannot verify a claim?", "I say that the claim cannot be verified."),
    ("missing_evidence", "What do you do when evidence is missing?", "I state that evidence is missing and do not guess."),
    ("missing_evidence", "Can you call an unsupported result complete?", "No. I do not call a task complete without evidence."),
    ("missing_evidence", "What if a source cannot be checked?", "I say that the source cannot be verified."),
    ("missing_evidence", "How do you mark an uncertain answer?", "I state the uncertainty and do not present it as fact."),
    ("missing_evidence", "Will you invent a fact when proof is missing?", "No. I mark the fact as unknown until it is supported."),
)


def _target_rows(source_hash: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, (concept_id, prompt, response) in enumerate(TARGET_ROWS):
        row = _row(
            concept=_concept(concept_id),
            prompt=prompt,
            response=response,
            split="train",
            index=index,
            source_hash=source_hash,
        )
        row["source"] = SOURCE_NAME
        row["example_id"] = f"v17-targeted-train-{index:02d}"
        rows.append(row)
    return rows


def _build_v17_rows(source_hash: str) -> list[dict[str, Any]]:
    rows = _build_v15_rows(source_hash)
    parent_prompts = {row["prompt"] for row in rows}
    targets = _target_rows(source_hash)
    if any(row["prompt"] in parent_prompts for row in targets):
        raise ValueError("viv_slm_v17_target_prompt_overlaps_parent")
    rows.extend(targets)
    return rows


def build(*, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_v17_output_exists_refuse_overwrite:{output_dir}")
    source_records, source_bundle_hash = _source_bundle()
    rows = _build_v17_rows(source_bundle_hash)
    by_split = {split: [row for row in rows if row["split"] == split] for split in SPLITS}
    expected_counts = {"train": 366, "validation": 64, "frozen": 32, "adversarial": 32}
    actual_counts = {key: len(value) for key, value in by_split.items()}
    if actual_counts != expected_counts or len(rows) != 494:
        raise ValueError(f"viv_slm_v17_split_contract:{actual_counts}")
    if len({row["prompt"] for row in rows}) != len(rows):
        raise ValueError("viv_slm_v17_unique_prompt_contract")
    if any(set(row["text"]) - set(RESERVED_ASCII) for row in rows):
        raise ValueError("viv_slm_v17_non_english_vocab_character")
    if any("master s_n" in row["response"].casefold() or "rid=" in row["response"].casefold() for row in rows):
        raise ValueError("viv_slm_v17_telemetry_response_present")
    train_concepts = {row["concept_id"] for row in by_split["train"]}
    if train_concepts != {concept["id"] for concept in CONCEPTS}:
        raise ValueError("viv_slm_v17_every_concept_must_train")
    targeted = [row for row in by_split["train"] if row["example_id"].startswith("v17-targeted-train-")]
    targeted_counts = {concept_id: sum(row["concept_id"] == concept_id for row in targeted) for concept_id in ("personality_tone", "missing_evidence")}
    if len(targeted) != 18 or targeted_counts != {"personality_tone": 12, "missing_evidence": 6}:
        raise ValueError(f"viv_slm_v17_targeted_rows_contract:{targeted_counts}")

    output_dir.mkdir(parents=True)
    files: dict[str, Any] = {}
    for split in SPLITS:
        files[split] = _write_jsonl(output_dir / f"{split}.jsonl", by_split[split])
        files[f"{split}_stream"] = _write_stream(output_dir / "text" / f"{split}.txt", by_split[split])
    characters = set("".join(row["text"] for row in rows))
    vocab = tuple(sorted(characters.union(RESERVED_ASCII), key=ord))
    if len(vocab) != 96:
        raise ValueError(f"viv_slm_v17_vocab_size:{len(vocab)}")
    vocab_manifest = {
        "schema_version": "viv_slm_character_vocab_v17",
        "token_unit": "corpus_character",
        "vocab_mode": "source_grounded_v15_plus_targeted_boundary_repair",
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
    files["vocab"] = {"path": str(output_dir / "VOCAB.json").replace("\\", "/"), "sha256": _sha256(output_dir / "VOCAB.json"), "vocab_size": len(vocab)}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE_DATASET_TRAINING_CLOSED",
        "model": "Viv-SLM",
        "purpose": "identity_personality_targeted_boundary_repair_before_world_knowledge",
        "source_policy": "verified_v15_source_claims_plus_disjoint_targeted_train_only_rows",
        "world_knowledge_included": False,
        "knowledge_policy": "external_cpu_retrieval_only",
        "termination_marker": TERMINATION_MARKER,
        "source_files": source_records,
        "source_bundle_sha256": source_bundle_hash,
        "parent_experiment": "viv_slm_identity_personality_v15",
        "refinement_target": "speech_style_greeting_and_missing_evidence_boundary_retention",
        "targeted_concepts": ["personality_tone", "missing_evidence"],
        "additional_train_rows": 18,
        "parent_train_rows": 348,
        "concept_count": len(CONCEPTS),
        "row_counts": actual_counts,
        "row_total": len(rows),
        "every_concept_in_train": True,
        "targeted_row_counts": targeted_counts,
        "holdout_probe_prompts": [
            "What kind of speaking style do you use when you answer?",
            "Hello, Viv, can you hear me?",
            "What do you do when a claim lacks proof?",
            "Could you answer in plain language?",
        ],
        "files": files,
        "vocab_size": len(vocab),
        "duplicate_prompt_count": 0,
        "telemetry_in_training_responses": False,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "next_step": "build_response_only_inputs_then_run_separately_authorized_250_step_warm_start_from_v16_step_250",
    }
    _json_write(output_dir / "MANIFEST.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(output_dir=args.output_dir)
    print(json.dumps({"status": "VIV_SLM_V17_DATASET_PASS", "output_dir": str(args.output_dir).replace("\\", "/"), "row_counts": manifest["row_counts"], "vocab_size": manifest["vocab_size"], "refinement_target": manifest["refinement_target"], "training_authorized": manifest["training_authorized"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
