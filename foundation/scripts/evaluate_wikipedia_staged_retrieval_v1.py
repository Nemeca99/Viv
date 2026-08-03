#!/usr/bin/env python3
"""Evaluate retrieval over staged vectors without persisting an index."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))
from lib.knowledge_semantic_backend import _local_embedding  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    left = math.sqrt(sum(float(x) * float(x) for x in a))
    right = math.sqrt(sum(float(y) * float(y) for y in b))
    return dot / (left * right) if left and right else float("nan")


_TITLE_RE = re.compile(r"^\s*Title:\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)
_REDIRECT_RE = re.compile(r"^\s*#REDIRECT\s*\[\[(.*?)\]\]", re.IGNORECASE | re.MULTILINE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _revalidate_source_manifest(manifest_path: Path, staged_paths: set[str]) -> dict:
    """Recheck source truth after vector ranking; fail closed on mismatch."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"state": "HOLD", "rows_checked": 0, "matched": 0, "reasons": [f"manifest_read:{type(exc).__name__}"]}
    if manifest.get("schema_version") != "wikipedia_staged_source_manifest_v1" or manifest.get("state") != "VERIFIED":
        return {"state": "HOLD", "rows_checked": 0, "matched": 0, "reasons": ["source_manifest_not_verified"]}
    by_path = {str(row.get("path")): row for row in manifest.get("rows") or []}
    reasons: list[str] = []
    matched = 0
    root = Path(str(manifest.get("source", {}).get("root", ""))).resolve()
    for raw_path in sorted(staged_paths):
        row = by_path.get(raw_path)
        path = Path(raw_path)
        if row is None:
            reasons.append(f"manifest_row_missing:{raw_path}")
            continue
        try:
            exists = path.is_file()
            observed_bytes = path.stat().st_size if exists else None
            text = path.read_text(encoding="utf-8", errors="replace") if exists else ""
            title_match = _TITLE_RE.search(text)
            redirect_match = _REDIRECT_RE.search(text)
            checks = {
                "contained": bool(row.get("contained")) and path.resolve().is_relative_to(root),
                "exists": exists,
                "indexed_observed_bytes": exists and int(row.get("indexed_bytes", -1)) == observed_bytes,
                "manifest_observed_bytes": exists and int(row.get("observed_bytes", -1)) == observed_bytes,
                "source_sha256": exists and _sha256(path) == row.get("source_sha256"),
                "title_header": bool(title_match) and title_match.group(1).strip() == str(row.get("title") or ""),
                "redirect_status": (redirect_match is not None) == bool(row.get("is_redirect")),
            }
        except (OSError, ValueError, TypeError) as exc:
            checks = {"exception": f"{type(exc).__name__}:{exc}"}
        if not all(checks.values()):
            reasons.append(f"source_revalidation_failed:{raw_path}:{checks}")
        else:
            matched += 1
    return {
        "state": "VERIFIED" if not reasons and matched == len(staged_paths) else "HOLD",
        "rows_checked": len(staged_paths),
        "matched": matched,
        "reasons": reasons,
        "manifest_sha256": _sha256(manifest_path),
    }


