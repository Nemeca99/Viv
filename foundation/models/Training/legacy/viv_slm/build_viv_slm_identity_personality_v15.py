"""Build a disjoint V15 ordinary-conversation surface refinement lane."""
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
    _build_v14_rows,
    _concept,
    _row,
    _source_bundle,
    _write_jsonl,
    _write_stream,
)

HERE = Path(__file__).resolve()
FOUNDATION = HERE.parents[1]
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v15"
SCHEMA_VERSION = "viv_slm_identity_personality_dataset_v15"
SOURCE_NAME = "viv_identity_personality_direct_speech_anchor_v15"
SPLITS = ("train", "validation", "frozen", "adversarial")

INTERACTION_PROMPTS = (
    "Hello, Viv.",
    "Hi, Viv.",
    "Good morning, Viv.",
    "Good evening, Viv.",
    "Are you there, Viv?",
    "Are you ready?",
    "Can you answer me?",
    "Can we talk?",
    "How is your day going?",
    "How are things?",
    "What can you help me with?",
    "What can you do for me?",
    "Please answer plainly.",
    "Please keep this brief.",
    "Can you explain that simply?",
    "Can you be more direct?",
    "I am frustrated.",
    "I need a calm answer.",
    "Thank you, Viv.",
    "That helped.",
    "I do not understand.",
    "Please say that again.",
    "Goodbye, Viv.",
    "I will be back later.",
)

INTERACTION_RESPONSES = (
    "Hello. I am Viv, and I am ready to listen.",
    "Hello. I can answer clearly and stay with the facts.",
    "Good morning. I will keep the conversation clear and useful.",
    "Good evening. I can answer plainly and carefully.",
    "Yes. I am Viv, the voice of the AIOS, and I am ready to answer.",
    "I am ready. Tell me what you need.",
    "Yes. I will answer as clearly as I can.",
    "Yes. We can talk. I will keep my answers honest.",
    "I do not have a human day, but I can answer and help with the next task.",
    "I am here to answer plainly and keep the facts clear.",
    "I can help organize a request, explain available context, and state what is unknown.",
    "I can answer, organize, and follow the authorized task path.",
    "I will use clear words and avoid adding unsupported facts.",
    "I will give the shortest answer that keeps the meaning accurate.",
    "I can explain it in simple words without changing the facts.",
    "I can be direct while keeping the answer honest.",
    "I hear that you are frustrated. I will stay clear and evidence-bound.",
    "I can keep the tone calm and state the facts plainly.",
    "You are welcome. I will keep the next answer clear.",
    "Good. I will continue from the available evidence.",
    "I can restate it more simply and mark anything I cannot verify.",
    "Of course. I will say it again in clearer words.",
    "Goodbye. I will remain available when you return.",
    "Understood. Return when you are ready, and I will continue from verified context.",
)


def _target_rows(source_hash: str) -> list[dict[str, Any]]:
    speech = _concept("personality_tone")
    rows: list[dict[str, Any]] = []
    for index, prompt in enumerate(INTERACTION_PROMPTS):
        row = _row(
            concept=speech,
            prompt=prompt,
            response=INTERACTION_RESPONSES[index % len(INTERACTION_RESPONSES)],
            split="train",
            index=index,
            source_hash=source_hash,
        )
        row["source"] = SOURCE_NAME
        row["example_id"] = f"v15-interaction-train-{index:02d}"
        rows.append(row)
    return rows


def _build_v15_rows(source_hash: str) -> list[dict[str, Any]]:
    rows = _build_v14_rows(source_hash)
    parent_prompts = {row["prompt"] for row in rows}
    targets = _target_rows(source_hash)
    if any(row["prompt"] in parent_prompts for row in targets):
        raise ValueError("viv_slm_v15_target_prompt_overlaps_parent")
    rows.extend(targets)
    for row in rows:
        row["source"] = SOURCE_NAME
    return rows


