#!/usr/bin/env python3
"""Read-only preflight for a staged Wikipedia semantic index.

This checks the existing structural index, corpus metadata, and the real local
embedding backend. It never enumerates the full corpus, writes vectors, or
admits CARMA/training data.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.knowledge_external_adapters import (  # noqa: E402
    LEGACY_WIKIPEDIA_INDEX,
    LEGACY_WIKIPEDIA_ROOT,
)
from lib.knowledge_semantic_backend import semantic_compare  # noqa: E402


def _index_probe() -> dict[str, Any]:
    try:
        stat = LEGACY_WIKIPEDIA_INDEX.stat()
        uri = f"file:{LEGACY_WIKIPEDIA_INDEX.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5.0) as conn:
            tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table'")]
            columns = [row[1] for row in conn.execute("pragma table_info(file_index)")]
        required = {"file_name", "full_path", "extension", "size_bytes", "is_dir"}
        return {
            "ok": "file_index" in tables and required.issubset(columns),
            "state": "AVAILABLE" if "file_index" in tables and required.issubset(columns) else "INVALID_SCHEMA",
            "path": str(LEGACY_WIKIPEDIA_INDEX),
            "bytes": stat.st_size,
            "mode": "sqlite_read_only",
            "tables": tables,
            "columns": columns,
        }
    except (OSError, sqlite3.Error) as exc:
        return {
            "ok": False,
            "state": "INCONCLUSIVE",
            "path": str(LEGACY_WIKIPEDIA_INDEX),
            "error": f"{type(exc).__name__}:{exc}",
        }


def _corpus_probe() -> dict[str, Any]:
    metadata_path = LEGACY_WIKIPEDIA_ROOT / "deduplication_metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        return {
            "ok": LEGACY_WIKIPEDIA_ROOT.is_dir() and bool(metadata.get("processing_completed")),
            "state": "AVAILABLE" if LEGACY_WIKIPEDIA_ROOT.is_dir() else "MISSING",
            "root": str(LEGACY_WIKIPEDIA_ROOT),
            "metadata_path": str(metadata_path),
            "articles": metadata.get("total_articles_processed"),
            "batches": metadata.get("batches_created"),
            "processing_completed": metadata.get("processing_completed"),
        }
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        return {
            "ok": False,
            "state": "INCONCLUSIVE",
            "root": str(LEGACY_WIKIPEDIA_ROOT),
            "metadata_path": str(metadata_path),
            "error": f"{type(exc).__name__}:{exc}",
        }


def preflight(*, timeout_s: float = 5.0) -> dict[str, Any]:
    index = _index_probe()
    corpus = _corpus_probe()
    embedding = semantic_compare(
        "Anarchism is a political philosophy.",
        "A political philosophy concerns ideas about authority and society.",
        timeout_s=timeout_s,
    )
    checks = {
        "index": bool(index.get("ok")),
        "corpus": bool(corpus.get("ok")),
        "embedding": bool(embedding.get("ok")),
    }
    ready = all(checks.values())
    return {
        "ok": ready,
        "state": "READY_FOR_STAGED_BUILD" if ready else "BLOCKED_EMBEDDING_BACKEND" if not checks["embedding"] else "BLOCKED_SOURCE_CONTRACT",
        "checks": checks,
        "index": index,
        "corpus": corpus,
        "embedding": embedding,
        "writes_performed": False,
        "training_authorized": False,
        "carma_admission": False,
        "next_action": "Provide a real local embedding endpoint, then rerun this read-only preflight." if not checks["embedding"] else "Create an immutable staged source manifest before bounded ingestion.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-s", type=float, default=5.0)
    args = parser.parse_args()
    print(json.dumps(preflight(timeout_s=max(0.5, args.timeout_s)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