def evaluate(
    artifacts: list[Path],
    queries: list[dict],
    manifest_path: Path | None = None,
    title_map_path: Path | None = None,
    source_manifest_path: Path | None = None,
    max_staged_articles: int = 64,
) -> dict:
    max_staged_articles = max(1, int(max_staged_articles))
    rows_by_path: dict[str, dict] = {}
    artifact_hashes = []
    excluded_paths: set[str] = set()
    manifest_hash = None
    manifest_counts = None
    title_aliases: dict[str, str] = {}
    title_map_hash = None
    if manifest_path is not None:
        manifest_hash = __import__("hashlib").sha256(manifest_path.read_bytes()).hexdigest()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_counts = manifest.get("resolution_counts", {})
        excluded_paths = {
            str(row["path"])
            for row in manifest.get("rows", [])
            if row.get("source_is_redirect")
        }
    if title_map_path is not None:
        title_map_hash = __import__("hashlib").sha256(title_map_path.read_bytes()).hexdigest()
        title_map = json.loads(title_map_path.read_text(encoding="utf-8"))
        title_aliases = {
            str(row["redirect_path"]): str(row["canonical_path"])
            for row in title_map.get("results", [])
            if row.get("resolution_state") == "RESOLVED_CROSS_DIRECTORY" and row.get("canonical_path")
        }
    for artifact_path in artifacts:
        artifact_hashes.append({"path": str(artifact_path), "sha256": __import__("hashlib").sha256(artifact_path.read_bytes()).hexdigest()})
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        if artifact.get("state") != "VERIFIED":
            raise ValueError(f"artifact_not_verified:{artifact_path}")
        for row in artifact.get("rows", []):
            path = str(row["path"])
            if path in rows_by_path:
                raise ValueError(f"duplicate_staged_path:{path}")
            vector = row.get("embedding", [])
            if len(vector) != 384 or not all(math.isfinite(float(value)) for value in vector):
                raise ValueError(f"invalid_staged_vector:{path}")
            if path not in excluded_paths:
                rows_by_path[path] = {"path": path, "vector": vector, "ordinal": row.get("ordinal")}

    ranked = []
    for case in queries:
        query_vector = _local_embedding(case["query"])
        scores = sorted(
            ((path, _cosine(query_vector, row["vector"])) for path, row in rows_by_path.items()),
            key=lambda item: item[1],
            reverse=True,
        )
        target = case["target_path"]
        effective_target = title_aliases.get(target, target)
        target_rank = next((index for index, (path, _score) in enumerate(scores, start=1) if path == effective_target), None)
        target_excluded = target in excluded_paths and effective_target == target
        ranked.append(
            {
                "query": case["query"],
                "target_path": target,
                "effective_target_path": effective_target,
                "target_present": effective_target in rows_by_path,
                "target_excluded_redirect": target_excluded,
                "eligible_for_metric": effective_target in rows_by_path and not target_excluded,
                "target_rank": target_rank,
                "top_k": [{"path": path, "score": round(score, 6)} for path, score in scores[:5]],
            }
        )
    valid_ranks = [item["target_rank"] for item in ranked if item["eligible_for_metric"] and item["target_rank"] is not None]
    source_revalidation = (
        _revalidate_source_manifest(source_manifest_path, set(rows_by_path))
        if source_manifest_path is not None
        else {"state": "NOT_REQUESTED", "rows_checked": 0, "matched": 0, "reasons": []}
    )
    state = "VERIFIED" if len(rows_by_path) <= max_staged_articles and len(rows_by_path) > 0 and source_revalidation["state"] in {"VERIFIED", "NOT_REQUESTED"} else "HOLD"
    return {
        "schema_version": "wikipedia_staged_retrieval_evaluation_v1",
        "created_utc": _utc_now(),
        "state": state,
        "bounded_article_limit": max_staged_articles,
        "staged_article_count": len(rows_by_path),
        "redirect_manifest_sha256": manifest_hash,
        "redirect_resolution_counts": manifest_counts,
        "title_map_sha256": title_map_hash,
        "excluded_redirect_rows": len(excluded_paths),
        "embedding_dimensions": 384,
        "artifact_hashes": artifact_hashes,
        "source_revalidation": source_revalidation,
        "queries": ranked,
        "metrics": {
            "queries": len(queries),
            "target_present": sum(item["target_present"] for item in ranked),
            "eligible_queries": sum(item["eligible_for_metric"] for item in ranked),
            "excluded_redirect_queries": sum(item["target_excluded_redirect"] for item in ranked),
            "top1_hits": sum(item["target_rank"] == 1 for item in ranked),
            "mean_reciprocal_rank": sum(1.0 / rank for rank in valid_ranks) / len(valid_ranks) if valid_ranks else 0.0,
            "max_target_rank": max(valid_ranks) if valid_ranks else None,
        },
        "writes_performed": False,
        "vector_index_written": False,
        "carma_admission": False,
        "training_authorized": False,
        "interpretation": "Read-only staged retrieval quality only; no claim of full-corpus semantic quality or factual entailment.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, action="append", required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--redirect-manifest", type=Path)
    parser.add_argument("--title-map", type=Path)
    parser.add_argument("--queries-file", type=Path)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--max-staged-articles", type=int, default=64)
    args = parser.parse_args()
    os.environ["VIV_EMBED_BACKEND"] = "hf_local"
    os.environ["VIV_EMBED_MODEL_PATH"] = str(args.model_path)
    queries = [
        {"query": "a political philosophy that rejects the state and imposed hierarchy", "target_path": r"F:\AI_Datasets\wikipedia_deduplicated\batch_0000\000001_Anarchism.txt"},
        {"query": "a condition involving differences in communication and behavior", "target_path": r"F:\AI_Datasets\wikipedia_deduplicated\batch_0000\000004_Autism spectrum.txt"},
        {"query": "the reflectivity of a surface", "target_path": r"F:\AI_Datasets\wikipedia_deduplicated\batch_0000\000005_Albedo.txt"},
        {"query": "the science and practice of cultivating land and crops", "target_path": r"F:\AI_Datasets\wikipedia_deduplicated\batch_0000\000050_Agriculture.txt"},
    ]
    if args.queries_file is not None:
        loaded_queries = json.loads(args.queries_file.read_text(encoding="utf-8"))
        if not isinstance(loaded_queries, list) or not all(isinstance(item, dict) for item in loaded_queries):
            raise SystemExit("queries_file_must_contain_list_of_objects")
        queries = loaded_queries
    result = evaluate(
        args.artifact,
        queries,
        args.redirect_manifest,
        args.title_map,
        args.source_manifest,
        args.max_staged_articles,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["state"] == "VERIFIED", "state": result["state"], "staged_article_count": result["staged_article_count"], "metrics": result["metrics"], "output": str(args.output)}, indent=2))
    return 0 if result["state"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
