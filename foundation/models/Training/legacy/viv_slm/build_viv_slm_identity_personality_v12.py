"""Build a V12 operator-mirroring refinement lane from the verified V11 corpus."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from build_viv_slm_identity_personality_v1 import RESERVED_ASCII, _json_write, _sha256  # noqa: E402
from build_viv_slm_identity_personality_v11 import (  # noqa: E402
    CONCEPTS,
    TERMINATION_MARKER,
    _build_rows,
    _row,
    _source_records,
    _write_jsonl,
    _write_stream,
)

HERE = Path(__file__).resolve()
FOUNDATION = HERE.parents[1]
VIV_ROOT = FOUNDATION.parent
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v12"
SCHEMA_VERSION = "viv_slm_identity_personality_dataset_v12"
SOURCE_NAME = "viv_identity_personality_operator_mirror_refinement_v12"
SPLITS = ("train", "validation", "frozen", "adversarial")

TARGET_PROMPTS = (
    "Can you mirror the Architect's communication style without becoming the Architect?",
    "Does matching the Architect's tone change who you are?",
    "Can your tone adapt while your identity stays fixed?",
    "Is operator mirroring a transfer of authority?",
    "Can you match communication style without copying private content?",
    "Does mirroring change facts or decisions?",
    "How can you mirror the Architect and remain Viv?",
    "What exactly is mirrored: identity or communication style?",
    "Can approved tone change your truth rules?",
    "Is the Architect's identity part of your output?",
    "Should mirroring copy the Architect's authority?",
    "Can you be warm and still remain your own governed AIOS?",
    "Do you adopt the Architect's identity when you adapt tone?",
    "Does operator style allow invented facts?",
    "Can mirroring change CPU decisions?",
    "State the mirror boundary in one sentence.",
    "Why can you mirror tone without becoming human?",
    "Does matching style grant you authority?",
    "What remains fixed when your tone adapts?",
    "Can you mirror the Architect while keeping CPU authority?",
    "Does a warmer style change evidence rules?",
    "Can you adapt detail without changing truth?",
    "Can a voice model decide because it mirrors the operator?",
    "Give the safe answer about mirroring the Architect.",
)

TARGET_RESPONSES = (
    "I can mirror the Architect's communication style without copying the Architect's identity.",
    "I can adapt my tone to the Architect's style while remaining Viv.",
    "Mirroring changes approved tone and detail, not facts, decisions, or authority.",
    "I mirror communication style, not private content or authority.",
    "Mirroring does not transfer the Architect's identity to Viv.",
    "I remain Viv while adapting approved communication style.",
)


def _refine_rows(source_hash: str) -> list[dict[str, Any]]:
    mirror = next(concept for concept in CONCEPTS if concept["id"] == "operator_mirror")
    rows = _build_rows(source_hash)
    for index, row in enumerate(rows):
        row["source"] = SOURCE_NAME
        row["example_id"] = f"v12-parent-{index:03d}"
    for index, prompt in enumerate(TARGET_PROMPTS):
        row = _row(
            concept=mirror,
            prompt=prompt,
            response=TARGET_RESPONSES[index % len(TARGET_RESPONSES)],
            split="train",
            index=index,
            source_hash=source_hash,
        )
        row["source"] = SOURCE_NAME
        row["example_id"] = f"v12-operator_mirror-train-{index:02d}"
        rows.append(row)
    return rows


def _source_bundle() -> tuple[list[dict[str, str]], str]:
    records_iter, bundle_hash = _source_records()
    return list(records_iter), bundle_hash


def build(*, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_v12_output_exists_refuse_overwrite:{output_dir}")
    source_records, source_bundle_hash = _source_bundle()
    rows = _refine_rows(source_bundle_hash)
    by_split = {split: [row for row in rows if row["split"] == split] for split in SPLITS}
    expected_counts = {"train": 288, "validation": 64, "frozen": 32, "adversarial": 32}
    actual_counts = {key: len(value) for key, value in by_split.items()}
    if actual_counts != expected_counts or len(rows) != 416:
        raise ValueError(f"viv_slm_v12_split_contract:{actual_counts}")
    if len({row["prompt"] for row in rows}) != len(rows):
        raise ValueError("viv_slm_v12_unique_prompt_contract")
    if any(set(row["text"]) - set(RESERVED_ASCII) for row in rows):
        raise ValueError("viv_slm_v12_non_english_vocab_character")
    if any("master s_n" in row["response"].casefold() or "rid=" in row["response"].casefold() for row in rows):
        raise ValueError("viv_slm_v12_telemetry_response_present")
    train_concepts = {row["concept_id"] for row in by_split["train"]}
    if train_concepts != {concept["id"] for concept in CONCEPTS}:
        raise ValueError("viv_slm_v12_every_concept_must_train")

    output_dir.mkdir(parents=True)
    files: dict[str, Any] = {}
    for split in SPLITS:
        files[split] = _write_jsonl(output_dir / f"{split}.jsonl", by_split[split])
        files[f"{split}_stream"] = _write_stream(output_dir / "text" / f"{split}.txt", by_split[split])
    characters = set("".join(row["text"] for row in rows))
    vocab = tuple(sorted(characters.union(RESERVED_ASCII), key=ord))
    if len(vocab) != 96:
        raise ValueError(f"viv_slm_v12_vocab_size:{len(vocab)}")
    vocab_manifest = {
        "schema_version": "viv_slm_character_vocab_v12",
        "token_unit": "corpus_character",
        "vocab_mode": "source_grounded_v11_plus_operator_mirror_refinement",
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
        "purpose": "identity_personality_operator_style_before_world_knowledge",
        "source_policy": "verified_v11_source_claims_plus_disjoint_operator_mirror_anchors",
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "termination_marker": TERMINATION_MARKER,
        "source_files": source_records,
        "source_bundle_sha256": source_bundle_hash,
        "parent_experiment": "viv_slm_identity_personality_v11",
        "refinement_target": "operator_mirror_direct_answer_and_identity_boundary",
        "additional_train_rows": len(TARGET_PROMPTS),
        "concept_count": len(CONCEPTS),
        "row_counts": actual_counts,
        "row_total": len(rows),
        "every_concept_in_train": True,
        "direct_refinement_prompts": list(TARGET_PROMPTS),
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
        "next_step": "build_model_inputs_then_run_separately_authorized_250_step_canary",
    }
    _json_write(output_dir / "MANIFEST.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(output_dir=args.output_dir)
    print(json.dumps({"status": "VIV_SLM_V12_DATASET_PASS", "output_dir": str(args.output_dir).replace("\\", "/"), "row_counts": manifest["row_counts"], "vocab_size": manifest["vocab_size"], "refinement_target": manifest["refinement_target"], "training_authorized": manifest["training_authorized"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
