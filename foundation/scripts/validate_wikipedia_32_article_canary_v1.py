#!/usr/bin/env python3
"""Validate the staged Wikipedia canary without mutating source or index state."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
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


def _contained(path: Path) -> bool:
    try:
        path.resolve().relative_to(SOURCE_ROOT)
        return True
    except ValueError:
        return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _direct_path_overlap(paths: set[str], search_root: Path, explicit_files: list[Path]) -> dict:
    """Search selected current training artifacts for exact source paths."""
    matches: list[str] = []
    scanned = 0
    candidates = explicit_files
    if not candidates and not search_root.is_dir():
        return {"state": "INCONCLUSIVE", "reason": "training_artifact_root_missing", "matches": [], "files_scanned": 0}
    if not candidates:
        candidates = [candidate for candidate in search_root.rglob("*") if candidate.is_file() and "backups" not in candidate.parts and candidate.suffix.lower() in {".json", ".jsonl"} and candidate.stat().st_size <= 10 * 1024 * 1024]
    for candidate in candidates:
        if not candidate.is_file() or "backups" in candidate.parts:
            continue
        if candidate.suffix.lower() not in {".json", ".jsonl", ".txt", ".md"}:
            continue
        scanned += 1
        try:
            data = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(path in data for path in paths):
            matches.append(str(candidate))
    return {
        "state": "VERIFIED_DISJOINT" if not matches else "HOLD_OVERLAP",
        "matches": matches,
        "files_scanned": scanned,
        "scope": "exact_full_path_strings_in_current_non_backup_artifacts",
    }


def validate(artifact_path: Path, training_root: Path, explicit_files: list[Path] | None = None) -> dict:
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    rows = artifact.get("rows", [])
    reasons: list[str] = []
    checks = {
        "artifact_state_verified": artifact.get("state") == "VERIFIED",
        "requested_equals_processed": artifact.get("requested_articles") == artifact.get("processed_articles") == len(rows),
        "staged_only": artifact.get("staged_only") is True,
        "no_vector_index_write": artifact.get("vector_index_written") is False,
        "no_carma_admission": artifact.get("carma_admission") is False,
        "no_training_authority": artifact.get("training_authorized") is False,
    }
    if not all(checks.values()):
        reasons.append("artifact_contract_failed")

    paths: set[str] = set()
    chain = "0" * 64
    row_results: list[dict] = []
    requested_paths = [str(row.get("path", "")) for row in rows]
    with sqlite3.connect(f"file:{INDEX.as_posix()}?mode=ro", uri=True, timeout=10.0) as db:
        # The recovered index is multi-gigabyte and exact full_path lookups are
        # not guaranteed to use a narrow index.  Group the canary by directory
        # and issue one bounded prefix query per directory instead.
        indexed_by_path: dict[str, tuple[int, object]] = {}
        prefixes = sorted({str(Path(raw).parent) + "\\" for raw in requested_paths if raw})
        for prefix in prefixes:
            for indexed_path, indexed_bytes, modified_ts in db.execute(
                "SELECT full_path, size_bytes, modified_ts FROM file_index "
                "WHERE full_path LIKE ? AND extension='.txt' AND is_dir=0",
                (prefix + "%",),
            ):
                indexed_by_path[str(indexed_path)] = (int(indexed_bytes or 0), modified_ts)
        for fallback_ordinal, row in enumerate(rows, start=1):
            # Manifest-bound batches preserve corpus ordinals; legacy canaries
            # may start at one.  Recompute exactly what the artifact recorded.
            source_ordinal = int(row.get("ordinal", fallback_ordinal))
            raw_path = str(row.get("path", ""))
            path = Path(raw_path)
            canonical = str(path.resolve())
            paths.add(canonical.lower())
            path_ok = _contained(path) and path.is_file()
            indexed = indexed_by_path.get(raw_path)
            if path_ok:
                text = path.read_text(encoding="utf-8", errors="replace")[: int(artifact.get("max_article_chars", 12000))]
                source_sha = _sha256(path)
                chunk = text[: int(artifact.get("chunk_chars", 2048))]
                observed_bytes = path.stat().st_size
                chunk_sha = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
            else:
                source_sha = ""
                chunk_sha = ""
                observed_bytes = None
                chunk = ""
            vector = row.get("embedding", [])
            finite = all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in vector)
            receipt_material = f"{chain}|{source_ordinal}|{path}|{source_sha}|{len(vector)}".encode("utf-8")
            chain = hashlib.sha256(receipt_material).hexdigest()
            result = {
                "ordinal": source_ordinal,
                "path_contained_and_exists": path_ok,
                "sqlite_row_found": indexed is not None,
                "indexed_bytes_match": indexed is not None and int(indexed[0] or 0) == int(row.get("indexed_bytes", -1)),
                "observed_bytes_match": path_ok and observed_bytes == int(row.get("observed_bytes", -1)),
                "source_sha256_match": path_ok and source_sha == row.get("source_sha256"),
                "chunk_sha256_match": path_ok and chunk_sha == row.get("chunk_sha256"),
                "chunk_chars_match": path_ok and len(chunk) == int(row.get("chunk_chars", -1)),
                "embedding_dimensions": len(vector),
                "embedding_finite": finite,
            }
            row_results.append(result)

    checks.update(
        {
            "unique_paths": len(paths) == len(rows),
            "all_row_checks": all(all(value for key, value in result.items() if key != "ordinal") for result in row_results),
            "receipt_chain_match": chain == artifact.get("checkpoint", {}).get("receipt_chain_sha256"),
            "all_embeddings_384": all(result["embedding_dimensions"] == 384 for result in row_results),
            "all_embeddings_finite": all(result["embedding_finite"] for result in row_results),
        }
    )
    if not checks["all_row_checks"]:
        reasons.append("source_or_index_revalidation_failed")
    if not checks["receipt_chain_match"]:
        reasons.append("receipt_chain_mismatch")

    overlap = _direct_path_overlap(paths, training_root, explicit_files or [])
    if overlap["state"] == "HOLD_OVERLAP":
        reasons.append("direct_path_overlap_with_current_artifact")
    elif overlap["state"] == "INCONCLUSIVE":
        reasons.append("training_artifact_scope_unavailable")

    state = "VERIFIED" if not reasons else ("INCONCLUSIVE_DISJOINTNESS" if reasons == ["training_artifact_scope_unavailable"] else "HOLD")
    return {
        "schema_version": "wikipedia_32_article_canary_validation_v1",
        "created_utc": _utc_now(),
        "state": state,
        "artifact": str(artifact_path),
        "source_index": str(INDEX),
        "source_root": str(SOURCE_ROOT),
        "checks": checks,
        "row_count": len(rows),
        "receipt_chain_sha256_recomputed": chain,
        "direct_path_overlap": overlap,
        "disjointness_interpretation": "Direct source-path disjointness only; semantic/content overlap is not claimed without row-level training provenance.",
        "row_results": row_results,
        "reasons": reasons,
        "writes_performed": False,
        "source_tree_changed": False,
        "sqlite_index_changed": False,
        "vector_index_written": False,
        "carma_admission": False,
        "training_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--training-root", type=Path, default=Path(r"L:\Continue\Viv\foundation\artifacts\auto"))
    parser.add_argument("--overlap-file", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = validate(args.artifact, args.training_root, args.overlap_file)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["state"] == "VERIFIED", "state": result["state"], "row_count": result["row_count"], "reasons": result["reasons"], "output": str(args.output)}, indent=2))
    return 0 if result["state"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
