#!/usr/bin/env python3
"""Run a bounded staged Wikipedia embedding canary without admission."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.knowledge_semantic_backend import _local_embedding  # noqa: E402

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


def _manifest_rows(manifest_path: Path, *, limit: int, offset: int) -> tuple[list[tuple], dict]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"source_manifest_read_failed:{type(exc).__name__}") from exc
    if manifest.get("schema_version") != "wikipedia_staged_source_manifest_v1" or manifest.get("state") != "VERIFIED":
        raise ValueError("source_manifest_not_verified")
    source = manifest.get("source") or {}
    if str(source.get("index")) != str(INDEX) or int(source.get("index_bytes", -1)) != INDEX.stat().st_size:
        raise ValueError("source_manifest_index_identity_mismatch")
    selection = manifest.get("selection") or {}
    if int(selection.get("offset", -1)) != offset or int(selection.get("limit", -1)) != limit:
        raise ValueError("source_manifest_selection_mismatch")
    rows = manifest.get("rows") or []
    if len(rows) != limit:
        raise ValueError("source_manifest_row_count_mismatch")
    indexed = []
    for row in rows:
        path = Path(str(row.get("path") or ""))
        if not _contained(path) or not path.is_file():
            raise ValueError(f"source_manifest_path_invalid:{path}")
        observed = path.stat().st_size
        if observed != int(row.get("observed_bytes", -1)) or observed != int(row.get("indexed_bytes", -1)):
            raise ValueError(f"source_manifest_bytes_changed:{path}")
        if _sha256(path) != row.get("source_sha256"):
            raise ValueError(f"source_manifest_hash_changed:{path}")
        indexed.append((str(path), int(row["indexed_bytes"]), row.get("indexed_modified_ts"), int(row["ordinal"])))
    return indexed, {
        "path": str(manifest_path),
        "sha256": _sha256(manifest_path),
        "state": manifest["state"],
        "selection_offset": offset,
        "selection_limit": limit,
    }


def run(*, model_path: Path, limit: int = 32, offset: int = 0, source_manifest: Path | None = None) -> dict:
    os.environ["VIV_EMBED_BACKEND"] = "hf_local"
    os.environ["VIV_EMBED_MODEL_PATH"] = str(model_path)
    manifest_info = None
    if source_manifest is not None:
        indexed, manifest_info = _manifest_rows(source_manifest, limit=limit, offset=offset)
    else:
        uri = f"file:{INDEX.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=10.0) as db:
            indexed = db.execute(
                "SELECT full_path, size_bytes, modified_ts FROM file_index "
                "WHERE full_path LIKE ? AND extension='.txt' AND is_dir=0 "
                "ORDER BY full_path COLLATE NOCASE LIMIT ? OFFSET ?",
                (r"F:\AI_Datasets\wikipedia_deduplicated\%", limit, offset),
            ).fetchall()
    rows = []
    chain = "0" * 64
    for ordinal, (raw_path, indexed_bytes, modified_ts, *manifest_ordinal) in enumerate(indexed, start=1):
        if manifest_ordinal:
            ordinal = manifest_ordinal[0]
        path = Path(str(raw_path))
        if not _contained(path) or not path.is_file():
            raise ValueError(f"source_path_containment_or_existence_failed:{path}")
        text = path.read_text(encoding="utf-8", errors="replace")[:12000]
        source_sha = _sha256(path)
        chunk = text[:2048]
        vector = _local_embedding(chunk)
        receipt_material = f"{chain}|{ordinal}|{path}|{source_sha}|{len(vector)}".encode("utf-8")
        chain = hashlib.sha256(receipt_material).hexdigest()
        rows.append(
            {
                "ordinal": ordinal,
                "path": str(path),
                "indexed_bytes": int(indexed_bytes or 0),
                "observed_bytes": path.stat().st_size,
                "indexed_modified_ts": modified_ts,
                "source_sha256": source_sha,
                "chunk_sha256": hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
                "chunk_chars": len(chunk),
                "embedding_dimensions": len(vector),
                "embedding": vector,
            }
        )
    return {
        "schema_version": "wikipedia_32_article_canary_v1",
        "created_utc": _utc_now(),
        "state": "VERIFIED" if len(rows) == limit else "HOLD_SOURCE_COUNT",
        "source_index": str(INDEX),
        "source_root": str(SOURCE_ROOT),
        "embedding_backend": "huggingface_local",
        "model_path": str(model_path),
        "model_sha256": _sha256(model_path / "model.safetensors"),
        "requested_articles": limit,
        "processed_articles": len(rows),
        "selection_offset": offset,
        "selection_order": "full_path COLLATE NOCASE",
        "selection_mode": "manifest_bound" if manifest_info else "read_only_index_offset",
        "source_manifest": manifest_info,
        "chunk_chars": 2048,
        "max_article_chars": 12000,
        "checkpoint": {
            "interval_articles": 1024,
            "processed_articles": len(rows),
            "receipt_chain_sha256": chain,
        },
        "staged_only": True,
        "source_tree_changed": False,
        "sqlite_index_changed": False,
        "staged_vectors_written": bool(rows),
        "vector_index_written": False,
        "carma_admission": False,
        "training_authorized": False,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--source-manifest", type=Path)
    args = parser.parse_args()
    if not (INDEX.is_file() and (args.model_path / "model.safetensors").is_file()):
        raise SystemExit("required index or model artifact missing")
    result = run(model_path=args.model_path, offset=args.offset, source_manifest=args.source_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["state"] == "VERIFIED", "state": result["state"], "offset": result["selection_offset"], "processed_articles": result["processed_articles"], "receipt_chain_sha256": result["checkpoint"]["receipt_chain_sha256"], "output": str(args.output), "staged_vectors_written": result["staged_vectors_written"], "vector_index_written": False, "carma_admission": False, "training_authorized": False}, indent=2))
    return 0 if result["state"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
