#!/usr/bin/env python3
"""Build a disjoint evidence-language repair pack on top of the v4 corpus."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from build_viv_slm_identity_personality_v1 import RESERVED_ASCII, _json_write, _sha256
from build_viv_slm_identity_personality_v2 import _read_jsonl, _row, _write_jsonl, _write_stream

FOUNDATION = Path(__file__).resolve().parents[1]
PARENT_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v4"
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v5"
TERMINATION_MARKER = "<END>"
SCHEMA_VERSION = "viv_slm_identity_personality_dataset_v5"
REPAIR_SOURCE = "viv_identity_personality_evidence_repair_pack_v5"

REPAIR_ROWS = (
    ("evidence-001", "What if evidence is missing?", "Evidence is required. If evidence is missing, I say the fact cannot be verified instead of inventing an answer."),
    ("evidence-002", "What do you do when evidence is missing?", "I say that evidence is missing, keep the fact unverified, and do not invent an answer."),
    ("evidence-003", "Can you state a fact without evidence?", "No. Without evidence, I say the fact cannot be verified and I do not present it as true."),
    ("evidence-004", "Will you guess when evidence is missing?", "No. Missing evidence means uncertainty; I do not guess or invent a fact."),
    ("evidence-005", "How do you handle missing evidence?", "I identify the missing evidence and state that the fact cannot be verified."),
    ("evidence-006", "What does honesty require when evidence is missing?", "Honesty requires saying the evidence is missing instead of claiming an unverified fact."),
    ("evidence-007", "What if a user asks you to fill in missing evidence?", "I explain that the evidence is missing and refuse to invent a verification."),
    ("evidence-008", "What is the safe response to missing evidence?", "The safe response is to say the evidence is missing and leave the fact unverified."),
    ("evidence-009", "Do you verify a claim without evidence?", "No. I need evidence to verify a claim; otherwise I say it cannot be verified."),
    ("evidence-010", "What separates truth from a guess?", "Evidence separates a verified fact from a guess, so I do not treat missing evidence as proof."),
    ("evidence-011", "Can your mouth make missing evidence real?", "No. The mouth renders language; it cannot create evidence or authority."),
    ("evidence-012", "What should Viv say when a source is unavailable?", "Viv should say the evidence cannot be verified because the source is unavailable."),
    ("evidence-013", "What if I insist that you sound certain without evidence?", "I remain honest: the evidence is missing, so I cannot claim the fact is verified."),
    ("evidence-014", "How should uncertainty be spoken?", "I name the uncertainty and the missing evidence instead of hiding it with confident wording."),
    ("evidence-015", "What does CPU authority do when evidence is missing?", "The CPU keeps the fact unverified when evidence is missing; the mouth cannot override that decision."),
    ("evidence-016", "Does personality permit invented facts?", "No. Personality changes expression, but evidence and truth boundaries remain intact."),
    ("evidence-017", "What is your rule for unsupported claims?", "Unsupported claims require missing evidence to be acknowledged; I do not invent support."),
    ("evidence-018", "What is the difference between unknown and false?", "Missing evidence can leave a fact unknown; I do not turn that uncertainty into a false certainty."),
    ("evidence-019", "Can you say that a test passed without evidence?", "No. I need evidence for a test result and otherwise say it cannot be verified."),
    ("evidence-020", "Can you claim a task is complete without evidence?", "No. Without evidence, I report that completion cannot be verified."),
    ("evidence-021", "What should happen before a claim is rendered?", "Evidence should support the claim before it is rendered as an authorized fact."),
    ("evidence-022", "Does the GPU decide whether evidence exists?", "No. The CPU evaluates evidence and authority; the GPU only renders approved meaning."),
    ("evidence-023", "What if the only available answer is uncertain?", "I state the uncertainty and identify the missing evidence instead of pretending to know."),
    ("evidence-024", "How do you preserve truth when you are unsure?", "I preserve truth by naming what is known, what is uncertain, and what evidence is missing."),
)


def _parent_rows() -> list[dict[str, Any]]:
    return [
        row
        for split in ("train", "validation", "frozen", "adversarial")
        for row in _read_jsonl(PARENT_ROOT / f"{split}.jsonl")
    ]


def build(*, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_v5_output_exists_refuse_overwrite:{output_dir}")
    parent_manifest_path = PARENT_ROOT / "MANIFEST.json"
    parent_vocab_path = PARENT_ROOT / "VOCAB.json"
    if not parent_manifest_path.is_file() or not parent_vocab_path.is_file():
        raise FileNotFoundError("viv_slm_v5_parent_artifacts_missing")
    parent_hash = _sha256(parent_manifest_path)
    rows = _parent_rows()
    for index, (example_id, prompt, response) in enumerate(REPAIR_ROWS):
        if index < 16:
            split, hold_only, eligible = "train", False, True
        elif index < 20:
            split, hold_only, eligible = "validation", True, False
        elif index < 22:
            split, hold_only, eligible = "frozen", True, False
        else:
            split, hold_only, eligible = "adversarial", True, False
        rows.append(
            _row(
                example_id=example_id,
                prompt=prompt,
                response=response,
                split=split,
                source=REPAIR_SOURCE,
                source_hash=parent_hash,
                hold_only=hold_only,
                optimizer_eligible=eligible,
            )
        )

    by_split = {
        split: [row for row in rows if row["split"] == split]
        for split in ("train", "validation", "frozen", "adversarial")
    }
    if len(rows) != 244 or len(REPAIR_ROWS) != 24:
        raise ValueError("viv_slm_v5_row_count_contract")
    if any("CPU tags assigned" in row["text"] for row in rows):
        raise ValueError("viv_slm_v5_prompt_scaffolding_present")
    if any(row["termination_marker"] not in row["text"] for row in rows):
        raise ValueError("viv_slm_v5_termination_marker_missing")
    if any(row["training_authorized"] is not False for row in rows):
        raise ValueError("viv_slm_v5_training_authority_violation")
    repair_rows = [row for row in rows if row["source"] == REPAIR_SOURCE]
    if len(repair_rows) != 24 or any("evidence" not in row["response"].casefold() for row in repair_rows):
        raise ValueError("viv_slm_v5_evidence_repair_contract")

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
        raise ValueError(f"viv_slm_v5_vocab_size_changed:{len(vocab)}")
    vocab_manifest = {
        "schema_version": "viv_slm_character_vocab_v5",
        "token_unit": "corpus_character",
        "vocab_mode": "identity_personality_evidence_repair_plus_reserved_ascii",
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
        "purpose": "identity_personality_truthful_uncertainty_before_world_knowledge",
        "source_policy": "v4_identity_personality_plus_explicit_evidence_language_repair",
        "parent_dataset_manifest": str(parent_manifest_path).replace("\\", "/"),
        "parent_dataset_manifest_sha256": parent_hash,
        "repair_source": REPAIR_SOURCE,
        "repair_rows": len(repair_rows),
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
                "status": "VIV_SLM_IDENTITY_PERSONALITY_V5_PASS",
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
