#!/usr/bin/env python3
"""Classify staged Wikipedia rows and resolve redirects only via local provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

INDEX = Path(r"D:\LocalAi\5126\FSAA\Luna\AIOS_V2\dataset_core\global_index.db")
SOURCE_ROOT = Path(r"F:\AI_Datasets\wikipedia_deduplicated").resolve()
REDIRECT_RE = re.compile(r"^\s*#REDIRECT\s*\[\[([^\]|#]+)", re.IGNORECASE | re.MULTILINE)
TITLE_RE = re.compile(r"^\s*Title:\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)


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


def _title_and_redirect(path: Path) -> tuple[str | None, str | None, str]:
    text = path.read_text(encoding="utf-8", errors="replace")[:12000]
    title_match = TITLE_RE.search(text)
    redirect_match = REDIRECT_RE.search(text)
    return (
        title_match.group(1).strip() if title_match else None,
        redirect_match.group(1).strip() if redirect_match else None,
        text,
    )


def build(artifacts: list[Path]) -> dict:
    rows = []
    artifact_hashes = []
    for artifact_path in artifacts:
        artifact_hashes.append({"path": str(artifact_path), "sha256": _sha256(artifact_path)})
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        if data.get("state") != "VERIFIED":
            raise ValueError(f"artifact_not_verified:{artifact_path}")
        rows.extend(data.get("rows", []))

    redirect_rows = []
    parsed = []
    for row in rows:
        path = Path(str(row["path"]))
        title, target, _text = _title_and_redirect(path)
        item = {
            "path": str(path),
            "source_sha256": _sha256(path),
            "title": title,
            "redirect_target": target,
            "source_is_redirect": target is not None,
        }
        parsed.append(item)

    # Keep this checkpoint bounded: a redirect may only resolve inside the
    # same staged source directory. Full-corpus title-map construction is a
    # separate governed ingestion step and is not silently performed here.
    candidate_by_target: dict[str, list[Path]] = {}
    for item in parsed:
        if not item["source_is_redirect"]:
            continue
        source_path = Path(item["path"])
        target = str(item["redirect_target"])
        try:
            candidates = source_path.parent.glob(f"*_{target}.txt")
        except (ValueError, OSError):
            candidates = []
        for path in candidates:
            if not _contained(path) or not path.is_file():
                continue
            title, redirect, _text = _title_and_redirect(path)
            if title and redirect is None and title.casefold() == target.casefold():
                candidate_by_target.setdefault(target.casefold(), []).append(path)

    for item in parsed:
        if not item["source_is_redirect"]:
            item.update({"resolution_state": "DIRECT_CONTENT", "canonical_path": item["path"]})
            continue
        target = str(item["redirect_target"])
        matches = sorted({str(path) for path in candidate_by_target.get(target.casefold(), [])})
        if len(matches) == 1:
            item.update({"resolution_state": "RESOLVED_LOCAL", "canonical_path": matches[0], "candidate_count": 1})
        else:
            item.update({"resolution_state": "UNRESOLVED_LOCAL_STAGED_SCOPE", "canonical_path": None, "candidate_count": len(matches)})
        redirect_rows.append(item)

    counts = {}
    for item in parsed:
        counts[item["resolution_state"]] = counts.get(item["resolution_state"], 0) + 1
    return {
        "schema_version": "wikipedia_redirect_aware_manifest_v1",
        "created_utc": _utc_now(),
        "state": "VERIFIED",
        "source_index": str(INDEX),
        "source_root": str(SOURCE_ROOT),
        "input_artifacts": artifact_hashes,
        "row_count": len(parsed),
        "resolution_counts": counts,
        "redirect_rows": redirect_rows,
        "rows": parsed,
        "authority": {
            "read_only_index": True,
            "source_tree_changed": False,
            "vector_index_written": False,
            "carma_admission": False,
            "training_authorized": False,
        },
        "resolution_scope": "same_staged_source_directory_only",
        "interpretation": "Only exact local non-redirect title matches in the staged source directory are resolved; unresolved redirects remain explicit and are not treated as article content.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["state"] == "VERIFIED", "state": result["state"], "row_count": result["row_count"], "resolution_counts": result["resolution_counts"], "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
