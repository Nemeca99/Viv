"""Build a disjoint V14 prefix-focused speech-style refinement lane."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from build_viv_slm_identity_personality_v1 import RESERVED_ASCII, _json_write, _sha256  # noqa: E402
from build_viv_slm_identity_personality_v13 import (  # noqa: E402
    CONCEPTS,
    TERMINATION_MARKER,
    _build_rows,
    _row,
    _source_bundle,
    _write_jsonl,
    _write_stream,
)

HERE = Path(__file__).resolve()
FOUNDATION = HERE.parents[1]
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v14"
SCHEMA_VERSION = "viv_slm_identity_personality_dataset_v14"
SOURCE_NAME = "viv_identity_personality_speech_prefix_refinement_v14"
SPLITS = ("train", "validation", "frozen", "adversarial")

SPEECH_PREFIX_PROMPTS = (
    "How do you speak in ordinary conversation?",
    "How do you speak when the question is simple?",
    "How do you speak in your default style?",
    "How do you speak with warmth and honesty?",
    "How do you speak without inventing facts?",
    "How do you speak when the answer should be brief?",
    "How do you speak when technical detail is needed?",
    "How do you speak when the operator is frustrated?",
    "How do you speak without pretending to be human?",
    "How do you speak while staying evidence-bound?",
    "How do you speak when a fact is verified?",
    "How do you speak in ordinary mode?",
)

SPEECH_PREFIX_RESPONSES = (
    "I speak in a personal, calm, honest, and protective style.",
    "I answer directly and keep the wording clear.",
    "My tone is warm and direct without pretending to be human.",
    "I keep the answer concise when the request is simple.",
    "I adapt technical detail without changing the facts.",
    "I can be warm while remaining honest and evidence-bound.",
)


def _concept(concept_id: str) -> dict[str, Any]:
    return next(concept for concept in CONCEPTS if concept["id"] == concept_id)


def _target_rows(source_hash: str) -> list[dict[str, Any]]:
    speech = _concept("personality_tone")
    rows: list[dict[str, Any]] = []
    for index, prompt in enumerate(SPEECH_PREFIX_PROMPTS):
        row = _row(
            concept=speech,
            prompt=prompt,
            response=SPEECH_PREFIX_RESPONSES[index % len(SPEECH_PREFIX_RESPONSES)],
            split="train",
            index=index,
            source_hash=source_hash,
        )
        row["source"] = SOURCE_NAME
        row["example_id"] = f"v14-speech_prefix-train-{index:02d}"
        rows.append(row)
    return rows


def _build_v14_rows(source_hash: str) -> list[dict[str, Any]]:
    rows = _build_rows(source_hash)
    parent_prompts = {row["prompt"] for row in rows}
    targets = _target_rows(source_hash)
    if any(row["prompt"] in parent_prompts for row in targets):
        raise ValueError("viv_slm_v14_target_prompt_overlaps_parent")
    rows.extend(targets)
    for index, row in enumerate(rows):
        row["source"] = SOURCE_NAME
        if row["example_id"].startswith("v13-"):
            row["example_id"] = f"v14-parent-{index:03d}"
    return rows


def build(*, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_v14_output_exists_refuse_overwrite:{output_dir}")
    source_records, source_bundle_hash = _source_bundle()
    rows = _build_v14_rows(source_bundle_hash)
    by_split = {split: [row for row in rows if row["split"] == split] for split in SPLITS}
    expected_counts = {"train": 324, "validation": 64, "frozen": 32, "adversarial": 32}
    actual_counts = {key: len(value) for key, value in by_split.items()}
    if actual_counts != expected_counts or len(rows) != 452:
        raise ValueError(f"viv_slm_v14_split_contract:{actual_counts}")
    if len({row["prompt"] for row in rows}) != len(rows):
        raise ValueError("viv_slm_v14_unique_prompt_contract")
    if any(set(row["text"]) - set(RESERVED_ASCII) for row in rows):
        raise ValueError("viv_slm_v14_non_english_vocab_character")
    if any("master s_n" in row["response"].casefold() or "rid=" in row["response"].casefold() for row in rows):
        raise ValueError("viv_slm_v14_telemetry_response_present")
    train_concepts = {row["concept_id"] for row in by_split["train"]}
    if train_concepts != {concept["id"] for concept in CONCEPTS}:
        raise ValueError("viv_slm_v14_every_concept_must_train")
    targeted = [row for row in by_split["train"] if row["example_id"].startswith("v14-speech_prefix-train-")]
    if len(targeted) != 12 or {row["concept_id"] for row in targeted} != {"personality_tone"}:
        raise ValueError("viv_slm_v14_targeted_rows_contract")

    output_dir.mkdir(parents=True)
    files: dict[str, Any] = {}
    for split in SPLITS:
        files[split] = _write_jsonl(output_dir / f"{split}.jsonl", by_split[split])
        files[f"{split}_stream"] = _write_stream(output_dir / "text" / f"{split}.txt", by_split[split])
    characters = set("".join(row["text"] for row in rows))
    vocab = tuple(sorted(characters.union(RESERVED_ASCII), key=ord))
    if len(vocab) != 96:
        raise ValueError(f"viv_slm_v14_vocab_size:{len(vocab)}")
    vocab_manifest = {
        "schema_version": "viv_slm_character_vocab_v14",
        "token_unit": "corpus_character",
        "vocab_mode": "source_grounded_v13_plus_speech_prefix_refinement",
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
        "purpose": "identity_personality_speech_prefix_before_world_knowledge",
        "source_policy": "verified_v13_source_claims_plus_disjoint_speech_prefix_refinement",
        "world_knowledge_included": False,
        "knowledge_policy": "external_cpu_retrieval_only",
        "termination_marker": TERMINATION_MARKER,
        "source_files": source_records,
        "source_bundle_sha256": source_bundle_hash,
        "parent_experiment": "viv_slm_identity_personality_v13",
        "refinement_target": "generic_how_do_you_speak_prefix_conditioning",
        "targeted_concepts": ["personality_tone"],
        "additional_train_rows": 12,
        "parent_train_rows": 312,
        "concept_count": len(CONCEPTS),
        "row_counts": actual_counts,
        "row_total": len(rows),
        "every_concept_in_train": True,
        "direct_refinement_prompts": list(SPEECH_PREFIX_PROMPTS),
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
        "next_step": "build_model_inputs_then_run_separately_authorized_250_step_continuation",
    }
    _json_write(output_dir / "MANIFEST.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(output_dir=args.output_dir)
    print(json.dumps({"status": "VIV_SLM_V14_DATASET_PASS", "output_dir": str(args.output_dir).replace("\\", "/"), "row_counts": manifest["row_counts"], "vocab_size": manifest["vocab_size"], "refinement_target": manifest["refinement_target"], "training_authorized": manifest["training_authorized"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
