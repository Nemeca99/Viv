#!/usr/bin/env python3
"""Build a resumable, provenance-preserving Wikipedia title sidecar index.

The recovered SQLite database is read-only and has no title/FTS index.  This
builder derives title keys from the existing six-digit-prefix filename
contract without changing that database or the F: corpus.  The runtime must
still verify the source file's Title header, redirect state, containment, and
hash before returning knowledge.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SOURCE_INDEX = Path(r"D:\LocalAi\5126\FSAA\Luna\AIOS_V2\dataset_core\global_index.db")
SOURCE_ROOT = r"F:\AI_Datasets\wikipedia_deduplicated"
NAME_RE = re.compile(r"^(?P<prefix>[0-9]{6})_(?P<title>.+)\.txt$", re.IGNORECASE)
SCHEMA = "wikipedia_title_index_v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def source_identity() -> dict[str, object]:
    stat = SOURCE_INDEX.stat()
    return {
        "path": str(SOURCE_INDEX),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "mode": "read_only",
        "root": SOURCE_ROOT,
    }


def initialize(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(output) as db:
        db.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS titles (
                title_key TEXT NOT NULL,
                title TEXT NOT NULL,
                full_path TEXT NOT NULL,
                indexed_bytes INTEGER NOT NULL,
                source_rowid INTEGER NOT NULL,
                PRIMARY KEY (title_key, full_path)
            );
            CREATE INDEX IF NOT EXISTS idx_titles_key ON titles(title_key);
            CREATE INDEX IF NOT EXISTS idx_titles_path ON titles(full_path);
            """
        )
        defaults = {
            "schema_version": SCHEMA,
            "state": "CHECKPOINT",
            "created_utc": utc_now(),
            "updated_utc": utc_now(),
            "source_index": json.dumps(source_identity(), sort_keys=True),
            "source_root": SOURCE_ROOT,
            "last_source_rowid": "0",
            "source_rows_seen": "0",
            "titles_admitted": "0",
            "malformed_rows": "0",
        }
        db.executemany("INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)", defaults.items())
        db.commit()


def meta_get(db: sqlite3.Connection, key: str, default: str = "") -> str:
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return str(row[0]) if row else default


def meta_set(db: sqlite3.Connection, key: str, value: object) -> None:
    db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, str(value)))


def build(output: Path, *, max_rows: int, batch_size: int) -> dict[str, object]:
    if not SOURCE_INDEX.is_file():
        raise FileNotFoundError(SOURCE_INDEX)
    initialize(output)
    source = source_identity()
    with sqlite3.connect(output) as sidecar:
        prior_source = json.loads(meta_get(sidecar, "source_index", "{}"))
        if prior_source != source:
            raise RuntimeError("source_index_identity_changed")
        last_rowid = int(meta_get(sidecar, "last_source_rowid", "0"))
        seen = int(meta_get(sidecar, "source_rows_seen", "0"))
        admitted = int(meta_get(sidecar, "titles_admitted", "0"))
        malformed = int(meta_get(sidecar, "malformed_rows", "0"))
        sidecar.execute("PRAGMA busy_timeout=5000")
        with sqlite3.connect(f"file:{SOURCE_INDEX.as_posix()}?mode=ro", uri=True, timeout=10.0) as source_db:
            source_db.execute("PRAGMA query_only=ON")
            while max_rows <= 0 or seen < max_rows:
                remaining = batch_size if max_rows <= 0 else min(batch_size, max_rows - seen)
                rows = source_db.execute(
                    "SELECT rowid, file_name, full_path, size_bytes "
                    "FROM file_index WHERE rowid > ? AND full_path LIKE ? "
                    "AND extension='.txt' AND is_dir=0 ORDER BY rowid LIMIT ?",
                    (last_rowid, SOURCE_ROOT.replace("/", "\\") + "\\%", remaining),
                ).fetchall()
                if not rows:
                    meta_set(sidecar, "state", "COMPLETE")
                    break
                inserts: list[tuple[str, str, str, int, int]] = []
                for rowid, raw_name, raw_path, indexed_bytes in rows:
                    last_rowid = int(rowid)
                    seen += 1
                    name = Path(str(raw_name)).name
                    match = NAME_RE.match(name)
                    path = str(raw_path)
                    if not match or not path.casefold().startswith(SOURCE_ROOT.casefold() + "\\"):
                        malformed += 1
                        continue
                    title = match.group("title")
                    inserts.append((title.casefold(), title, path, int(indexed_bytes or 0), int(rowid)))
                before_changes = sidecar.total_changes
                sidecar.executemany(
                    "INSERT OR IGNORE INTO titles(title_key,title,full_path,indexed_bytes,source_rowid) "
                    "VALUES (?,?,?,?,?)",
                    inserts,
                )
                admitted += sidecar.total_changes - before_changes
                meta_set(sidecar, "last_source_rowid", last_rowid)
                meta_set(sidecar, "source_rows_seen", seen)
                meta_set(sidecar, "titles_admitted", admitted)
                meta_set(sidecar, "malformed_rows", malformed)
                meta_set(sidecar, "updated_utc", utc_now())
                sidecar.commit()
                if len(rows) < remaining:
                    meta_set(sidecar, "state", "COMPLETE")
                    sidecar.commit()
                    break
        # Recompute rather than trusting an in-memory delta: a resumable
        # process may be interrupted between a title batch and its metadata
        # update. The table count is the authoritative checkpoint measure.
        actual_admitted = int(sidecar.execute("SELECT COUNT(*) FROM titles").fetchone()[0])
        meta_set(sidecar, "titles_admitted", actual_admitted)
        meta_set(sidecar, "updated_utc", utc_now())
        sidecar.commit()
    with sqlite3.connect(output) as db:
        state = meta_get(db, "state", "CHECKPOINT")
        return {
            "ok": state in {"CHECKPOINT", "COMPLETE"},
            "schema_version": SCHEMA,
            "state": state,
            "output": str(output),
            "source_index": source,
            "last_source_rowid": int(meta_get(db, "last_source_rowid", "0")),
            "source_rows_seen": int(meta_get(db, "source_rows_seen", "0")),
            "titles_admitted": int(meta_get(db, "titles_admitted", "0")),
            "malformed_rows": int(meta_get(db, "malformed_rows", "0")),
            "authority": {
                "read_only_source_index": True,
                "source_tree_changed": False,
                "sqlite_index_changed": False,
                "derived_index_only": True,
                "vector_index_written": False,
                "carma_admission": False,
                "training_authorized": False,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-rows", type=int, default=100_000, help="0 means continue to end")
    parser.add_argument("--batch-size", type=int, default=5_000)
    args = parser.parse_args()
    if args.max_rows < 0 or args.batch_size < 1:
        raise SystemExit("invalid_bound")
    result = build(args.output, max_rows=args.max_rows, batch_size=args.batch_size)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
