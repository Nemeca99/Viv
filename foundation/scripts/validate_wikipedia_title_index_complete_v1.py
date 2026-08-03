#!/usr/bin/env python3
"""Validate complete title-sidecar reconciliation and sampled source authority."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_INDEX = Path(r"D:\LocalAi\5126\FSAA\Luna\AIOS_V2\dataset_core\global_index.db")
SOURCE_ROOT = Path(r"F:\AI_Datasets\wikipedia_deduplicated").resolve()
SIDECAR = ROOT / "artifacts" / "auto" / "knowledge" / "wikipedia_title_index_v1_checkpoint_20260803T023000Z.sqlite"
TITLE_RE = re.compile(r"^\s*Title:\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)


def main() -> int:
    source_stat = SOURCE_INDEX.stat()
    with sqlite3.connect(f"file:{SOURCE_INDEX.as_posix()}?mode=ro", uri=True) as source_db:
        source_rows = int(source_db.execute(
            "SELECT COUNT(*) FROM file_index WHERE full_path LIKE ? AND extension='.txt' AND is_dir=0",
            (r"F:\AI_Datasets\wikipedia_deduplicated\%",),
        ).fetchone()[0])
    with sqlite3.connect(SIDECAR) as db:
        meta = dict(db.execute("SELECT key,value FROM meta").fetchall())
        sidecar_rows = int(db.execute("SELECT COUNT(*) FROM titles").fetchone()[0])
        first = db.execute("SELECT title,title_key,full_path,indexed_bytes FROM titles ORDER BY source_rowid LIMIT 512").fetchall()
        last = db.execute("SELECT title,title_key,full_path,indexed_bytes FROM titles ORDER BY source_rowid DESC LIMIT 512").fetchall()
    identity = json.loads(meta["source_index"])
    assert meta["schema_version"] == "wikipedia_title_index_v1"
    assert meta["state"] == "COMPLETE"
    assert identity["path"] == str(SOURCE_INDEX)
    assert int(identity["bytes"]) == source_stat.st_size
    assert int(identity["mtime_ns"]) == source_stat.st_mtime_ns
    assert source_rows - sidecar_rows == int(meta["malformed_rows"])
    assert sidecar_rows == int(meta["titles_admitted"])
    header_mismatch = 0
    bytes_mismatch = 0
    path_bad = 0
    for title, key, raw_path, indexed_bytes in first + last:
        path = Path(raw_path)
        if not path.resolve().is_relative_to(SOURCE_ROOT):
            path_bad += 1
            continue
        if path.stat().st_size != int(indexed_bytes):
            bytes_mismatch += 1
        text = path.read_text(encoding="utf-8", errors="replace")[:12000]
        match = TITLE_RE.search(text)
        if not match or match.group(1).strip().casefold() != str(title).casefold():
            header_mismatch += 1
        assert str(key) == str(title).casefold()
    assert path_bad == 0
    assert bytes_mismatch == 0
    result = {
        "ok": True,
        "state": meta["state"],
        "source_rows": source_rows,
        "sidecar_rows": sidecar_rows,
        "malformed_rows": int(meta["malformed_rows"]),
        "sample_checked": len(first) + len(last),
        "sample_header_mismatch": header_mismatch,
        "candidate_index_verified": True,
        "header_authority_required_at_runtime": True,
        "runtime_admission": False,
        "training_authorized": False,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
