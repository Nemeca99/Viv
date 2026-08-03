#!/usr/bin/env python3
"""Check exact staged Wikipedia text overlap against a governed train/holdout set.

This is intentionally narrower than semantic deduplication: a zero result proves
no exact normalized chunk/field match, while semantic overlap remains explicit
UNASSESSED. The command is read-only apart from its timestamped evidence output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.triad_kernel import TRIAD_CONTRACT_VERSION  # noqa: E402


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_jsonl(path: Path) -> tuple[list[dict], set[str]]:
    rows: list[dict] = []
    fields: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows.append(row)
        fields.update(_norm(value) for value in row.values() if isinstance(value, (str, int, float, bool)))
    return rows, fields


def validate(artifacts: list[Path], train_path: Path, holdout_path: Path) -> dict:
    train_rows, train_fields = _load_jsonl(train_path)
    holdout_rows, holdout_fields = _load_jsonl(holdout_path)
    reference_fields = train_fields | holdout_fields
    chunks: set[str] = set()
    source_paths: set[str] = set()
    artifact_hashes = []
    for artifact_path in artifacts:
        artifact_hashes.append({"path": str(artifact_path), "sha256": _sha256(artifact_path)})
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        if artifact.get("state") != "VERIFIED":
            raise ValueError(f"artifact_not_verified:{artifact_path}")
        for row in artifact.get("rows", []):
            path = Path(str(row["path"]))
            source_paths.add(str(path).casefold())
            text = path.read_text(encoding="utf-8", errors="replace")[:12000]
            chunks.add(_norm(text[:2048]))
    exact_matches = sorted(chunk for chunk in chunks if chunk and chunk in reference_fields)
    return {
        "schema_version": "wikipedia_training_disjointness_v1",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "triad_contract_version": TRIAD_CONTRACT_VERSION,
        "state": "VERIFIED" if not exact_matches else "HOLD",
        "artifact_hashes": artifact_hashes,
        "staged_unique_paths": len(source_paths),
        "staged_unique_chunks": len(chunks),
        "train_rows": len(train_rows),
        "holdout_rows": len(holdout_rows),
        "exact_normalized_chunk_field_overlap": len(exact_matches),
        "exact_overlap_examples": exact_matches[:3],
        "semantic_overlap": "UNASSESSED",
        "interpretation": "VERIFIED exact normalized chunk/field disjointness only; semantic or paraphrase overlap requires a separate approved evaluator.",
        "authority": {
            "vector_index_written": False,
            "carma_admission": False,
            "training_authorized": False,
            "run_authorized": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, action="append", required=True)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = validate(args.artifact, args.train, args.holdout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["state"] == "VERIFIED", "state": result["state"], "exact_overlap": result["exact_normalized_chunk_field_overlap"], "semantic_overlap": result["semantic_overlap"], "output": str(args.output)}, indent=2))
    return 0 if result["state"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
