#!/usr/bin/env python3
"""Create a read-only, authority-closed plan for staged Wikipedia ingestion."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


INDEX = Path(r"D:\LocalAi\5126\FSAA\Luna\AIOS_V2\dataset_core\global_index.db")
ROOT = Path(r"F:\AI_Datasets\wikipedia_deduplicated")
METADATA = ROOT / "deduplication_metadata.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_plan(*, model_path: Path) -> dict:
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    uri = f"file:{INDEX.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10.0) as db:
        rows = db.execute(
            "SELECT extension, COUNT(*), COALESCE(SUM(size_bytes), 0) "
            "FROM file_index WHERE full_path LIKE ? AND is_dir=0 "
            "GROUP BY extension ORDER BY COUNT(*) DESC",
            (r"F:\AI_Datasets\wikipedia_deduplicated\%",),
        ).fetchall()
    by_extension = {
        str(extension): {"count": int(count), "bytes": int(size)}
        for extension, count, size in rows
    }
    article_count = int(by_extension.get(".txt", {}).get("count", 0))
    article_bytes = int(by_extension.get(".txt", {}).get("bytes", 0))
    expected_articles = int(metadata.get("total_articles_processed", 0))
    return {
        "schema_version": "wikipedia_staged_ingestion_plan_v1",
        "created_utc": _utc_now(),
        "state": "READY_FOR_GOVERNED_CANARY" if article_count == expected_articles else "HOLD_SOURCE_COUNT_MISMATCH",
        "source": {
            "root": str(ROOT),
            "metadata_path": str(METADATA),
            "metadata_sha256": _sha256(METADATA),
            "index": str(INDEX),
            "index_mode": "sqlite_read_only",
            "index_bytes": INDEX.stat().st_size,
            "indexed_by_extension": by_extension,
            "article_count": article_count,
            "article_bytes": article_bytes,
            "metadata_article_count": expected_articles,
            "article_count_match": article_count == expected_articles,
        },
        "embedding": {
            "backend": "huggingface_local",
            "model_path": str(model_path),
            "model_sha256": _sha256(model_path / "model.safetensors"),
            "dimensions": 384,
            "local_files_only": True,
        },
        "proposed_stages": [
            {"stage": "manifest", "operation": "enumerate_indexed_txt_paths_and_capture_source_metadata", "writes": "manifest_only"},
            {"stage": "chunk", "operation": "read_bounded_article_text_and_create_deterministic_chunks", "chunk_chars": 2048, "max_article_chars": 12000},
            {"stage": "embed", "operation": "generate_cpu_local_embeddings", "batch_articles": 32, "max_inflight_batches": 1},
            {"stage": "checkpoint", "operation": "atomically_commit_stage_receipt_every_articles", "checkpoint_interval": 1024},
            {"stage": "validate", "operation": "run_disjoint_retrieval_and_provenance_checks_before_any_admission"},
        ],
        "authority": {
            "execution_authorized": False,
            "full_ingestion_started": False,
            "vector_index_written": False,
            "carma_admission": False,
            "training_authorized": False,
        },
        "constraints": [
            "Do not substitute the structural SQLite index for semantic evidence.",
            "Keep source hashes and model hash in every stage receipt.",
            "Keep staged vectors separate from CARMA until disjoint validation passes.",
            "Do not write source files or alter the recovered SQLite index.",
            "Stop on count, hash, path-containment, embedding, or checkpoint mismatch.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not (INDEX.is_file() and ROOT.is_dir() and METADATA.is_file() and (args.model_path / "model.safetensors").is_file()):
        raise SystemExit("required source or local model artifact missing")
    result = build_plan(model_path=args.model_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["state"] == "READY_FOR_GOVERNED_CANARY", "state": result["state"], "article_count": result["source"]["article_count"], "article_bytes": result["source"]["article_bytes"], "output": str(args.output), "execution_authorized": False, "vector_index_written": False, "carma_admission": False, "training_authorized": False}, indent=2))
    return 0 if result["state"] == "READY_FOR_GOVERNED_CANARY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
