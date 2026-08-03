#!/usr/bin/env python3
"""Aggregate verified bounded retrieval windows into a pre-change baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def aggregate(artifacts: list[Path]) -> dict:
    if not artifacts:
        raise ValueError("baseline_requires_artifacts")
    windows = []
    all_queries = []
    for artifact_path in artifacts:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        if payload.get("state") != "VERIFIED":
            raise ValueError(f"evaluation_not_verified:{artifact_path}")
        revalidation = payload.get("source_revalidation") or {}
        if revalidation.get("state") != "VERIFIED":
            raise ValueError(f"source_revalidation_not_verified:{artifact_path}")
        metrics = payload.get("metrics") or {}
        queries = payload.get("queries") or []
        windows.append({
            "artifact": str(artifact_path),
            "sha256": _sha256(artifact_path),
            "staged_article_count": payload.get("staged_article_count"),
            "queries": metrics.get("queries"),
            "target_present": metrics.get("target_present"),
            "top1_hits": metrics.get("top1_hits"),
            "mean_reciprocal_rank": metrics.get("mean_reciprocal_rank"),
            "max_target_rank": metrics.get("max_target_rank"),
            "source_rows_revalidated": revalidation.get("matched"),
        })
        all_queries.extend(queries)
    ranks = [int(row["target_rank"]) for row in all_queries if row.get("eligible_for_metric") and row.get("target_rank") is not None]
    target_present = sum(bool(row.get("target_present")) for row in all_queries)
    top1 = sum(int(row.get("target_rank") or 0) == 1 for row in all_queries)
    return {
        "schema_version": "wikipedia_staged_retrieval_baseline_v1",
        "created_utc": _utc_now(),
        "state": "VERIFIED",
        "interpretation": "Pre-change bounded semantic retrieval baseline only; not full-corpus quality, factual entailment, or persistent-index authority.",
        "windows": windows,
        "aggregate": {
            "windows": len(windows),
            "staged_articles": sum(int(row.get("staged_article_count") or 0) for row in windows),
            "queries": len(all_queries),
            "target_present": target_present,
            "top1_hits": top1,
            "target_presence_rate": round(target_present / len(all_queries), 6) if all_queries else 0.0,
            "top1_rate": round(top1 / len(all_queries), 6) if all_queries else 0.0,
            "mean_reciprocal_rank": round(sum(1.0 / rank for rank in ranks) / len(ranks), 6) if ranks else 0.0,
            "max_target_rank": max(ranks) if ranks else None,
            "source_rows_revalidated": sum(int(row.get("source_rows_revalidated") or 0) for row in windows),
        },
        "authority": {
            "vector_index_written": False,
            "carma_admission": False,
            "training_authorized": False,
            "run_authorized": False,
            "deployment_changed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(args.artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "state": result["state"], "aggregate": result["aggregate"], "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
