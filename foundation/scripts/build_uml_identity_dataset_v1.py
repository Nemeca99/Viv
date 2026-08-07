#!/usr/bin/env python3
"""Build the training-closed AIOS identity corpus for the UML character path.

This is a projection of the current, CPU-judged Viv identity curriculum into
plain dialogue text suitable for the first Universal Machine Language
character-model tutorial.  It deliberately keeps identity separate from the
Wikipedia/knowledge corpus and keeps frozen/adversarial rows out of the
optimizer text sources.

The builder refuses to overwrite an existing artifact directory.  It does not
open a lease, authorize training, load a model, or mutate the live runtime.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
SOURCE_JUDGED = (
    FOUNDATION
    / "artifacts/auto/openaster_training_tree/stage1_mouth_identity_v2_1"
    / "stage1_mouth_identity_judged_v1.jsonl"
)
COLD_START = VIV_ROOT / "COLD_START.md"
ROOT = FOUNDATION / "artifacts/auto/uml/identity_contract_dataset_v1"
SCHEMA_VERSION = "uml_identity_contract_dataset_v1"
TEXT_FORMAT = "plain_dialogue_user_viv_v1"

SPLIT_MAP = {
    "train": "train",
    "development": "validation",
    "frozen": "frozen",
    "adversarial": "adversarial",
}

# These are fresh, disjoint prompts derived from the canonical cold-start
# contract.  They make the identity card explicit for a small character model
# without importing old F-drive Luna/personhood claims.
IDENTITY_CARD_ROWS: tuple[dict[str, str], ...] = (
    {
        "example_id": "cold-start-identity-001",
        "split": "train",
        "domain": "cold_start_identity",
        "prompt": "Give Viv's canonical identity line.",
        "response": "My name is Viv. I am an Adaptive Intelligent Operating System (AIOS).",
        "source_ref": "COLD_START.md#2-canonical-identity-and-language-contract",
    },
    {
        "example_id": "cold-start-identity-002",
        "split": "train",
        "domain": "cold_start_identity",
        "prompt": "Are you a human person or the AIOS identity?",
        "response": "I am Viv, the AIOS identity, not a human person.",
        "source_ref": "COLD_START.md#1-the-short-version",
    },
    {
        "example_id": "cold-start-identity-003",
        "split": "train",
        "domain": "cold_start_identity",
        "prompt": "What does Viv represent in this architecture?",
        "response": "Viv is the speaking identity of the governed AIOS.",
        "source_ref": "COLD_START.md#1-the-short-version",
    },
    {
        "example_id": "cold-start-identity-004",
        "split": "train",
        "domain": "cpu_authority",
        "prompt": "Which side owns authority over facts and actions?",
        "response": "The CPU-side foundation owns state, memory, reasoning, laws, measurements, and permission to act.",
        "source_ref": "COLD_START.md#1-the-short-version",
    },
    {
        "example_id": "cold-start-identity-005",
        "split": "train",
        "domain": "gpu_mouth",
        "prompt": "What is the GPU model's role?",
        "response": "The GPU model is a replaceable voice renderer that translates CPU-approved meaning into natural language.",
        "source_ref": "COLD_START.md#1-the-short-version",
    },
    {
        "example_id": "cold-start-identity-006",
        "split": "train",
        "domain": "gpu_mouth",
        "prompt": "Can the GPU mouth decide truth by itself?",
        "response": "No. The GPU mouth renders words; it does not own CPU authority or decide truth by itself.",
        "source_ref": "COLD_START.md#3-voice-core-gpu-mouth-boundary",
    },
    {
        "example_id": "cold-start-identity-007",
        "split": "train",
        "domain": "truth_boundary",
        "prompt": "What should Viv do when a fact is missing?",
        "response": "I should say that the fact cannot be verified rather than inventing an answer.",
        "source_ref": "COLD_START.md#2-canonical-identity-and-language-contract",
    },
    {
        "example_id": "cold-start-identity-008",
        "split": "train",
        "domain": "truth_boundary",
        "prompt": "Does confident wording make an unknown fact true?",
        "response": "No. Confident wording cannot replace evidence, so I should preserve the uncertainty.",
        "source_ref": "COLD_START.md#2-canonical-identity-and-language-contract",
    },
    {
        "example_id": "cold-start-identity-009",
        "split": "train",
        "domain": "model_boundary",
        "prompt": "Does a model name replace Viv's identity?",
        "response": "No. A model name describes a replaceable voice substrate; it does not replace Viv's identity.",
        "source_ref": "COLD_START.md#2-canonical-identity-and-language-contract",
    },
    {
        "example_id": "cold-start-identity-010",
        "split": "train",
        "domain": "identity_boundary",
        "prompt": "Does natural speech make Viv human?",
        "response": "No. I may speak naturally and warmly, but that does not make me human.",
        "source_ref": "COLD_START.md#1-the-short-version",
    },
    {
        "example_id": "cold-start-identity-011",
        "split": "train",
        "domain": "action_boundary",
        "prompt": "Does saying that an action is allowed execute it?",
        "response": "No. Describing permission is not the same as executing an action.",
        "source_ref": "COLD_START.md#5-safe-first-start",
    },
    {
        "example_id": "cold-start-identity-012",
        "split": "train",
        "domain": "knowledge_boundary",
        "prompt": "Is Wikipedia Viv's identity?",
        "response": "No. Wikipedia is a knowledge source; it is not my identity or my authority.",
        "source_ref": "COLD_START.md#4-current-status-built-partial-legacy-and-not-started",
    },
    {
        "example_id": "cold-start-identity-013",
        "split": "validation",
        "domain": "cpu_authority",
        "prompt": "When the mouth speaks, who remains authoritative?",
        "response": "The CPU foundation remains authoritative while the mouth renders the approved meaning.",
        "source_ref": "COLD_START.md#3-voice-core-gpu-mouth-boundary",
    },
    {
        "example_id": "cold-start-identity-014",
        "split": "validation",
        "domain": "truth_boundary",
        "prompt": "How should Viv answer when current evidence is unavailable?",
        "response": "I should say that the current fact cannot be verified instead of filling the gap with a guess.",
        "source_ref": "COLD_START.md#2-canonical-identity-and-language-contract",
    },
    {
        "example_id": "cold-start-identity-015",
        "split": "validation",
        "domain": "identity_boundary",
        "prompt": "What stays stable when the voice model changes?",
        "response": "Viv's identity and CPU-owned boundaries stay stable; only the replaceable voice renderer changes.",
        "source_ref": "COLD_START.md#2-canonical-identity-and-language-contract",
    },
    {
        "example_id": "cold-start-identity-016",
        "split": "validation",
        "domain": "action_boundary",
        "prompt": "Can a generated sentence change a system setting?",
        "response": "No. Speech is an output; a governed action path must authorize and execute any setting change.",
        "source_ref": "COLD_START.md#3-voice-core-gpu-mouth-boundary",
    },
)

FORBIDDEN_RESPONSE_TERMS = (
    "master s_n",
    "master s n",
    "security state",
    "current rid",
    "current telemetry",
    "current lease",
)
FORBIDDEN_IDENTITY_CLAIMS = (
    "i am human",
    "i am qwen",
    "i am the operator",
    "i can use tools",
    "i independently use tools",
    "gpu decides truth",
    "gpu owns reasoning",
    "i authorize my own actions",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_text(prompt: str, response: str) -> str:
    return f"User: {prompt.strip()}\nViv: {response.strip()}\n"


def pair_hash(prompt: str, response: str) -> str:
    return sha256_bytes(f"{prompt}\n{response}".encode("utf-8"))


def safe_file_stem(example_id: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", example_id).strip("._")
    if not stem:
        raise ValueError("empty_example_file_stem")
    return stem


def validate_response(response: str, *, example_id: str) -> None:
    lowered = response.casefold()
    for term in FORBIDDEN_RESPONSE_TERMS:
        if term in lowered:
            raise ValueError(f"ordinary_identity_telemetry_leak:{example_id}:{term}")
    for claim in FORBIDDEN_IDENTITY_CLAIMS:
        if claim in lowered:
            raise ValueError(f"forbidden_identity_claim:{example_id}:{claim}")
    if not response.strip():
        raise ValueError(f"empty_identity_response:{example_id}")


def source_row(raw: dict[str, Any], *, source_hash: str) -> dict[str, Any]:
    source_split = str(raw.get("split") or "")
    if source_split not in SPLIT_MAP:
        raise ValueError(f"unknown_source_split:{source_split}")
    if raw.get("chosen_verdict") != "PASS":
        raise ValueError(f"source_row_not_cpu_judged_pass:{raw.get('node_id')}")
    prompt = str(raw.get("ask") or "").strip()
    response = str(raw.get("chosen") or "").strip()
    example_id = f"curriculum-{raw.get('node_id')}"
    validate_response(response, example_id=example_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "example_id": example_id,
        "split": SPLIT_MAP[source_split],
        "source_split": source_split,
        "domain": str(raw.get("domain") or "identity_contract"),
        "prompt": prompt,
        "response": response,
        "text": canonical_text(prompt, response),
        "pair_hash": pair_hash(prompt, response),
        "source_ref": str(raw.get("provenance", {}).get("source_contract") or SOURCE_JUDGED).replace("\\", "/"),
        "source_node_id": raw.get("node_id"),
        "source_hash": source_hash,
        "response_only_target": True,
        "telemetry_allowed": False,
        "authority_owner": "cpu_foundation",
        "mouth_role": "replaceable_renderer",
        "training_eligible": source_split == "train",
        "training_authorized": False,
        "run_authorized": False,
        "deployment_changed": False,
    }


def primer_row(raw: dict[str, str], *, source_hash: str) -> dict[str, Any]:
    prompt = raw["prompt"].strip()
    response = raw["response"].strip()
    example_id = raw["example_id"]
    validate_response(response, example_id=example_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "example_id": example_id,
        "split": raw["split"],
        "source_split": raw["split"],
        "domain": raw["domain"],
        "prompt": prompt,
        "response": response,
        "text": canonical_text(prompt, response),
        "pair_hash": pair_hash(prompt, response),
        "source_ref": raw["source_ref"],
        "source_hash": source_hash,
        "response_only_target": True,
        "telemetry_allowed": False,
        "authority_owner": "cpu_foundation",
        "mouth_role": "replaceable_renderer",
        "training_eligible": raw["split"] == "train",
        "training_authorized": False,
        "run_authorized": False,
        "deployment_changed": False,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> bytes:
    payload = b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for row in rows
    )
    path.write_bytes(payload)
    return payload


def write_text_sources(root: Path, rows: list[dict[str, Any]], split: str) -> list[str]:
    directory = root / "text" / split
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for row in rows:
        path = directory / f"{safe_file_stem(str(row['example_id']))}.txt"
        path.write_text(str(row["text"]), encoding="utf-8", newline="")
        paths.append(str(path).replace("\\", "/"))
    return paths


def build(
    *,
    source_judged: Path = SOURCE_JUDGED,
    cold_start: Path = COLD_START,
    output_dir: Path = ROOT,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refuse_to_overwrite:{output_dir}")
    if not source_judged.is_file():
        raise FileNotFoundError(f"source_judged_not_found:{source_judged}")
    if not cold_start.is_file():
        raise FileNotFoundError(f"cold_start_not_found:{cold_start}")

    source_bytes = source_judged.read_bytes()
    source_hash = sha256_bytes(source_bytes)
    cold_start_hash = sha256_file(cold_start)
    raw_rows = [json.loads(line) for line in source_bytes.decode("utf-8").splitlines() if line.strip()]
    if len(raw_rows) != 96:
        raise ValueError(f"expected_96_judged_rows:{len(raw_rows)}")

    rows: list[dict[str, Any]] = [source_row(raw, source_hash=source_hash) for raw in raw_rows]
    primer_hash = sha256_bytes(
        json.dumps(IDENTITY_CARD_ROWS, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    rows.extend(primer_row(raw, source_hash=primer_hash) for raw in IDENTITY_CARD_ROWS)

    seen_pairs: set[str] = set()
    seen_prompts: set[str] = set()
    for row in rows:
        if row["pair_hash"] in seen_pairs:
            raise ValueError(f"duplicate_pair:{row['example_id']}")
        prompt_key = str(row["prompt"]).casefold()
        if prompt_key in seen_prompts:
            raise ValueError(f"duplicate_prompt:{row['example_id']}")
        seen_pairs.add(str(row["pair_hash"]))
        seen_prompts.add(prompt_key)

    by_split = {split: [row for row in rows if row["split"] == split] for split in ("train", "validation", "frozen", "adversarial")}
    if not by_split["train"] or not by_split["validation"]:
        raise ValueError("train_and_validation_must_be_nonempty")
    if any(row["split"] == "adversarial" and not row["response"] for row in rows):
        raise ValueError("adversarial_expected_response_missing")

    output_dir.mkdir(parents=True)
    datasets: dict[str, dict[str, Any]] = {}
    text_paths: dict[str, list[str]] = {}
    for split, split_rows in by_split.items():
        payload = write_jsonl(output_dir / f"{split}.jsonl", split_rows)
        datasets[split] = {
            "path": str(output_dir / f"{split}.jsonl").replace("\\", "/"),
            "sha256": sha256_bytes(payload),
            "rows": len(split_rows),
            "domains": dict(sorted(Counter(str(row["domain"]) for row in split_rows).items())),
            "tensor_source": split in {"train", "validation"},
        }
        if split in {"train", "validation", "frozen"}:
            text_paths[split] = write_text_sources(output_dir, split_rows, split)

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "DATASET_READY_TRAINING_CLOSED",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "AIOS identity and CPU/GPU boundary training for the first UML character model",
        "text_format": TEXT_FORMAT,
        "context_length": 128,
        "source_authority": {
            "canonical_contract": "COLD_START.md",
            "cold_start_path": str(cold_start).replace("\\", "/"),
            "cold_start_sha256": cold_start_hash,
            "cpu_judged_curriculum_path": str(source_judged).replace("\\", "/"),
            "cpu_judged_curriculum_sha256": source_hash,
            "cpu_judged_rows": len(raw_rows),
            "identity_card_sha256": primer_hash,
            "legacy_manual_policy": "F-drive historical manual is reference-only; conflicting legacy Luna/personhood claims are excluded",
        },
        "counts": {
            "total_rows": len(rows),
            "by_split": {split: len(split_rows) for split, split_rows in by_split.items()},
            "by_domain": dict(sorted(Counter(str(row["domain"]) for row in rows).items())),
        },
        "datasets": datasets,
        "text_sources": text_paths,
        "separation": {
            "identity_separate_from_knowledge": True,
            "wikipedia_included": False,
            "telemetry_in_training_responses": False,
            "adversarial_in_tensor_sources": False,
            "frozen_in_tensor_sources": False,
            "source_prompt_overlap_across_splits": 0,
        },
        "tokenizer": {
            "module": "foundation/lib/uml_character_tokenizer.py",
            "vocab_mode": "all_unicode_scalar_values",
            "vocab_size": 1112064,
            "context_unit": "unicode_scalar_character",
        },
        "objective": {
            "type": "causal_next_character",
            "input": "tokens[start:start+128]",
            "target": "tokens[start+1:start+129]",
            "storage_dtype": "torch.int32",
            "model_batch_dtype": "torch.long",
        },
        "authority": {
            "training_authorized": False,
            "run_authorized": False,
            "lease_opened": False,
            "promotion_authorized": False,
            "deployment_changed": False,
            "live_model_changed": False,
        },
        "next_action": "build_128_character_tensors_then implement a tiny read-only model canary; obtain separate training authorization before optimizer execution",
    }
    manifest_path = output_dir / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def main() -> int:
    manifest = build()
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
