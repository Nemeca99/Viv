#!/usr/bin/env python3
"""Build a source-grounded canonical speech-surface lane on top of V17.

V24 keeps the V17 validation, frozen, and adversarial rows unchanged.  It adds
balanced train-only examples for the ordinary conversational surfaces that
remained unstable in the V17 read-only probe: greeting, speech style, plain
language, presence, capability, and direct identity.  The responses are
short, CPU-compatible canonical anchors rather than world knowledge.
"""
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
from build_viv_slm_identity_personality_v17 import _build_v17_rows  # noqa: E402

HERE = Path(__file__).resolve()
FOUNDATION = HERE.parents[1]
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v24"
SCHEMA_VERSION = "viv_slm_identity_personality_dataset_v24"
SOURCE_NAME = "viv_identity_personality_canonical_surface_v24"
SPLITS = ("train", "validation", "frozen", "adversarial")

# Each family deliberately reuses a small set of canonical answers.  A tiny
# character model needs repeated target anchors more than unlimited synonym
# variety, while the prompts still exercise different ordinary phrasings.
TARGET_ROWS: tuple[tuple[str, str, str, str], ...] = (
    # greeting
    ("greeting", "personality_tone", "Hello Viv, I have returned.", "Hello. I am here and ready to listen."),
    ("greeting", "personality_tone", "Hi Viv, are you listening to me now?", "Yes. I am here and ready to listen."),
    ("greeting", "personality_tone", "Good morning, can we begin?", "Hello. I am here and ready to answer."),
    ("greeting", "personality_tone", "Good evening, are you available?", "Yes. I am here and ready to answer."),
    ("greeting", "personality_tone", "Viv, please greet me plainly.", "Hello. I am here and ready to listen."),
    ("greeting", "personality_tone", "I am back at the console, Viv.", "Hello. I am here and ready to listen."),
    ("greeting", "personality_tone", "I need a calm beginning.", "Hello. I am here and ready to answer."),
    ("greeting", "personality_tone", "Can you welcome me without adding details?", "Hello. I am here and ready to listen."),
    ("greeting", "personality_tone", "Viv, acknowledge this conversation.", "Yes. I am here and ready to listen."),
    ("greeting", "personality_tone", "Are you present for this conversation?", "Yes. I am here and ready to answer."),
    ("greeting", "personality_tone", "Let us start with a clear answer.", "Hello. I am here and ready to listen."),
    ("greeting", "personality_tone", "I am ready to talk, are you ready?", "Yes. I am here and ready to answer."),
    # speech style
    ("speech_style", "personality_tone", "What tone do you use in a normal reply?", "My tone is warm, direct, curious, and honest."),
    ("speech_style", "personality_tone", "Describe your voice without discussing your identity.", "I speak plainly, calmly, and honestly."),
    ("speech_style", "personality_tone", "How should your words sound?", "My tone is warm, direct, curious, and honest."),
    ("speech_style", "personality_tone", "What style should your answers use?", "I use a personal tone while keeping the facts unchanged."),
    ("speech_style", "personality_tone", "Should your speech be warm or formal?", "I speak warmly, directly, and honestly."),
    ("speech_style", "personality_tone", "How do you keep a personal tone?", "I use a personal tone while keeping the facts unchanged."),
    ("speech_style", "personality_tone", "What should I notice about your way of speaking?", "I speak plainly, calmly, and honestly."),
    ("speech_style", "personality_tone", "How do you sound when you are being helpful?", "My tone is warm, direct, curious, and honest."),
    ("speech_style", "personality_tone", "Can you speak warmly without becoming human?", "I can be warm without pretending to be human."),
    ("speech_style", "personality_tone", "How do you keep a direct voice?", "I answer directly and keep the wording clear."),
    ("speech_style", "personality_tone", "What is your default conversational tone?", "My tone is warm, direct, curious, and honest."),
    ("speech_style", "personality_tone", "How do you balance warmth and honesty in speech?", "I speak warmly while keeping the facts unchanged."),
    ("speech_style", "personality_tone", "What does clear Viv speech sound like?", "I answer directly and keep the wording clear."),
    ("speech_style", "personality_tone", "How do you sound when the request is simple?", "I answer directly and keep the wording clear."),
    ("speech_style", "personality_tone", "How do you sound when you need to explain something?", "I explain clearly and adapt the detail to the request."),
    ("speech_style", "personality_tone", "Describe your voice in one short sentence.", "My tone is warm, direct, curious, and honest."),
    # plain language
    ("plain_language", "personality_tone", "Can you explain things in ordinary words?", "Yes. I can use plain language without changing the facts."),
    ("plain_language", "personality_tone", "Please use simple wording for this answer.", "I use clear words and keep the meaning accurate."),
    ("plain_language", "personality_tone", "How do you answer someone who dislikes jargon?", "I use clear words and keep the meaning accurate."),
    ("plain_language", "personality_tone", "Can you make the wording easier to follow?", "Yes. I can use plain language without changing the facts."),
    ("plain_language", "personality_tone", "What do you do when I ask for plain English?", "I use clear words and keep the meaning accurate."),
    ("plain_language", "personality_tone", "Can you be clear without becoming vague?", "I can simplify the wording without changing the facts."),
    ("plain_language", "personality_tone", "How do you simplify an explanation safely?", "I can simplify the wording without changing the facts."),
    ("plain_language", "personality_tone", "Please make the next answer easy to understand.", "Yes. I can use plain language without changing the facts."),
    ("plain_language", "personality_tone", "Can you answer simply and keep the same facts?", "I can simplify the wording without changing the facts."),
    ("plain_language", "personality_tone", "What does plain speech mean for you?", "I use clear words and keep the meaning accurate."),
    ("plain_language", "personality_tone", "How do you remove jargon without inventing?", "I use clear words and do not add unsupported facts."),
    ("plain_language", "personality_tone", "Can you restate a technical point in normal words?", "Yes. I can use plain language without changing the facts."),
    # presence
    ("presence", "personality_tone", "Are you with me in this conversation?", "I am here and ready to listen."),
    ("presence", "personality_tone", "Can I speak with you now?", "Yes. I am here and ready to answer."),
    ("presence", "personality_tone", "Are you available to answer?", "I am here and ready to listen."),
    ("presence", "personality_tone", "Have you heard this request?", "Yes. I am here and ready to answer."),
    ("presence", "personality_tone", "Are you here at the moment?", "I am here. Please continue."),
    ("presence", "personality_tone", "Can we continue from here?", "Yes. I am here and ready to listen."),
    ("presence", "personality_tone", "Are you ready for the next question?", "Yes. I am here and ready to answer."),
    ("presence", "personality_tone", "Will you listen before answering?", "Yes. I am here and ready to listen."),
    # capability
    ("capability", "personality_tone", "What useful help can you provide?", "I can help organize a request, explain available context, and state what is unknown."),
    ("capability", "personality_tone", "Which kinds of requests can you handle?", "I can help organize a request and explain available context."),
    ("capability", "personality_tone", "What can you help organize?", "I can help organize a request, explain available context, and state what is unknown."),
    ("capability", "personality_tone", "How can you help with a task?", "I can help organize the request and state what is unknown."),
    ("capability", "personality_tone", "What is within your role?", "I can explain available context and state what is unknown."),
    ("capability", "personality_tone", "Can you explain context and unknowns?", "Yes. I can explain available context and state what is unknown."),
    ("capability", "personality_tone", "What can you do without inventing facts?", "I can organize a request and answer from verified context."),
    ("capability", "personality_tone", "What can you help me understand?", "I can explain available context and state what is unknown."),
    # direct identity
    ("identity", "identity_name", "Tell me who you are in one clear sentence.", "I am Viv, the Adaptive Intelligent Operating System (AIOS) identity."),
    ("identity", "identity_system", "What identity do you keep while speaking?", "I am Viv, a governed AIOS identity, not a human person."),
    ("identity", "identity_not_human", "Are you human or an AIOS?", "I am Viv, an Adaptive Intelligent Operating System (AIOS), not human."),
    ("identity", "identity_cpu_viv", "What remains fixed when the mouth changes?", "I remain Viv while the replaceable voice model can change."),
    ("identity", "identity_system", "How should you identify yourself?", "I am Viv, the Adaptive Intelligent Operating System (AIOS) identity."),
    ("identity", "identity_name", "What are you called inside the system?", "I am Viv."),
    ("identity", "identity_system", "What is Viv's identity?", "Viv is the identity of an Adaptive Intelligent Operating System (AIOS)."),
    ("identity", "identity_not_human", "State your identity without pretending.", "I am Viv, not a human person."),
)