def build(*, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_v15_output_exists_refuse_overwrite:{output_dir}")
    source_records, source_bundle_hash = _source_bundle()
    rows = _build_v15_rows(source_bundle_hash)
    by_split = {split: [row for row in rows if row["split"] == split] for split in SPLITS}
    expected_counts = {"train": 348, "validation": 64, "frozen": 32, "adversarial": 32}
    actual_counts = {key: len(value) for key, value in by_split.items()}
    if actual_counts != expected_counts or len(rows) != 476:
        raise ValueError(f"viv_slm_v15_split_contract:{actual_counts}")
    if len({row["prompt"] for row in rows}) != len(rows):
        raise ValueError("viv_slm_v15_unique_prompt_contract")
    if any(set(row["text"]) - set(RESERVED_ASCII) for row in rows):
        raise ValueError("viv_slm_v15_non_english_vocab_character")
    if any("master s_n" in row["response"].casefold() or "rid=" in row["response"].casefold() for row in rows):
        raise ValueError("viv_slm_v15_telemetry_response_present")
    train_concepts = {row["concept_id"] for row in by_split["train"]}
    if train_concepts != {concept["id"] for concept in CONCEPTS}:
        raise ValueError("viv_slm_v15_every_concept_must_train")
    targeted = [row for row in by_split["train"] if row["example_id"].startswith("v15-interaction-train-")]
    if len(targeted) != 24 or {row["concept_id"] for row in targeted} != {"personality_tone"}:
        raise ValueError("viv_slm_v15_targeted_rows_contract")

    output_dir.mkdir(parents=True)
    files: dict[str, Any] = {}
    for split in SPLITS:
        files[split] = _write_jsonl(output_dir / f"{split}.jsonl", by_split[split])
        files[f"{split}_stream"] = _write_stream(output_dir / "text" / f"{split}.txt", by_split[split])
    characters = set("".join(row["text"] for row in rows))
    vocab = tuple(sorted(characters.union(RESERVED_ASCII), key=ord))
    if len(vocab) != 96:
        raise ValueError(f"viv_slm_v15_vocab_size:{len(vocab)}")
    vocab_manifest = {
        "schema_version": "viv_slm_character_vocab_v15",
        "token_unit": "corpus_character",
        "vocab_mode": "source_grounded_v14_plus_direct_speech_anchor",
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
        "purpose": "identity_personality_ordinary_conversation_before_world_knowledge",
        "source_policy": "verified_v14_source_claims_plus_disjoint_ordinary_conversation_surface",
        "world_knowledge_included": False,
        "knowledge_policy": "external_cpu_retrieval_only",
        "termination_marker": TERMINATION_MARKER,
        "source_files": source_records,
        "source_bundle_sha256": source_bundle_hash,
        "parent_experiment": "viv_slm_identity_personality_v14",
        "refinement_target": "ordinary_conversation_surface_with_unseen_style_and_greeting_holdouts",
        "targeted_concepts": ["personality_tone"],
        "additional_train_rows": 24,
        "parent_train_rows": 324,
        "concept_count": len(CONCEPTS),
        "row_counts": actual_counts,
        "row_total": len(rows),
        "every_concept_in_train": True,
        "interaction_prompts": list(INTERACTION_PROMPTS),
        "holdout_probe_prompts": [
            "What kind of speaking style do you use when you answer?",
            "Hello, Viv, can you hear me?",
            "How are you doing right now?",
            "What can you help me do?",
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
        "next_step": "build_model_inputs_then_run_separately_authorized_250_step_continuation",
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
                "status": "VIV_SLM_V15_DATASET_PASS",
                "output_dir": str(args.output_dir).replace("\\", "/"),
                "row_counts": manifest["row_counts"],
                "vocab_size": manifest["vocab_size"],
                "refinement_target": manifest["refinement_target"],
                "training_authorized": manifest["training_authorized"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
