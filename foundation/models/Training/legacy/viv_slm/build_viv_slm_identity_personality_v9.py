#!/usr/bin/env python3
"""Build v9 with registry-compliant CPU mouth response targets.

The v8 corpus is retained unchanged. This lane applies the existing CPU
acronym registry to response targets only, so the renderer is trained toward
the same first-use forms that the mouth contract accepts. Prompts, splits,
provenance, identity scope, and external-knowledge policy remain bounded.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for path in (FOUNDATION, VIV_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from build_viv_slm_identity_personality_v1 import RESERVED_ASCII, _json_write, _sha256  # noqa: E402
from build_viv_slm_identity_personality_v2 import _read_jsonl, _row, _write_jsonl, _write_stream  # noqa: E402
from voice_core.acronym_registry import repair_acronym_usage, validate_acronym_usage  # noqa: E402


PARENT_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v8"
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v9"
TERMINATION_MARKER = "<END>"
SCHEMA_VERSION = "viv_slm_identity_personality_dataset_v9"
REPAIR_SOURCE = "viv_identity_personality_acronym_repair_pack_v9"


def _parent_rows() -> list[dict[str, Any]]:
    return [
        row
        for split in ("train", "validation", "frozen", "adversarial")
        for row in _read_jsonl(PARENT_ROOT / f"{split}.jsonl")
    ]


def _repaired_rows(parent_hash: str) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    changed = 0
    for original in _parent_rows():
        response = str(original.get("response") or "").strip()
        repaired_record = repair_acronym_usage(response)
        repaired = str(repaired_record.get("repaired") or response).strip()
        if validate_acronym_usage(repaired):
            raise ValueError(f"viv_slm_v9_acronym_repair_incomplete:{original.get('example_id')}")
        changed += int(repaired != response)
        row = _row(
            example_id=f"v9-{original['example_id']}",
            prompt=str(original.get("prompt") or "").strip(),
            response=repaired,
            split=str(original["split"]),
            source=REPAIR_SOURCE,
            source_hash=parent_hash,
            hold_only=bool(original.get("hold_only")),
            optimizer_eligible=bool(original.get("optimizer_eligible")),
        )
        row["parent_example_id"] = str(original.get("example_id") or "")
        row["parent_source"] = str(original.get("source") or "")
        row["acronym_repair_kinds"] = [str(item.get("kind")) for item in repaired_record.get("repairs") or () if isinstance(item, dict)]
        rows.append(row)
    return rows, changed


def build(*, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"viv_slm_v9_output_exists_refuse_overwrite:{output_dir}")
    parent_manifest_path = PARENT_ROOT / "MANIFEST.json"
    parent_vocab_path = PARENT_ROOT / "VOCAB.json"
    if not parent_manifest_path.is_file() or not parent_vocab_path.is_file():
        raise FileNotFoundError("viv_slm_v9_parent_artifacts_missing")
    parent_hash = _sha256(parent_manifest_path)
    rows, changed = _repaired_rows(parent_hash)
    by_split = {
        split: [row for row in rows if row["split"] == split]
        for split in ("train", "validation", "frozen", "adversarial")
    }
    expected = {"train": 310, "validation": 48, "frozen": 21, "adversarial": 21}
    if {key: len(value) for key, value in by_split.items()} != expected:
        raise ValueError("viv_slm_v9_split_count_contract")
    if len(rows) != 400:
        raise ValueError("viv_slm_v9_row_total_contract")
    if changed <= 0:
        raise ValueError("viv_slm_v9_expected_acronym_repairs_missing")
    if any(row["termination_marker"] not in row["text"] for row in rows):
        raise ValueError("viv_slm_v9_termination_marker_missing")
    if any(row["training_authorized"] is not False for row in rows):
        raise ValueError("viv_slm_v9_training_authority_violation")
    if any("master s_n" in str(row["response"]).casefold() or "rid=" in str(row["response"]).casefold() for row in rows):
        raise ValueError("viv_slm_v9_telemetry_response_present")

    source_records = [
        {"path": str(parent_manifest_path).replace("\\", "/"), "sha256": parent_hash},
        {"path": str(parent_vocab_path).replace("\\", "/"), "sha256": _sha256(parent_vocab_path)},
        {"path": "voice_core/acronym_registry.py", "sha256": _sha256(VIV_ROOT / "voice_core" / "acronym_registry.py")},
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
        raise ValueError(f"viv_slm_v9_vocab_size_changed:{len(vocab)}")
    vocab_manifest = {
        "schema_version": "viv_slm_character_vocab_v9",
        "token_unit": "corpus_character",
        "vocab_mode": "identity_personality_acronym_safe_plus_reserved_ascii",
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
        "purpose": "identity_personality_acronym_safe_renderer_training_before_world_knowledge",
        "source_policy": "v8_rows_with_cpu_acronym_registry_response_normalization",
        "parent_dataset_manifest": str(parent_manifest_path).replace("\\", "/"),
        "parent_dataset_manifest_sha256": parent_hash,
        "repair_source": REPAIR_SOURCE,
        "rows_changed_by_repair": changed,
        "acronym_policy": "registry_validate_acronym_usage_empty_after_repair",
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
                "status": "VIV_SLM_IDENTITY_PERSONALITY_V9_PASS",
                "output_dir": str(args.output_dir).replace("\\", "/"),
                "row_counts": manifest["row_counts"],
                "row_total": manifest["row_total"],
                "rows_changed_by_repair": manifest["rows_changed_by_repair"],
                "vocab_size": manifest["vocab_size"],
                "world_knowledge_included": manifest["world_knowledge_included"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