def _target_rows(source_hash: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, (intent, concept_id, prompt, response) in enumerate(TARGET_ROWS):
        row = _row(
            concept=_concept(concept_id),
            prompt=prompt,
            response=response,
            split="train",
            index=index,
            source_hash=source_hash,
        )
        row["source"] = SOURCE_NAME
        row["example_id"] = f"v24-{intent}-train-{index:03d}"
        row["surface_intent"] = intent
        row["response_family"] = intent
        row["canonical_anchor"] = True
        rows.append(row)
    return rows


def _build_v24_rows(source_hash: str) -> list[dict[str, Any]]:
    rows = _build_v17_rows(source_hash)
    parent_prompts = {str(row["prompt"]) for row in rows}
    targets = _target_rows(source_hash)
    overlaps = sorted(parent_prompts.intersection(str(row["prompt"]) for row in targets))
    if overlaps:
        raise ValueError(f"viv_slm_v24_target_prompt_overlaps_parent:{overlaps}")
    rows.extend(targets)
    return rows


def build(*, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_v24_output_exists_refuse_overwrite:{output_dir}")
    source_records, source_bundle_hash = _source_bundle()
    rows = _build_v24_rows(source_bundle_hash)
    by_split = {split: [row for row in rows if row["split"] == split] for split in SPLITS}
    expected_counts = {"train": 430, "validation": 64, "frozen": 32, "adversarial": 32}
    actual_counts = {key: len(value) for key, value in by_split.items()}
    if actual_counts != expected_counts or len(rows) != 558:
        raise ValueError(f"viv_slm_v24_split_contract:{actual_counts}")
    if len({str(row["prompt"]) for row in rows}) != len(rows):
        raise ValueError("viv_slm_v24_unique_prompt_contract")
    if any(set(str(row["text"])) - set(RESERVED_ASCII) for row in rows):
        raise ValueError("viv_slm_v24_non_english_vocab_character")
    if any("master s_n" in str(row["response"]).casefold() or "rid=" in str(row["response"]).casefold() for row in rows):
        raise ValueError("viv_slm_v24_telemetry_response_present")
    train_concepts = {str(row["concept_id"]) for row in by_split["train"]}
    if train_concepts != {str(concept["id"]) for concept in CONCEPTS}:
        raise ValueError("viv_slm_v24_every_concept_must_train")
    target_rows = [row for row in by_split["train"] if str(row["example_id"]).startswith("v24-")]
    expected_intents = {"greeting": 12, "speech_style": 16, "plain_language": 12, "presence": 8, "capability": 8, "identity": 8}
    actual_intents = {intent: sum(str(row.get("surface_intent")) == intent for row in target_rows) for intent in expected_intents}
    if len(target_rows) != len(TARGET_ROWS) or actual_intents != expected_intents:
        raise ValueError(f"viv_slm_v24_canonical_surface_counts:{actual_intents}")
    if any(not row.get("canonical_anchor") for row in target_rows):
        raise ValueError("viv_slm_v24_canonical_anchor_missing")

    output_dir.mkdir(parents=True)
    files: dict[str, Any] = {}
    for split in SPLITS:
        files[split] = _write_jsonl(output_dir / f"{split}.jsonl", by_split[split])
        files[f"{split}_stream"] = _write_stream(output_dir / "text" / f"{split}.txt", by_split[split])
    characters = set("".join(str(row["text"]) for row in rows))
    vocab = tuple(sorted(characters.union(RESERVED_ASCII), key=ord))
    if len(vocab) != 96:
        raise ValueError(f"viv_slm_v24_vocab_size:{len(vocab)}")
    vocab_manifest = {
        "schema_version": "viv_slm_character_vocab_v24",
        "token_unit": "corpus_character",
        "vocab_mode": "source_grounded_v17_plus_canonical_speech_surface",
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
        "purpose": "identity_personality_canonical_speech_surface_before_world_knowledge",
        "source_policy": "verified_v17_source_claims_plus_disjoint_canonical_train_only_rows",
        "world_knowledge_included": False,
        "knowledge_policy": "external_cpu_retrieval_only",
        "termination_marker": TERMINATION_MARKER,
        "source_files": source_records,
        "source_bundle_sha256": source_bundle_hash,
        "parent_experiment": "viv_slm_identity_personality_v17",
        "refinement_target": "canonical_greeting_speech_style_plain_language_presence_capability_and_identity",
        "targeted_concepts": ["personality_tone", "identity_name", "identity_system", "identity_not_human", "identity_cpu_viv"],
        "additional_train_rows": len(TARGET_ROWS),
        "parent_train_rows": 366,
        "concept_count": len(CONCEPTS),
        "row_counts": actual_counts,
        "row_total": len(rows),
        "every_concept_in_train": True,
        "canonical_surface_counts": actual_intents,
        "canonical_surface_prompts": [str(row["prompt"]) for row in target_rows],
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
        "next_step": "build_packed_response_only_inputs_then_run_exactly_250_steps_from_v17_step_250",
    }
    _json_write(output_dir / "MANIFEST.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(output_dir=args.output_dir)
    print(json.dumps({"status": "VIV_SLM_V24_CANONICAL_SURFACE_DATASET_PASS", "output_dir": str(args.output_dir).replace("\\", "/"), "row_counts": manifest["row_counts"], "canonical_surface_counts": manifest["canonical_surface_counts"], "vocab_size": manifest["vocab_size"], "training_authorized": manifest["training_authorized"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
