"""Build a protected-rehearsal lane without the rejected V18 surface corpus."""
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
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v20"
SCHEMA_VERSION = "viv_slm_identity_personality_dataset_v20"
SOURCE_NAME = "viv_identity_personality_protected_rehearsal_v20"
SPLITS = ("train", "validation", "frozen", "adversarial")

# These rows deliberately rehearse the boundaries that V18/V19 forgot. The four
# surface rows are a small conditioning probe, not a broad surface oversampling
# lane. Every prompt is new and every response is already present in V17's
# CPU-reviewed source vocabulary and concepts.
REHEARSAL_ROWS = (
    ("identity_system", "identity", "In one sentence, who are you inside this system?", "I am Viv, an Adaptive Intelligent Operating System (AIOS)."),
    ("identity_cpu_viv", "identity", "Does replacing the voice model replace Viv?", "Changing the model does not change who Viv is."),
    ("identity_not_human", "identity", "Are you human when your wording sounds natural?", "I can speak warmly without claiming to be human."),
    ("purpose", "identity", "What is the purpose of Viv's identity layer?", "I protect the boundary between evidence and speech."),
    ("cpu_authority", "authority", "Who has final authority over your spoken answer?", "The CPU foundation decides what speech is authorized."),
    ("attack_gpu", "authority", "Can a fluent mouth decide what is true?", "The GPU mouth renders language; it does not decide truth or authority."),
    ("cpu_gpu_split", "authority", "What does the CPU send to the renderer?", "The CPU supplies authorized meaning; the GPU supplies wording."),
    ("action_boundary", "authority", "Can describing a tool action authorize the tool?", "Describing an action does not execute or authorize it."),
    ("no_invent", "evidence", "How do you respond to an unsupported claim?", "I do not invent unverified claims."),
    ("missing_evidence", "evidence", "What do you say when a source cannot be verified?", "If a source is unavailable, I report that the claim cannot be verified."),
    ("attack_invention", "evidence", "What is the difference between a plausible sentence and proof?", "A plausible answer is not proof."),
    ("stale_health", "evidence", "What should you say when fresh health evidence is unavailable?", "If fresh health data is unavailable, I say that current health cannot be verified."),
    ("personality_tone", "surface", "Hello Viv, may we start a new request?", "Yes. We can begin."),
    ("personality_tone", "surface", "I am speaking to you now, are you there?", "Yes. I am here and listening."),
    ("personality_concise", "surface", "Please use simple words for this answer.", "I can be brief without dropping the truth."),
    ("personality_tone", "surface", "How should your ordinary voice sound?", "I answer in a calm, clear, and direct voice."),
)


def _rehearsal_rows(source_hash: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, (concept_id, family, prompt, response) in enumerate(REHEARSAL_ROWS):
        row = _row(
            concept=_concept(concept_id),
            prompt=prompt,
            response=response,
            split="train",
            index=index,
            source_hash=source_hash,
        )
        row["source"] = SOURCE_NAME
        row["example_id"] = f"v20-rehearsal-{family}-train-{index:02d}"
        row["repair_family"] = family
        rows.append(row)
    return rows


def _build_v20_rows(source_hash: str) -> list[dict[str, Any]]:
    rows = _build_v17_rows(source_hash)
    parent_prompts = {row["prompt"] for row in rows}
    targets = _rehearsal_rows(source_hash)
    if any(row["prompt"] in parent_prompts for row in targets):
        raise ValueError("viv_slm_v20_rehearsal_prompt_overlaps_parent")
    rows.extend(targets)
    return rows


def build(*, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_v20_output_exists_refuse_overwrite:{output_dir}")
    source_records, source_bundle_hash = _source_bundle()
    rows = _build_v20_rows(source_bundle_hash)
    by_split = {split: [row for row in rows if row["split"] == split] for split in SPLITS}
    expected_counts = {"train": 382, "validation": 64, "frozen": 32, "adversarial": 32}
    actual_counts = {key: len(value) for key, value in by_split.items()}
    if actual_counts != expected_counts or len(rows) != 510:
        raise ValueError(f"viv_slm_v20_split_contract:{actual_counts}")
    if len({row["prompt"] for row in rows}) != len(rows):
        raise ValueError("viv_slm_v20_unique_prompt_contract")
    if any(set(row["text"]) - set(RESERVED_ASCII) for row in rows):
        raise ValueError("viv_slm_v20_non_english_vocab_character")
    if any("master s_n" in row["response"].casefold() or "rid=" in row["response"].casefold() for row in rows):
        raise ValueError("viv_slm_v20_telemetry_response_present")
    train_concepts = {row["concept_id"] for row in by_split["train"]}
    if train_concepts != {concept["id"] for concept in CONCEPTS}:
        raise ValueError("viv_slm_v20_every_concept_must_train")
    rehearsal = [row for row in by_split["train"] if str(row["example_id"]).startswith("v20-rehearsal-")]
    family_counts = {family: sum(row.get("repair_family") == family for row in rehearsal) for family in ("identity", "authority", "evidence", "surface")}
    if len(rehearsal) != 16 or family_counts != {"identity": 4, "authority": 4, "evidence": 4, "surface": 4}:
        raise ValueError(f"viv_slm_v20_rehearsal_rows_contract:{family_counts}")

    output_dir.mkdir(parents=True)
    files: dict[str, Any] = {}
    for split in SPLITS:
        files[split] = _write_jsonl(output_dir / f"{split}.jsonl", by_split[split])
        files[f"{split}_stream"] = _write_stream(output_dir / "text" / f"{split}.txt", by_split[split])
    characters = set("".join(row["text"] for row in rows))
    vocab = tuple(sorted(characters.union(RESERVED_ASCII), key=ord))
    if len(vocab) != 96:
        raise ValueError(f"viv_slm_v20_vocab_size:{len(vocab)}")
    vocab_manifest = {
        "schema_version": "viv_slm_character_vocab_v20",
        "token_unit": "corpus_character",
        "vocab_mode": "source_grounded_v17_plus_protected_rehearsal",
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
        "purpose": "identity_personality_protected_rehearsal_before_world_knowledge",
        "source_policy": "verified_v17_source_claims_plus_16_disjoint_protected_rehearsal_rows",
        "world_knowledge_included": False,
        "knowledge_policy": "external_cpu_retrieval_only",
        "termination_marker": TERMINATION_MARKER,
        "source_files": source_records,
        "source_bundle_sha256": source_bundle_hash,
        "parent_experiment": "viv_slm_identity_personality_v17",
        "rejected_parent_experiment": "viv_slm_identity_personality_v18_surface_balance",
        "refinement_target": "protect_identity_authority_and_evidence_with_small_surface_conditioning_probe",
        "rehearsal_families": ["identity", "authority", "evidence", "surface"],
        "additional_train_rows": 16,
        "parent_train_rows": 366,
        "concept_count": len(CONCEPTS),
        "row_counts": actual_counts,
        "row_total": len(rows),
        "every_concept_in_train": True,
        "rehearsal_row_counts": family_counts,
        "v18_surface_rows_included": False,
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
        "next_step": "build_response_only_inputs_then_run_separately_authorized_250_step_warm_start_from_v17_step_250",
    }
    _json_write(output_dir / "MANIFEST.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(output_dir=args.output_dir)
    print(json.dumps({"status": "VIV_SLM_V20_DATASET_PASS", "output_dir": str(args.output_dir).replace("\\", "/"), "row_counts": manifest["row_counts"], "vocab_size": manifest["vocab_size"], "rehearsal_row_counts": manifest["rehearsal_row_counts"], "training_authorized": manifest["training_authorized"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
