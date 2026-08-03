#!/usr/bin/env python3
"""Build a bounded, hash-bearing lexical Wikipedia retrieval baseline.

This is a source and retrieval canary only. It does not create embeddings,
write a vector index, admit CARMA records, or authorize training.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.knowledge_external_adapters import query_legacy_wikipedia  # noqa: E402


DEFAULT_QUERIES = ("Anarchism", "Artificial intelligence", "Transformer")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash_file(path: Path, *, max_bytes: int = 4096) -> tuple[str, int]:
    digest = hashlib.sha256()
    read_bytes = 0
    with path.open("rb") as handle:
        while read_bytes < max_bytes:
            chunk = handle.read(min(1024 * 1024, max_bytes - read_bytes))
            if not chunk:
                break
            digest.update(chunk)
            read_bytes += len(chunk)
    return digest.hexdigest(), read_bytes


def build_canary(queries: tuple[str, ...], *, limit: int, max_chars: int) -> dict:
    rows = []
    for query in queries:
        result = query_legacy_wikipedia(query, limit=limit, max_chars=max_chars)
        facts = result.get("facts", []) if isinstance(result, dict) else []
        sources = []
        for fact in facts:
            source = fact.get("source", {}) if isinstance(fact, dict) else {}
            path_text = source.get("path") if isinstance(source, dict) else None
            if not path_text:
                continue
            path = Path(path_text)
            if not path.is_file():
                continue
            prefix_hash, prefix_bytes = _hash_file(path)
            sources.append(
                {
                    "claim": fact.get("claim"),
                    "path": str(path),
                    "source_sha256": source.get("sha256"),
                    "source_bytes": source.get("bytes"),
                    "observed_prefix_sha256": prefix_hash,
                    "observed_prefix_bytes": prefix_bytes,
                    "content_prefix": str(fact.get("value", ""))[:max_chars],
                }
            )
        rows.append(
            {
                "query": query,
                "state": result.get("state", "INCONCLUSIVE"),
                "mode": result.get("mode"),
                "candidate_rows": result.get("candidate_rows", 0),
                "errors": result.get("errors", []),
                "sources": sources,
            }
        )
    verified = sum(1 for row in rows for source in row["sources"] if source.get("source_sha256"))
    return {
        "schema_version": "wikipedia_lexical_canary_v1",
        "created_utc": _utc_now(),
        "state": "VERIFIED" if verified else "INCONCLUSIVE",
        "semantic_state": "BLOCKED_EMBEDDING_BACKEND",
        "scope": {
            "queries": list(queries),
            "limit_per_query": limit,
            "max_chars_per_article": max_chars,
            "source_root": r"F:\AI_Datasets\wikipedia_deduplicated",
            "index_mode": "sqlite_read_only_structural_index",
        },
        "writes_performed": True,
        "vector_index_written": False,
        "carma_admission": False,
        "training_authorized": False,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--max-chars", type=int, default=2048)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 5 or args.max_chars < 128 or args.max_chars > 8192:
        raise SystemExit("bounded limits are invalid")
    payload = build_canary(DEFAULT_QUERIES, limit=args.limit, max_chars=args.max_chars)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": payload["state"] == "VERIFIED", "state": payload["state"], "output": str(args.output), "verified_sources": sum(len(row["sources"]) for row in payload["rows"]), "semantic_state": payload["semantic_state"], "vector_index_written": False}, indent=2))
    return 0 if payload["state"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
