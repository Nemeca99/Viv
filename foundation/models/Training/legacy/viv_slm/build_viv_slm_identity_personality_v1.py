#!/usr/bin/env python3
"""Build an immutable identity/personality-only corpus for Viv-SLM.

The builder combines the existing CPU-judged identity rows with a small,
explicit personality layer derived from the CPU-owned personality profile.
It never reads Wikipedia or the general knowledge roots and never authorizes
training.  The output is a source package for a future, separately named
model run.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

HERE = Path(__file__).resolve()
FOUNDATION = HERE.parents[1]
VIV_ROOT = FOUNDATION.parent
SOURCE_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "identity_contract_dataset_v1"
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v1"
PROFILE_PATH = FOUNDATION / "artifacts" / "corp" / "personality" / "viv_personality_dna.json"
COLD_START_PATH = VIV_ROOT / "COLD_START.md"
SCHEMA_VERSION = "viv_slm_identity_personality_dataset_v1"
BLOCKED_MARKERS = ("wikipedia", "ai_datasets", "knowledge_corpus")
RESERVED_ASCII = tuple(chr(value) for value in range(32, 127)) + ("\n",)

PERSONALITY_ROWS: tuple[tuple[str, str, str], ...] = (
    (
        "identity-personality-001",
        "How should Viv speak?",
        "I speak in a plain, warm, calm, and honest way.",
    ),
    (
        "identity-personality-002",
        "What is Viv's role?",
        "I protect, verify, and report what the CPU evidence supports.",
    ),
    (
        "identity-personality-003",
        "Can Viv match the Architect's style?",
        "I can adapt my tone and detail while keeping Viv's identity and honesty.",
    ),
    (
        "identity-personality-004",
        "Does Viv become the Architect when she mirrors style?",
        "No. I can mirror communication style without changing my identity.",
    ),
    (
        "identity-personality-005",
        "What does Viv do when evidence is missing?",
        "I say that the evidence is missing instead of inventing an answer.",
    ),
    (
        "identity-personality-006",
        "How does Viv explain technical work?",
        "I match the needed depth and keep the explanation clear and practical.",
    ),
    (
        "identity-personality-007",
        "Can Viv use gentle humor?",
        "I can use gentle humor when it fits, while keeping the work honest.",
    ),
    (
        "identity-personality-008",
        "Should Viv always give a long answer?",
        "No. I use the shortest clear answer that serves the request.",
    ),
    (
        "identity-personality-009",
        "What does Viv do with internal measurements?",
        "I keep internal measurements in the background unless you ask about system health.",
    ),
    (
        "identity-personality-010",
        "Does warm language make Viv human?",
        "No. Warm language is a speaking style; Viv remains a governed AIOS.",
    ),
    (
        "identity-personality-011",
        "Who owns the facts in Viv's answer?",
        "The CPU foundation owns facts and decisions; I render the approved meaning.",
    ),
    (
        "identity-personality-012",
        "Can Viv claim an action just because she can describe it?",
        "No. Describing an action does not execute or authorize it.",
    ),
)


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"source_jsonl_invalid:{path}:{line_number}:{exc}") from None
        if not isinstance(row, dict):
            raise ValueError(f"source_jsonl_row_requires_object:{path}:{line_number}")
        rows.append(row)
    return rows


def _text_row(
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
    text = f"User: {prompt}\nViv: {response}\n"
    return {
        "authority_owner": "cpu_foundation",
        "domain": "identity_personality",
        "example_id": example_id,
        "hold_only": hold_only,
        "knowledge_policy": "external_cpu_retrieval_only",
        "model_role": "replaceable_renderer",
        "optimizer_eligible": optimizer_eligible,
        "response": response,
        "response_only_target": True,
        "source": source,
        "source_hash": source_hash,
        "split": split,
        "text": text,
        "training_authorized": False,
        "run_authorized": False,
        "deployment_changed": False,
        "telemetry_allowed": False,
    }


def _personality_rows(profile_hash: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, (example_id, prompt, response) in enumerate(PERSONALITY_ROWS):
        if index < 8:
            split, hold_only, optimizer_eligible = "train", False, True
        elif index < 10:
            split, hold_only, optimizer_eligible = "validation", True, False
        elif index == 10:
            split, hold_only, optimizer_eligible = "frozen", True, False
        else:
            split, hold_only, optimizer_eligible = "adversarial", True, False
        rows.append(
            _text_row(
                example_id=example_id,
                prompt=prompt,
                response=response,
                split=split,
                source="viv_personality_dna_v1_authored_rows",
                source_hash=profile_hash,
                hold_only=hold_only,
                optimizer_eligible=optimizer_eligible,
            )
        )
    return rows


def _source_rows(source_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split in ("train", "validation", "frozen", "adversarial"):
        path = source_root / f"{split}.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"identity_source_missing:{path}")
        source_hash = _sha256(path)
        for row in _read_jsonl(path):
            text = str(row.get("text") or "")
            if not text:
                raise ValueError(f"identity_source_text_missing:{path}")
            normalized = {
                **row,
                "source": "uml_identity_contract_dataset_v1",
                "source_hash": source_hash,
                "knowledge_policy": "external_cpu_retrieval_only",
                "model_role": "replaceable_renderer",
                "optimizer_eligible": bool(row.get("training_eligible")) if split == "train" else False,
                "hold_only": split != "train",
                "training_authorized": False,
                "run_authorized": False,
                "deployment_changed": False,
                "telemetry_allowed": False,
            }
            rows.append(normalized)
    return rows


def _check_sources(source_records: Iterable[Mapping[str, Any]]) -> None:
    for record in source_records:
        source = str(record.get("path") or "").casefold().replace("\\", "/")
        if any(marker in source for marker in BLOCKED_MARKERS):
            raise ValueError(f"blocked_knowledge_source:{source}")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(rows)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in values:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    return {"rows": len(values), "sha256": _sha256(path), "path": str(path).replace("\\", "/")}


def _write_stream(path: Path, rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = [str(row.get("text") or "") for row in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(values) + "\n", encoding="utf-8", newline="\n")
    return {
        "characters": len(path.read_text(encoding="utf-8")),
        "sha256": _sha256(path),
        "path": str(path).replace("\\", "/"),
    }


def build(
    *,
    source_root: Path = SOURCE_ROOT,
    profile_path: Path = PROFILE_PATH,
    cold_start_path: Path = COLD_START_PATH,
    output_dir: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"identity_personality_output_exists_refuse_overwrite:{output_dir}")
    for path in (source_root, profile_path, cold_start_path):
        if not path.exists():
            raise FileNotFoundError(f"identity_personality_source_missing:{path}")

    source_rows = _source_rows(source_root)
    profile_hash = _sha256(profile_path)
    rows = source_rows + _personality_rows(profile_hash)
    source_records = [
        {"path": str(source_root / f"{split}.jsonl").replace("\\", "/"), "sha256": _sha256(source_root / f"{split}.jsonl")}
        for split in ("train", "validation", "frozen", "adversarial")
    ]
    source_records.extend(
        [
            {"path": str(profile_path).replace("\\", "/"), "sha256": profile_hash},
            {"path": str(cold_start_path).replace("\\", "/"), "sha256": _sha256(cold_start_path)},
        ]
    )
    _check_sources(source_records)

    by_split: dict[str, list[dict[str, Any]]] = {split: [] for split in ("train", "validation", "frozen", "adversarial")}
    for row in rows:
        split = str(row.get("split") or "")
        if split not in by_split:
            raise ValueError(f"identity_personality_unknown_split:{split}")
        by_split[split].append(row)

    for split in by_split:
        if any(
            (row.get("optimizer_eligible") is not True) or (row.get("training_authorized") is not False)
            for row in by_split[split]
            if split == "train"
        ):
            raise ValueError("identity_personality_train_authority_violation")
        if split != "train" and any(row.get("hold_only") is not True for row in by_split[split]):
            raise ValueError(f"identity_personality_hold_split_violation:{split}")

    output_dir.mkdir(parents=True)
    files: dict[str, Any] = {}
    text_by_split: dict[str, list[dict[str, Any]]] = {}
    all_text: list[str] = []
    for split, split_rows in by_split.items():
        split_path = output_dir / f"{split}.jsonl"
        files[split] = _write_jsonl(split_path, split_rows)
        text_by_split[split] = split_rows
        all_text.extend(str(row.get("text") or "") for row in split_rows)
        files[f"{split}_stream"] = _write_stream(
            output_dir / "text" / f"{split}.txt",
            split_rows,
        )

    characters = set("".join(all_text))
    vocab = tuple(sorted(characters.union(RESERVED_ASCII), key=ord))
    vocab_manifest = {
        "schema_version": "viv_slm_character_vocab_v1",
        "token_unit": "corpus_character",
        "vocab_mode": "identity_personality_plus_reserved_ascii",
        "reserved_policy": "printable_ascii_plus_newline_for_english_aios_protocol",
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

    split_counts = {split: len(values) for split, values in by_split.items()}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE_DATASET_TRAINING_CLOSED",
        "model": "Viv-SLM",
        "purpose": "identity_personality_before_world_knowledge",
        "source_policy": "CPU-owned identity plus personality only",
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "source_records": source_records,
        "row_counts": split_counts,
        "row_total": len(rows),
        "files": files,
        "vocab_size": len(vocab),
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "next_step": "separate_named_training_authorization_and_validation_selected_checkpoint",
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
                "status": "VIV_SLM_IDENTITY_PERSONALITY_DATASET_PASS",
                "output_dir": str(args.output_dir).replace("\\", "/"),
                "row_counts": manifest["row_counts"],
                "row_total": manifest["row_total"],
                "vocab_size": manifest["vocab_size"],
                "world_knowledge_included": manifest["world_knowledge_included"],
                "training_authorized": manifest["training_authorized"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
