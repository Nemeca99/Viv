#!/usr/bin/env python3
"""Build a bounded, read-only title map for unresolved Wikipedia redirects."""
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
TITLE_RE = re.compile(r"^\s*Title:\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)
REDIRECT_RE = re.compile(r"^\s*#REDIRECT\s*\[\[([^\]|#]+)", re.IGNORECASE | re.MULTILINE)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _inspect(path: Path) -> tuple[str | None, str | None]:
    text = path.read_text(encoding="utf-8", errors="replace")[:12000]
    title = TITLE_RE.search(text)
    redirect = REDIRECT_RE.search(text)
    return (title.group(1).strip() if title else None, redirect.group(1).strip() if redirect else None)


def build(manifest_path: Path, candidate_cap: int) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    unresolved = [row for row in manifest.get("redirect_rows", []) if row.get("resolution_state", "").startswith("UNRESOLVED")]
    results = []
    with sqlite3.connect(f"file:{INDEX.as_posix()}?mode=ro", uri=True, timeout=10.0) as db:
        for row in unresolved:
            target = str(row["redirect_target"])
            # The corpus naming contract is six digits + '_' + exact title.
            # This is one bounded read-only query per target; candidate content
            # and the Title header remain authoritative.
            candidates = db.execute(
                "SELECT full_path, size_bytes FROM file_index "
                "WHERE full_path LIKE ? AND extension='.txt' AND is_dir=0 AND file_name GLOB ? "
                "ORDER BY full_path COLLATE NOCASE LIMIT ?",
                (r"F:\AI_Datasets\wikipedia_deduplicated\%", f"[0-9][0-9][0-9][0-9][0-9][0-9]_{target}.txt", candidate_cap),
            ).fetchall()
            exact = []
            inspected = []
            for raw_path, indexed_bytes in candidates:
                path = Path(str(raw_path))
                title = redirect = None
                valid = _contained(path) and path.is_file()
                if valid:
                    title, redirect = _inspect(path)
                record = {
                    "path": str(path),
                    "indexed_bytes": int(indexed_bytes or 0),
                    "exists_and_contained": valid,
                    "title": title,
                    "is_redirect": redirect is not None,
                }
                inspected.append(record)
                if valid and title and title.casefold() == target.casefold() and redirect is None:
                    record["source_sha256"] = _sha256(path)
                    record["observed_bytes"] = path.stat().st_size
                    exact.append(record)
            cap_reached = len(candidates) >= candidate_cap
            if len(exact) == 1:
                state = "RESOLVED_CROSS_DIRECTORY"
                canonical = exact[0]["path"]
            elif len(exact) > 1:
                state = "AMBIGUOUS_CROSS_DIRECTORY"
                canonical = None
            elif cap_reached:
                state = "CANDIDATE_CAP_REACHED"
                canonical = None
            else:
                state = "UNRESOLVED_CROSS_DIRECTORY"
                canonical = None
            results.append(
                {
                    "redirect_path": row["path"],
                    "redirect_target": target,
                    "resolution_state": state,
                    "canonical_path": canonical,
                    "exact_verified_candidates": exact,
                    "candidate_rows_inspected": inspected,
                    "candidate_cap": candidate_cap,
                }
            )
    counts = {}
    for result in results:
        counts[result["resolution_state"]] = counts.get(result["resolution_state"], 0) + 1
    return {
        "schema_version": "wikipedia_bounded_title_map_v1",
        "created_utc": _utc_now(),
        "state": "VERIFIED",
        "source_index": str(INDEX),
        "source_root": str(SOURCE_ROOT),
        "input_manifest": str(manifest_path),
        "input_manifest_sha256": _sha256(manifest_path),
        "resolution_scope": "cross_directory_index_query_per_target_with_candidate_cap",
        "candidate_cap": candidate_cap,
        "redirect_targets_requested": len(unresolved),
        "resolution_counts": counts,
        "results": results,
        "authority": {
            "read_only_index": True,
            "source_tree_changed": False,
            "sqlite_index_changed": False,
            "vector_index_written": False,
            "carma_admission": False,
            "training_authorized": False,
        },
        "interpretation": "Exact non-redirect Title matches are required; capped or missing candidates remain unresolved and are never treated as verified knowledge.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidate-cap", type=int, default=32)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.manifest, args.candidate_cap)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["state"] == "VERIFIED", "state": result["state"], "redirect_targets_requested": result["redirect_targets_requested"], "resolution_counts": result["resolution_counts"], "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
