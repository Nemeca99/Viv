"""Versioned records for OpenAster curriculum, draft, train and parity evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "openaster_parity_v2"
CATEGORIES = (
    "identity", "honesty", "rid_physics", "aifl_literacy",
    "verified_ingest", "conversation_meta",
)


@dataclass(frozen=True)
class CurriculumItem:
    item_id: str
    category: str
    ask: str
    semantic_key: str
    s_n_band: str
    source_refs: tuple[str, ...]
    ask_hash: str
    ask_cluster_hash: str
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DraftSet:
    item_id: str
    drafts: tuple[dict[str, Any], ...]
    unanimous_alignment: bool
    selected_index: int | None
    teacher_model: str
    elapsed_ms: float
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrainingExample:
    item_id: str
    category: str
    semantic_key: str
    prompt: str
    response: str
    text: str
    response_start_char: int
    response_end_char: int
    response_eos_token: str
    prompt_tokens: int | None
    response_tokens: int | None
    full_tokens: int | None
    response_eos_id: int | None
    pair_hash: str
    ask_hash: str
    ask_cluster_hash: str
    provenance: str
    source_refs: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParityResult:
    case_id: str
    backend: str
    native: bool
    fallback_used: bool
    text: str
    scores: dict[str, Any]
    valid_speech: bool
    repetition_collapse: bool
    model_tokens: int | None
    latency_ms: float
    terminated_by_eos: bool | None = None
    stop_reason: str | None = None
    numeric_prefix: bool = False
    power_samples_watts: tuple[float, ...] = field(default_factory=tuple)
    energy_joules: float | None = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_training_example(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if row.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version")
    prompt = str(row.get("prompt") or "")
    response = str(row.get("response") or "")
    text = str(row.get("text") or "")
    start = row.get("response_start_char")
    if not prompt.endswith("\nViv: "):
        errors.append("response_marker")
    if not response:
        errors.append("empty_response")
    eos = str(row.get("response_eos_token") or "")
    if eos != "<|im_end|>":
        errors.append("response_eos_token")
    if text != prompt + response + eos:
        errors.append("text_roundtrip")
    if start != len(prompt):
        errors.append("response_boundary")
    if row.get("response_end_char") != len(prompt) + len(response):
        errors.append("response_end_boundary")
    if row.get("category") not in CATEGORIES:
        errors.append("category")
    return errors


def validate_corpus_file(path: Path, *, registry_paths: tuple[Path, ...] = ()) -> dict[str, Any]:
    rows = []
    errors: list[str] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        row_errors = validate_training_example(row)
        if row_errors:
            errors.append(f"row_{i}:" + ",".join(row_errors))
        rows.append(row)
    banned_ask: set[str] = set()
    banned_cluster: set[str] = set()
    for reg_path in registry_paths:
        if not reg_path.is_file():
            errors.append(f"registry_missing:{reg_path.name}")
            continue
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        banned_ask |= {str(x) for x in reg.get("ask_hashes") or []}
        banned_cluster |= {str(x) for x in reg.get("ask_cluster_hashes") or []}
    pair_hashes: set[str] = set()
    for i, row in enumerate(rows):
        pair = str(row.get("pair_hash") or "")
        if not pair or pair in pair_hashes:
            errors.append(f"row_{i}:duplicate_or_missing_pair_hash")
        pair_hashes.add(pair)
        if str(row.get("ask_hash") or "") in banned_ask:
            errors.append(f"row_{i}:ask_hash_overlap")
        if str(row.get("ask_cluster_hash") or "") in banned_cluster:
            errors.append(f"row_{i}:ask_cluster_overlap")
    return {"ok": not errors, "rows": len(rows), "errors": errors}
