#!/usr/bin/env python3
"""Build a redirect-resolved staged vector artifact without persistent writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.knowledge_semantic_backend import _local_embedding  # noqa: E402

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


def _inspect(path: Path) -> tuple[str | None, str | None, str]:
    text = path.read_text(encoding="utf-8", errors="replace")[:12000]
    title = TITLE_RE.search(text)
    redirect = REDIRECT_RE.search(text)
    return (title.group(1).strip() if title else None, redirect.group(1).strip() if redirect else None, text)


def build(artifacts: list[Path], manifest_path: Path, title_map_path: Path, model_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    title_map = json.loads(title_map_path.read_text(encoding="utf-8"))
    title_results = {str(row["redirect_path"]): row for row in title_map.get("results", [])}
    rows_by_path: dict[str, dict] = {}
    input_hashes = []
    for artifact_path in artifacts:
        input_hashes.append({"path": str(artifact_path), "sha256": _sha256(artifact_path)})
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        if artifact.get("state") != "VERIFIED":
            raise ValueError(f"artifact_not_verified:{artifact_path}")
        for row in artifact.get("rows", []):
            rows_by_path[str(row["path"])] = row

    output_rows: list[dict] = []
    aliases: list[dict] = []
    for path, row in rows_by_path.items():
        manifest_row = next((item for item in manifest.get("rows", []) if item.get("path") == path), None)
        if manifest_row and manifest_row.get("source_is_redirect"):
            if manifest_row.get("resolution_state") == "RESOLVED_LOCAL":
                canonical = Path(str(manifest_row["canonical_path"]))
            else:
                result = title_results.get(path)
                if not result or result.get("resolution_state") != "RESOLVED_CROSS_DIRECTORY":
                    raise ValueError(f"redirect_not_resolved:{path}")
                canonical = Path(str(result["canonical_path"]))
            if not _contained(canonical) or not canonical.is_file():
                raise ValueError(f"canonical_path_invalid:{canonical}")
            title, redirect, text = _inspect(canonical)
            target = str(manifest_row["redirect_target"])
            if title is None or title.casefold() != target.casefold() or redirect is not None:
                raise ValueError(f"canonical_content_contract_failed:{canonical}")
            if str(canonical) in rows_by_path:
                aliases.append({"redirect_path": path, "canonical_path": str(canonical), "state": "ALIAS_TO_EXISTING_VECTOR"})
                continue
            chunk = text[:2048]
            vector = _local_embedding(chunk)
            output_rows.append({
                "ordinal": len(output_rows) + 1,
                "path": str(canonical),
                "source_kind": "resolved_redirect_target",
                "redirect_aliases": [path],
                "source_sha256": _sha256(canonical),
                "chunk_sha256": hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
                "chunk_chars": len(chunk),
                "observed_bytes": canonical.stat().st_size,
                "embedding_dimensions": len(vector),
                "embedding": vector,
            })
        else:
            output_rows.append({**row, "source_kind": "direct_staged_content", "redirect_aliases": []})

    # Preserve unique paths and validate every vector before writing evidence.
    if len({str(row["path"]) for row in output_rows}) != len(output_rows):
        raise ValueError("duplicate_output_vector_path")
    if not all(len(row.get("embedding", [])) == 384 and all(math.isfinite(float(value)) for value in row.get("embedding", [])) for row in output_rows):
        raise ValueError("invalid_output_vector")
    return {
        "schema_version": "wikipedia_redirect_resolved_staged_vectors_v1",
        "created_utc": _utc_now(),
        "state": "VERIFIED",
        "source_root": str(SOURCE_ROOT),
        "model_path": str(model_path),
        "model_sha256": _sha256(model_path / "model.safetensors"),
        "input_artifacts": input_hashes,
        "redirect_manifest": str(manifest_path),
        "redirect_manifest_sha256": _sha256(manifest_path),
        "title_map": str(title_map_path),
        "title_map_sha256": _sha256(title_map_path),
        "source_rows": len(rows_by_path),
        "unique_vector_rows": len(output_rows),
        "alias_count": len(aliases),
        "aliases": aliases,
        "rows": output_rows,
        "authority": {
            "source_tree_changed": False,
            "sqlite_index_changed": False,
            "vector_index_written": False,
            "carma_admission": False,
            "training_authorized": False,
            "run_authorized": False,
        },
        "interpretation": "Redirects are aliases to verified canonical local articles; only canonical content receives a staged vector and no persistent index is written.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, action="append", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--title-map", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ["VIV_EMBED_BACKEND"] = "hf_local"
    os.environ["VIV_EMBED_MODEL_PATH"] = str(args.model_path)
    result = build(args.artifact, args.manifest, args.title_map, args.model_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["state"] == "VERIFIED", "state": result["state"], "source_rows": result["source_rows"], "unique_vector_rows": result["unique_vector_rows"], "alias_count": result["alias_count"], "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
