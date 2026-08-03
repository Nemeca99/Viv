#!/usr/bin/env python3
"""Validate a derived Wikipedia title-index checkpoint without admitting it."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "artifacts" / "auto" / "knowledge" / "wikipedia_title_index_v1_checkpoint_20260803T023000Z.sqlite"
SOURCE_ROOT = Path(r"F:\AI_Datasets\wikipedia_deduplicated").resolve()


def main() -> int:
    if not INDEX.is_file():
        print(json.dumps({"ok": False, "state": "MISSING_CHECKPOINT", "path": str(INDEX)}))
        return 1
    with sqlite3.connect(INDEX) as db:
        meta = dict(db.execute("SELECT key,value FROM meta").fetchall())
        count = int(db.execute("SELECT COUNT(*) FROM titles").fetchone()[0])
        sample = db.execute(
            "SELECT title,title_key,full_path,indexed_bytes FROM titles ORDER BY source_rowid LIMIT 8"
        ).fetchall()
    assert meta["schema_version"] == "wikipedia_title_index_v1"
    assert meta["state"] in {"CHECKPOINT", "COMPLETE"}
    assert int(meta["source_rows_seen"]) >= count
    assert count == int(meta["titles_admitted"])
    assert json.loads(meta["source_index"])["mode"] == "read_only"
    assert all(Path(row[2]).resolve().is_relative_to(SOURCE_ROOT) for row in sample)
    assert all(row[0].casefold() == row[1] for row in sample)
    assert all(int(row[3]) >= 0 for row in sample)
    result = {
        "ok": True,
        "state": meta["state"],
        "rows": count,
        "source_rows_seen": int(meta["source_rows_seen"]),
        "malformed_rows": int(meta["malformed_rows"]),
        "source_index_read_only": json.loads(meta["source_index"])["mode"] == "read_only",
        "runtime_admission": False,
        "training_authorized": False,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
