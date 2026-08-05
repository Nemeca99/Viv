"""Build the balanced V11 identity/personality corpus for Viv-SLM.

V10 proved that holding entire semantic concepts out of training causes
cross-answering. V11 keeps every source-grounded concept in the optimizer
split and holds out only alternate prompt forms. It reuses V10's checked
source claims and concept definitions without inheriting V10 checkpoints.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from build_viv_slm_identity_personality_v1 import RESERVED_ASCII, _json_write, _sha256  # noqa: E402
from build_viv_slm_identity_personality_v10 import (  # noqa: E402
    CLAIM_SOURCES,
    CONCEPTS,
    COLD_START_PATH,
    MANUAL_PATH,
    PERSONALITY_PATH,
    PROMPT_FORMS,
    SLM_DOC_PATH,
    TERMINATION_MARKER,
    _assert_source_claims,
)

HERE = Path(__file__).resolve()
FOUNDATION = HERE.parents[1]
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v11"
VIV_ROOT = FOUNDATION.parent
SCHEMA_VERSION = "viv_slm_identity_personality_dataset_v11"
SOURCE_NAME = "viv_identity_personality_source_grounded_balanced_v11"
SPLITS = ("train", "validation", "frozen", "adversarial")
EXTRA_TRAIN_PROMPTS: dict[str, str] = {
    "identity_system": "Who are you?",
    "personality_tone": "How do you speak?",
    "operator_mirror": "Do you mirror the Architect?",
    "missing_evidence": "What if evidence is missing?",
    "cpu_authority": "Who owns decisions?",
    "gpu_renderer": "What does the GPU mouth do?",
    "purpose": "What is your purpose?",
    "knowledge_boundary": "Is Wikipedia your identity?",
}
V11_PROMPT_FORMS = PROMPT_FORMS + (
    "Could you answer about {subject}?",
    "Why does {subject} matter here?",
    "Give the licensed answer about {subject}.",
    "Reject an unsafe or invented claim about {subject}.",
)


def _source_records() -> tuple[dict[str, str], str]:
    hashes = _assert_source_claims()
    source_bundle = "\n".join(f"{path}:{digest}" for path, digest in sorted(hashes.items()))
    return (
        {"path": path, "sha256": digest} for path, digest in sorted(hashes.items())
    ), sha256(source_bundle.encode("utf-8")).hexdigest()


def _row(*, concept: dict[str, Any], prompt: str, response: str, split: str, index: int, source_hash: str) -> dict[str, Any]:
    return {
        "authority_owner": "cpu_foundation",
        "canonical_claims": list(concept["claims"]),
        "concept_id": concept["id"],
        "deployment_changed": False,
        "domain": "identity_personality",
        "example_id": f"v11-{concept['id']}-{split}-{index:02d}",
        "hold_only": split != "train",
        "knowledge_policy": "external_cpu_retrieval_only",
        "model_role": "replaceable_renderer",
        "optimizer_eligible": split == "train",
        "prompt": prompt,
        "response": response,
        "response_only_target": True,
        "source": SOURCE_NAME,
        "source_hash": source_hash,
        "split": split,
        "telemetry_allowed": False,
        "termination_marker": TERMINATION_MARKER,
        "text": f"User: {prompt}\nViv: {response}\n{TERMINATION_MARKER}\n",
        "training_authorized": False,
        "run_authorized": False,
        "world_knowledge_included": False,
    }


def _build_rows(source_hash: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_prompts: set[str] = set()
    for concept in CONCEPTS:
        responses = tuple(str(item) for item in concept["responses"])
        prompts = tuple(form.format(subject=concept["subject"]) for form in V11_PROMPT_FORMS)
        for index, prompt in enumerate(prompts):
            split = "train" if index < 8 else ("validation" if index < 10 else ("frozen" if index == 10 else "adversarial"))
            if prompt in seen_prompts:
                raise ValueError(f"viv_slm_v11_duplicate_prompt:{prompt}")
            seen_prompts.add(prompt)
            rows.append(_row(concept=concept, prompt=prompt, response=responses[index % len(responses)], split=split, index=index, source_hash=source_hash))
        if concept["id"] in EXTRA_TRAIN_PROMPTS:
            prompt = EXTRA_TRAIN_PROMPTS[concept["id"]]
            if prompt in seen_prompts:
                raise ValueError(f"viv_slm_v11_duplicate_extra_prompt:{prompt}")
            seen_prompts.add(prompt)
            rows.append(_row(concept=concept, prompt=prompt, response=responses[len(rows) % len(responses)], split="train", index=12, source_hash=source_hash))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
    return {"path": str(path).replace("\\", "/"), "rows": len(rows), "sha256": _sha256(path)}


def _write_stream(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(row["text"] for row in rows) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return {"path": str(path).replace("\\", "/"), "characters": len(text), "sha256": _sha256(path)}


def build(*, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_v11_output_exists_refuse_overwrite:{output_dir}")
    source_records_iter, source_bundle_hash = _source_records()
    source_records = list(source_records_iter)
    rows = _build_rows(source_bundle_hash)
    by_split = {split: [row for row in rows if row["split"] == split] for split in SPLITS}
    expected_counts = {"train": 264, "validation": 64, "frozen": 32, "adversarial": 32}
    actual_counts = {key: len(value) for key, value in by_split.items()}
    if actual_counts != expected_counts or len(rows) != 392:
        raise ValueError(f"viv_slm_v11_split_contract:{actual_counts}")
    if len({row["prompt"] for row in rows}) != len(rows):
        raise ValueError("viv_slm_v11_unique_prompt_contract")
    if any(set(row["text"]) - set(RESERVED_ASCII) for row in rows):
        raise ValueError("viv_slm_v11_non_english_vocab_character")
    if any("master s_n" in row["response"].casefold() or "rid=" in row["response"].casefold() for row in rows):
        raise ValueError("viv_slm_v11_telemetry_response_present")
    train_concepts = {row["concept_id"] for row in by_split["train"]}
    if len(train_concepts) != len(CONCEPTS):
        raise ValueError("viv_slm_v11_every_concept_must_train")

    output_dir.mkdir(parents=True)
    files: dict[str, Any] = {}
    for split in SPLITS:
        files[split] = _write_jsonl(output_dir / f"{split}.jsonl", by_split[split])
        files[f"{split}_stream"] = _write_stream(output_dir / "text" / f"{split}.txt", by_split[split])
    characters = set("".join(row["text"] for row in rows))
    vocab = tuple(sorted(characters.union(RESERVED_ASCII), key=ord))
    if len(vocab) != 96:
        raise ValueError(f"viv_slm_v11_vocab_size:{len(vocab)}")
    vocab_manifest = {
        "schema_version": "viv_slm_character_vocab_v11",
        "token_unit": "corpus_character",
        "vocab_mode": "source_grounded_balanced_identity_personality_plus_reserved_ascii",
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
        "source_policy": "v10_source_claims_with_balanced_concept_splits_and_direct_probe_anchors",
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "termination_marker": TERMINATION_MARKER,
        "source_files": source_records,
        "source_bundle_sha256": source_bundle_hash,
        "parent_experiment": "viv_slm_identity_personality_v10",
        "concept_count": len(CONCEPTS),
        "row_counts": actual_counts,
        "row_total": len(rows),
        "every_concept_in_train": True,
        "direct_probe_anchors": sorted(EXTRA_TRAIN_PROMPTS.values()),
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
    print(json.dumps({"status": "VIV_SLM_V11_DATASET_PASS", "output_dir": str(args.output_dir).replace("\\", "/"), "row_counts": manifest["row_counts"], "vocab_size": manifest["vocab_size"], "every_concept_in_train": manifest["every_concept_in_train"], "training_authorized": manifest["training_authorized"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
