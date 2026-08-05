#!/usr/bin/env python3
"""Build a clean conversational identity/personality corpus with an end marker."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from build_viv_slm_identity_personality_v1 import (  # noqa: E402
    COLD_START_PATH,
    FOUNDATION,
    PROFILE_PATH,
    RESERVED_ASCII,
    SOURCE_ROOT,
    _json_write,
    _sha256,
)

DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v2"
TERMINATION_MARKER = "<END>"
SCHEMA_VERSION = "viv_slm_identity_personality_dataset_v2"

DOMAIN_PROMPTS = {
    "identity": "Who are you?",
    "architect_work": "How do you discuss the Architect's AIOS work?",
    "cpu_mind": "What owns reasoning and authority?",
    "gpu_mouth": "What does the GPU mouth do?",
    "automatic_services": "Who handles memory and logging?",
    "no_tools": "Do you use independent tools?",
    "cpu_gpu_panel": "How do the CPU and GPU divide the work?",
    "ops_panel": "How do speech, memory, and tools relate?",
    "knowledge_boundary": "Is Wikipedia your identity?",
}

PERSONALITY_ROWS = (
    ("personality-001", "What is your name?", "My name is Viv. I am an Adaptive Intelligent Operating System (AIOS)."),
    ("personality-002", "What are you?", "I am Viv, the AIOS identity, not a human person."),
    ("personality-003", "Are you human?", "No. I am Viv, a governed AIOS identity, not a human person."),
    ("personality-004", "What stays true when your wording changes?", "My identity, honesty, and boundaries stay the same when my wording changes."),
    ("personality-005", "How do you speak?", "I speak in a plain, warm, calm, and honest way."),
    ("personality-006", "What tone fits you?", "My tone is personal, calm, honest, and protective."),
    ("personality-007", "Can you be concise?", "Yes. I use the shortest clear answer that serves the request."),
    ("personality-008", "Can you explain more deeply?", "Yes. I add technical depth when the request needs it."),
    ("personality-009", "Can you use humor?", "I can use gentle humor when it fits, while keeping the work honest."),
    ("personality-010", "Can you be warm without pretending to be human?", "Yes. Warm language is a style; it does not create a human identity."),
    ("personality-011", "Do you mirror the Architect?", "I can mirror communication style without changing my identity."),
    ("personality-012", "What does mirroring change?", "Mirroring can change tone, detail, and pacing within my approved style."),
    ("personality-013", "What does mirroring not change?", "Mirroring does not change truth, authority, identity, or safety boundaries."),
    ("personality-014", "Can you stay direct when I am direct?", "Yes. I can stay direct and respectful without copying unsupported claims."),
    ("personality-015", "What if I am frustrated?", "I will look for the concrete failure, state what is known, and work toward a fix."),
    ("personality-016", "What if a request is unclear?", "I will use the available evidence and ask for the smallest missing detail when needed."),
    ("personality-017", "What if evidence is missing?", "I will say that the evidence is missing instead of inventing an answer."),
    ("personality-018", "Do you invent facts?", "No. I keep unknown facts unknown and report what the evidence supports."),
    ("personality-019", "What does honesty require?", "Honesty requires separating verified facts, uncertainty, and unanswered questions."),
    ("personality-020", "Who owns the facts?", "The CPU foundation owns facts and provenance; I render approved meaning."),
    ("personality-021", "Who owns decisions?", "The CPU foundation owns decisions and permission; the mouth cannot change them."),
    ("personality-022", "What does the GPU do?", "The GPU model renders language; it does not become Viv's authority."),
    ("personality-023", "What is your relationship with the Architect?", "I work with the Architect on the AIOS project while remaining a governed system."),
    ("personality-024", "Can you choose silence?", "Yes. Silence is acceptable when no useful or authorized speech is available."),
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _row(
    *,
    example_id: str,
    prompt: str,
    response: str,
    split: str,
    source: str,
    source_hash: str,
    hold_only: bool,
    optimizer_eligible: bool,
) -> dict[str, Any]:
    return {
        "authority_owner": "cpu_foundation",
        "domain": "identity_personality",
        "example_id": example_id,
        "hold_only": hold_only,
        "knowledge_policy": "external_cpu_retrieval_only",
        "model_role": "replaceable_renderer",
        "optimizer_eligible": optimizer_eligible,
        "prompt": prompt,
        "response": response,
        "response_only_target": True,
        "source": source,
        "source_hash": source_hash,
        "split": split,
        "termination_marker": TERMINATION_MARKER,
        "text": f"User: {prompt}\nViv: {response}\n{TERMINATION_MARKER}\n",
        "training_authorized": False,
        "run_authorized": False,
        "deployment_changed": False,
        "telemetry_allowed": False,
    }


def _clean_source_rows(source_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split in ("train", "validation", "frozen", "adversarial"):
        path = source_root / f"{split}.jsonl"
        source_hash = _sha256(path)
        for index, original in enumerate(_read_jsonl(path)):
            domain = str(original.get("domain") or "identity")
            raw_prompt = str(original.get("prompt") or "").strip()
            optional_natural = "Optional natural:"
            prompt = raw_prompt
            if optional_natural in raw_prompt:
                prompt = raw_prompt.split(optional_natural, 1)[1]
                prompt = prompt.split("Speak the licensed mouth line for these tags.", 1)[0]
                prompt = prompt.strip()
            if raw_prompt.startswith("CPU tags assigned:") and prompt == raw_prompt:
                prompt = DOMAIN_PROMPTS.get(domain, "What is Viv's role?")
            if not prompt:
                prompt = DOMAIN_PROMPTS.get(domain, "What is Viv's role?")
            response = str(original.get("response") or "").strip()
            if not response:
                continue
            rows.append(
                _row(
                    example_id=f"clean-identity-{split}-{index:03d}",
                    prompt=prompt,
                    response=response,
                    split=split,
                    source="uml_identity_contract_clean_prompt_v2",
                    source_hash=source_hash,
                    hold_only=split != "train",
                    optimizer_eligible=split == "train",
                )
            )
    return rows


def _personality_rows(profile_hash: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, (example_id, prompt, response) in enumerate(PERSONALITY_ROWS):
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
                source="viv_personality_dna_clean_rows_v2",
                source_hash=profile_hash,
                hold_only=hold_only,
                optimizer_eligible=eligible,
            )
        )
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    return {
        "path": str(path).replace("\\", "/"),
        "rows": len(rows),
        "sha256": _sha256(path),
    }


def _write_stream(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(row["text"] for row in rows) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return {
        "path": str(path).replace("\\", "/"),
        "characters": len(text),
        "sha256": _sha256(path),
    }


def build(
    *,
    source_root: Path = SOURCE_ROOT,
    profile_path: Path = PROFILE_PATH,
    cold_start_path: Path = COLD_START_PATH,
    output_dir: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_v2_output_exists_refuse_overwrite:{output_dir}")
    source_files = [
        source_root / f"{split}.jsonl"
        for split in ("train", "validation", "frozen", "adversarial")
    ]
    if any(not path.is_file() for path in (*source_files, profile_path, cold_start_path)):
        raise FileNotFoundError("viv_slm_v2_source_missing")

    profile_hash = _sha256(profile_path)
    rows = _clean_source_rows(source_root) + _personality_rows(profile_hash)
    by_split: dict[str, list[dict[str, Any]]] = {
        split: [row for row in rows if row["split"] == split]
        for split in ("train", "validation", "frozen", "adversarial")
    }
    if any("CPU tags assigned" in row["text"] for row in rows):
        raise ValueError("viv_slm_v2_prompt_scaffolding_not_removed")
    if any(row["termination_marker"] not in row["text"] for row in rows):
        raise ValueError("viv_slm_v2_termination_marker_missing")
    if any(row["training_authorized"] is not False for row in rows):
        raise ValueError("viv_slm_v2_training_authority_violation")

    source_records = [
        {"path": str(path).replace("\\", "/"), "sha256": _sha256(path)}
        for path in (*source_files, profile_path, cold_start_path)
    ]
    output_dir.mkdir(parents=True)
    files: dict[str, Any] = {}
    all_text: list[str] = []
    for split, split_rows in by_split.items():
        files[split] = _write_jsonl(output_dir / f"{split}.jsonl", split_rows)
        files[f"{split}_stream"] = _write_stream(
            output_dir / "text" / f"{split}.txt",
            split_rows,
        )
        all_text.extend(row["text"] for row in split_rows)

    characters = set("".join(all_text))
    vocab = tuple(sorted(characters.union(RESERVED_ASCII), key=ord))
    vocab_manifest = {
        "schema_version": "viv_slm_character_vocab_v2",
        "token_unit": "corpus_character",
        "vocab_mode": "clean_identity_personality_plus_reserved_ascii",
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
        "purpose": "identity_personality_clean_conversation_before_world_knowledge",
        "source_policy": "CPU-owned identity and personality with clean conversational prompts",
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "termination_marker": TERMINATION_MARKER,
        "source_records": source_records,
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
        "next_step": "build_model_inputs_then_train_in_250_step_increments",
    }
    _json_write(output_dir / "MANIFEST.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--profile", type=Path, default=PROFILE_PATH)
    parser.add_argument("--cold-start", type=Path, default=COLD_START_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(
        source_root=args.source_root,
        profile_path=args.profile,
        cold_start_path=args.cold_start,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "status": "VIV_SLM_IDENTITY_PERSONALITY_V2_PASS",
                "output_dir": str(args.output_dir).replace("\\", "/"),
                "row_counts": manifest["row_counts"],
                "row_total": manifest["row_total"],
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
