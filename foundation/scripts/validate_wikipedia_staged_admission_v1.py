#!/usr/bin/env python3
"""Validate staged Wikipedia provenance and report persistent-index admission readiness.

This validator is evidence-only. It never writes the corpus, SQLite index, vector
index, CARMA, training state, or deployment state. A bounded staged pass can be
verified while persistent admission remains HOLD until broader coverage and
row-level semantic disjointness are proven separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.triad_kernel import TRIAD_CONTRACT_VERSION  # noqa: E402

SOURCE_ROOT = Path(r"F:\AI_Datasets\wikipedia_deduplicated").resolve()
TITLE_RE = re.compile(r"^\s*Title:\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)
REDIRECT_RE = re.compile(r"^\s*#REDIRECT\s*\[\[([^\]|#]+)", re.IGNORECASE | re.MULTILINE)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
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


def _check(name: str, passed: bool, detail: str) -> dict[str, object]:
    return {"name": name, "state": "PASS" if passed else "HOLD", "detail": detail}


def validate(vectors_path: Path, evaluation_path: Path, manifest_path: Path, title_map_path: Path) -> dict:
    vectors = json.loads(vectors_path.read_text(encoding="utf-8"))
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    title_map = json.loads(title_map_path.read_text(encoding="utf-8"))
    checks: list[dict[str, object]] = []

    checks.append(_check("vector_artifact_verified", vectors.get("state") == "VERIFIED", str(vectors.get("state"))))
    checks.append(_check("evaluation_artifact_verified", evaluation.get("state") == "VERIFIED", str(evaluation.get("state"))))
    checks.append(_check("manifest_verified", manifest.get("state") == "VERIFIED", str(manifest.get("state"))))
    checks.append(_check("title_map_verified", title_map.get("state") == "VERIFIED", str(title_map.get("state"))))

    manifest_hash = _sha256_file(manifest_path)
    title_map_hash = _sha256_file(title_map_path)
    lineage_ok = (
        vectors.get("redirect_manifest_sha256") == manifest_hash
        and vectors.get("title_map_sha256") == title_map_hash
        and evaluation.get("redirect_manifest_sha256") == manifest_hash
        and evaluation.get("title_map_sha256") == title_map_hash
    )
    checks.append(_check("lineage_hashes", lineage_ok, f"manifest={manifest_hash}; title_map={title_map_hash}"))

    authority = vectors.get("authority") or {}
    authority_closed = all(
        authority.get(key) is False
        for key in ("vector_index_written", "carma_admission", "training_authorized", "run_authorized", "source_tree_changed", "sqlite_index_changed")
    )
    checks.append(_check("vector_authority_closed", authority_closed, json.dumps(authority, sort_keys=True)))
    checks.append(_check("evaluation_writes_closed", all(evaluation.get(key) is False for key in ("writes_performed", "vector_index_written", "carma_admission", "training_authorized")), "evaluation side effects are false"))

    rows = vectors.get("rows") or []
    paths = [str(row.get("path")) for row in rows]
    unique_paths = len(paths) == len(set(paths))
    checks.append(_check("unique_canonical_paths", unique_paths, f"rows={len(rows)}; unique={len(set(paths))}"))
    finite_vectors = all(
        int(row.get("embedding_dimensions", 0)) == 384
        and len(row.get("embedding") or []) == 384
        and all(math.isfinite(float(value)) for value in row.get("embedding") or [])
        for row in rows
    )
    checks.append(_check("finite_384d_vectors", finite_vectors, f"rows={len(rows)}"))

    source_checks = 0
    source_failures: list[str] = []
    for row in rows:
        path = Path(str(row.get("path")))
        if not _contained(path) or not path.is_file():
            source_failures.append(f"path:{path}")
            continue
        title, redirect, text = _inspect(path)
        if redirect is not None or title is None:
            source_failures.append(f"content:{path}")
            continue
        if _sha256_file(path) != str(row.get("source_sha256")):
            source_failures.append(f"sha256:{path}")
            continue
        if path.stat().st_size != int(row.get("observed_bytes", -1)):
            source_failures.append(f"bytes:{path}")
            continue
        chunk = text[:2048]
        if hashlib.sha256(chunk.encode("utf-8")).hexdigest() != str(row.get("chunk_sha256")):
            source_failures.append(f"chunk:{path}")
            continue
        source_checks += 1
    checks.append(_check("source_provenance", not source_failures, f"verified={source_checks}/{len(rows)}; failures={source_failures[:3]}"))

    aliases = vectors.get("aliases") or []
    alias_targets_ok = all(str(alias.get("canonical_path")) in set(paths) for alias in aliases)
    checks.append(_check("alias_targets_canonical", alias_targets_ok, f"aliases={len(aliases)}"))
    metrics = evaluation.get("metrics") or {}
    retrieval_ok = (
        metrics.get("queries") == 4
        and metrics.get("target_present") == 4
        and metrics.get("top1_hits", 0) >= 3
        and float(metrics.get("mean_reciprocal_rank", 0.0)) >= 0.8
    )
    checks.append(_check("bounded_retrieval_baseline", retrieval_ok, json.dumps(metrics, sort_keys=True)))

    manifest_counts = manifest.get("resolution_counts") or {}
    cross_map_results = [row for row in title_map.get("results", []) if row.get("resolution_state") == "RESOLVED_CROSS_DIRECTORY"]
    resolution_reconciles = (
        len(cross_map_results) == int(manifest_counts.get("UNRESOLVED_LOCAL_STAGED_SCOPE", 0))
        and int(vectors.get("source_rows", -1)) == len(rows) + len(aliases)
    )
    checks.append(_check("redirect_resolution_reconciles", resolution_reconciles, f"cross_directory={len(cross_map_results)}; source_rows={vectors.get('source_rows')}; vectors={len(rows)}; aliases={len(aliases)}"))

    hold_reasons = [
        "bounded_sample_is_not_full_corpus_coverage",
        "semantic_or_content_disjointness_against_training_holdout_is_not_proven_by_these_artifacts",
        "persistent_vector_index_admission_requires_separate_authorization",
    ]
    all_evidence_checks_pass = all(row["state"] == "PASS" for row in checks)
    return {
        "schema_version": "wikipedia_staged_admission_validation_v1",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "triad_contract_version": TRIAD_CONTRACT_VERSION,
        "state": "VERIFIED" if all_evidence_checks_pass else "HOLD",
        "decision": "HOLD_PERSISTENT_INDEX_ADMISSION",
        "checks": checks,
        "source_rows": vectors.get("source_rows"),
        "unique_vector_rows": vectors.get("unique_vector_rows"),
        "alias_count": vectors.get("alias_count"),
        "retrieval_metrics": metrics,
        "hold_reasons": hold_reasons,
        "authority": {
            "vector_index_written": False,
            "carma_admission": False,
            "training_authorized": False,
            "run_authorized": False,
        },
        "interpretation": "Evidence and bounded retrieval provenance are verified; persistent-index admission remains held until full-coverage and row-level disjointness evidence plus separate authority exist.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--title-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = validate(args.vectors, args.evaluation, args.manifest, args.title_map)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["state"] == "VERIFIED", "state": result["state"], "decision": result["decision"], "output": str(args.output)}, indent=2))
    return 0 if result["state"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
