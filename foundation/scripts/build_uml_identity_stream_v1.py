#!/usr/bin/env python3
"""Assemble disjoint UML identity rows into contiguous causal text streams.

The per-row text files preserve provenance and boundary isolation.  A
character language model also needs a stream representation so short rows are
not silently excluded just because they are shorter than one 128-character
window.  This builder joins only rows from the same split with an explicit
blank-line separator and refuses to overwrite its output.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
DATASET_ROOT = FOUNDATION / "artifacts/auto/uml/identity_contract_dataset_v1"
ROOT = DATASET_ROOT / "stream_v1"
SCHEMA_VERSION = "uml_identity_stream_v1"
STREAM_SPLITS = ("train", "validation", "frozen")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_rows(split: str) -> list[dict[str, Any]]:
    path = DATASET_ROOT / f"{split}.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"dataset_split_not_found:{path}")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(row.get("split") != split for row in rows):
        raise ValueError(f"split_field_mismatch:{split}")
    return rows


def stream_text(rows: list[dict[str, Any]]) -> str:
    if not rows:
        raise ValueError("empty_stream_rows")
    # Each row already ends in one newline.  Add one explicit blank-line
    # separator; this is part of the training text and is hash recorded.
    return "\n".join(str(row["text"]) for row in rows)


def build(output_dir: Path = ROOT) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refuse_to_overwrite:{output_dir}")
    output_dir.mkdir(parents=True)
    datasets: dict[str, dict[str, Any]] = {}
    for split in STREAM_SPLITS:
        rows = load_rows(split)
        payload = stream_text(rows).encode("utf-8")
        path = output_dir / f"{split}.txt"
        path.write_bytes(payload)
        datasets[split] = {
            "path": str(path).replace("\\", "/"),
            "sha256": sha256_bytes(payload),
            "rows": len(rows),
            "characters": len(payload.decode("utf-8")),
            "row_pair_hashes": [str(row["pair_hash"]) for row in rows],
            "source_jsonl": str((DATASET_ROOT / f"{split}.jsonl")).replace("\\", "/"),
            "source_jsonl_sha256": sha256_bytes((DATASET_ROOT / f"{split}.jsonl").read_bytes()),
        }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE_TRAINING_CLOSED",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_root": str(DATASET_ROOT).replace("\\", "/"),
        "separator": "one_blank_line_between_rows",
        "window_policy": {
            "context_length": 128,
            "stride": 1,
            "objective": "causal_next_character",
            "coverage": "every character position with a following target is eligible",
        },
        "datasets": datasets,
        "adversarial_included": False,
        "wikipedia_included": False,
        "identity_separate_from_knowledge": True,
        "authority": {
            "training_authorized": False,
            "run_authorized": False,
            "lease_opened": False,
            "promotion_authorized": False,
            "deployment_changed": False,
            "live_model_changed": False,
        },
        "next_action": "convert train.txt and validation.txt with build_uml_char_tensor_dataset_v1.py; do not start optimizer execution",
    }
    manifest_path = output_dir / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def main() -> int:
    print(json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
