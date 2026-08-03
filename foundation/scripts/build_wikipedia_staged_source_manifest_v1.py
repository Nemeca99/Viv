#!/usr/bin/env python3
"""Build an immutable, bounded Wikipedia source manifest before embedding.

The recovered SQLite database is used read-only for deterministic selection.
The manifest is a source checkpoint only: it contains no vectors and grants no
runtime, CARMA, or training authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

INDEX = Path(r"D:\LocalAi\5126\FSAA\Luna\AIOS_V2\dataset_core\global_index.db")
SOURCE_ROOT = Path(r"F:\AI_Datasets\wikipedia_deduplicated").resolve()
METADATA = SOURCE_ROOT / "deduplication_metadata.json"
TITLE_RE = re.compile(r"^\s*Title:\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)
REDIRECT_RE = re.compile(r"^\s*#REDIRECT\s*\[\[(.*?)\]\]", re.IGNORECASE | re.MULTILINE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _contained(path: Path) -> bool:
    try:
        path.resolve().relative_to(SOURCE_ROOT)
        return True
    except ValueError:
        return False


def _inspect(path: Path) -> tuple[str | None, str | None, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    title_match = TITLE_RE.search(text)
    redirect_match = REDIRECT_RE.search(text)
    return (
        title_match.group(1).strip() if title_match else None,
        redirect_match.group(1).strip() if redirect_match else None,
        text,
    )


def build(*, offset: int, limit: int) -> dict:
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    index_stat = INDEX.stat()
    rows: list[dict] = []
    with sqlite3.connect(f"file:{INDEX.as_posix()}?mode=ro", uri=True, timeout=10.0) as db:
        selected = db.execute(
            "SELECT full_path, size_bytes, modified_ts FROM file_index "
            "WHERE full_path LIKE ? AND extension='.txt' AND is_dir=0 "
            "ORDER BY full_path COLLATE NOCASE LIMIT ? OFFSET ?",
            (r"F:\AI_Datasets\wikipedia_deduplicated\%", limit, offset),
        ).fetchall()
        available = int(db.execute(
            "SELECT COUNT(*) FROM file_index WHERE full_path LIKE ? AND extension='.txt' AND is_dir=0",
            (r"F:\AI_Datasets\wikipedia_deduplicated\%",),
        ).fetchone()[0])

    reasons: list[str] = []
    for ordinal, (raw_path, indexed_bytes, modified_ts) in enumerate(selected, start=offset + 1):
        path = Path(str(raw_path))
        contained = _contained(path)
        exists = path.is_file()
        if not contained or not exists:
            reasons.append(f"path_unavailable:{path}")
            rows.append({
                "ordinal": ordinal,
                "path": str(path),
                "contained": contained,
                "exists": exists,
            })
            continue
        title, redirect_target, text = _inspect(path)
        observed_bytes = path.stat().st_size
        if int(indexed_bytes or 0) != observed_bytes:
            reasons.append(f"indexed_observed_bytes_mismatch:{path}")
        if title is None:
            reasons.append(f"title_header_missing:{path}")
        source_hash = _sha256(path)
        rows.append({
            "ordinal": ordinal,
            "path": str(path),
            "contained": True,
            "exists": True,
            "indexed_bytes": int(indexed_bytes or 0),
            "observed_bytes": observed_bytes,
            "indexed_modified_ts": modified_ts,
            "source_sha256": source_hash,
            "title": title,
            "redirect_target": redirect_target,
            "is_redirect": redirect_target is not None,
            "content_chars": len(text),
        })

    state = "VERIFIED" if len(rows) == limit and not reasons else "HOLD"
    return {
        "schema_version": "wikipedia_staged_source_manifest_v1",
        "created_utc": _utc_now(),
        "state": state,
        "source": {
            "root": str(SOURCE_ROOT),
            "metadata_path": str(METADATA),
            "metadata_sha256": _sha256(METADATA),
            "metadata_articles": int(metadata.get("total_articles_processed", 0)),
            "index": str(INDEX),
            "index_mode": "sqlite_read_only",
            "index_bytes": index_stat.st_size,
            "index_modified_ts": index_stat.st_mtime,
            "available_indexed_txt": available,
        },
        "selection": {
            "order": "full_path COLLATE NOCASE",
            "offset": offset,
            "limit": limit,
            "selected": len(rows),
        },
        "rows": rows,
        "authority": {
            "source_tree_changed": False,
            "sqlite_index_changed": False,
            "vectors_written": False,
            "vector_index_written": False,
            "carma_admission": False,
            "training_authorized": False,
            "run_authorized": False,
        },
        "reasons": reasons,
        "next_action": "Embed only this verified manifest batch, then revalidate every source hash and header before staged retrieval evaluation.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=32)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.offset < 0 or args.limit <= 0 or not (INDEX.is_file() and SOURCE_ROOT.is_dir() and METADATA.is_file()):
        raise SystemExit("invalid bounds or required source artifact missing")
    result = build(offset=args.offset, limit=args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["state"] == "VERIFIED", "state": result["state"], "offset": args.offset, "limit": args.limit, "selected": result["selection"]["selected"], "output": str(args.output), "vectors_written": False, "training_authorized": False}, indent=2))
    return 0 if result["state"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
