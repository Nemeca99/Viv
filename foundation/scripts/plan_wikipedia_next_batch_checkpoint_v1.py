#!/usr/bin/env python3
"""Plan the next bounded Wikipedia canary batch without reading or writing vectors."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

INDEX = Path(r"D:\LocalAi\5126\FSAA\Luna\AIOS_V2\dataset_core\global_index.db")
SOURCE_ROOT = Path(r"F:\AI_Datasets\wikipedia_deduplicated").resolve()


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


def plan(*, offset: int, limit: int, prior_validation: Path) -> dict:
    prior_hash = _sha256(prior_validation)
    with sqlite3.connect(f"file:{INDEX.as_posix()}?mode=ro", uri=True, timeout=10.0) as db:
        rows = db.execute(
            "SELECT full_path, size_bytes, modified_ts FROM file_index "
            "WHERE full_path LIKE ? AND extension='.txt' AND is_dir=0 "
            "ORDER BY full_path COLLATE NOCASE LIMIT ? OFFSET ?",
            (r"F:\AI_Datasets\wikipedia_deduplicated\%", limit, offset),
        ).fetchall()
        count = db.execute(
            "SELECT COUNT(*) FROM file_index WHERE full_path LIKE ? AND extension='.txt' AND is_dir=0",
            (r"F:\AI_Datasets\wikipedia_deduplicated\%",),
        ).fetchone()[0]
    preview = []
    for ordinal, (raw_path, indexed_bytes, modified_ts) in enumerate(rows, start=offset + 1):
        path = Path(str(raw_path))
        preview.append(
            {
                "ordinal": ordinal,
                "path": str(path),
                "contained": _contained(path),
                "exists": path.is_file(),
                "indexed_bytes": int(indexed_bytes or 0),
                "observed_bytes": path.stat().st_size if path.is_file() else None,
                "indexed_modified_ts": modified_ts,
            }
        )
    state = "READY_FOR_BOUNDED_CANARY" if len(preview) == limit and all(row["contained"] and row["exists"] for row in preview) else "HOLD_BATCH_PREVIEW"
    return {
        "schema_version": "wikipedia_next_batch_checkpoint_v1",
        "created_utc": _utc_now(),
        "state": state,
        "source_index": str(INDEX),
        "source_root": str(SOURCE_ROOT),
        "selection": {
            "order": "full_path COLLATE NOCASE",
            "offset": offset,
            "limit": limit,
            "available_indexed_txt": int(count),
        },
        "prior_validation_artifact": str(prior_validation),
        "prior_validation_sha256": prior_hash,
        "preview_rows": preview,
        "execution_boundary": {
            "read_only_index": True,
            "source_tree_changed": False,
            "vector_index_written": False,
            "carma_admission": False,
            "training_authorized": False,
            "run_authorized": False,
        },
        "next_action": "Run a separate 32-article staged embedding canary for this offset only, then validate provenance and disjointness before considering any larger batch.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offset", type=int, default=32)
    parser.add_argument("--limit", type=int, default=32)
    parser.add_argument("--prior-validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = plan(offset=args.offset, limit=args.limit, prior_validation=args.prior_validation)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["state"] == "READY_FOR_BOUNDED_CANARY", "state": result["state"], "offset": args.offset, "limit": args.limit, "preview_rows": len(result["preview_rows"]), "output": str(args.output)}, indent=2))
    return 0 if result["state"] == "READY_FOR_BOUNDED_CANARY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
