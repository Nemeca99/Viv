#!/usr/bin/env python3
"""Bounded CPU-local semantic-overlap screening for staged Wikipedia and V104 rows.

This is a screening instrument, not a proof of semantic independence. It records
the encoder, thresholds, nearest pairs, and source hashes; it never admits an
index or changes training authority.
"""
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
from lib.triad_kernel import TRIAD_CONTRACT_VERSION  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = math.sqrt(sum(float(a) * float(a) for a in left))
    right_norm = math.sqrt(sum(float(b) * float(b) for b in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else float("nan")


def _load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate(artifacts: list[Path], train_path: Path, holdout_path: Path, model_path: Path, review_threshold: float, high_threshold: float) -> dict:
    staged: list[dict] = []
    artifact_hashes = []
    seen_paths: set[str] = set()
    for artifact_path in artifacts:
        artifact_hashes.append({"path": str(artifact_path), "sha256": _sha256(artifact_path)})
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        if artifact.get("state") != "VERIFIED":
            raise ValueError(f"artifact_not_verified:{artifact_path}")
        for row in artifact.get("rows", []):
            path = str(row["path"])
            if path.casefold() in seen_paths:
                continue
            seen_paths.add(path.casefold())
            source = Path(path)
            text = source.read_text(encoding="utf-8", errors="replace")[:12000]
            staged.append({"path": path, "text": text[:2048], "source_sha256": _sha256(source)})

    train_rows = _load_rows(train_path)
    holdout_rows = _load_rows(holdout_path)
    references: list[dict] = []
    for split, rows in (("train", train_rows), ("holdout", holdout_rows)):
        for row in rows:
            text = _norm(" ".join(str(row.get(key) or "") for key in ("ask", "response", "source_chosen")))
            references.append({"split": split, "example_id": row.get("example_id"), "text": text})

    os.environ["VIV_EMBED_BACKEND"] = "hf_local"
    os.environ["VIV_EMBED_MODEL_PATH"] = str(model_path)
    staged_vectors = [_local_embedding(row["text"]) for row in staged]
    reference_vectors = [_local_embedding(row["text"]) for row in references]
    nearest: list[dict] = []
    for staged_row, staged_vector in zip(staged, staged_vectors):
        best = max(
            (
                (_cosine(staged_vector, reference_vector), reference)
                for reference, reference_vector in zip(references, reference_vectors)
            ),
            key=lambda item: item[0],
        )
        score, reference = best
        nearest.append({
            "source_path": staged_row["path"],
            "source_sha256": staged_row["source_sha256"],
            "split": reference["split"],
            "example_id": reference["example_id"],
            "cosine": round(float(score), 6),
            "screening_state": "HIGH_REVIEW" if score >= high_threshold else ("REVIEW" if score >= review_threshold else "LOW"),
        })
    nearest.sort(key=lambda row: row["cosine"], reverse=True)
    high = [row for row in nearest if row["cosine"] >= high_threshold]
    review = [row for row in nearest if row["cosine"] >= review_threshold]
    return {
        "schema_version": "wikipedia_training_semantic_overlap_v1",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "triad_contract_version": TRIAD_CONTRACT_VERSION,
        "state": "VERIFIED",
        "screening_decision": "HIGH_REVIEW_REQUIRED" if high else ("REVIEW_REQUIRED" if review else "NO_THRESHOLD_HIT"),
        "encoder": {"path": str(model_path), "model_sha256": _sha256(model_path / "model.safetensors"), "dimensions": 384},
        "thresholds": {"review": review_threshold, "high_review": high_threshold},
        "staged_unique_paths": len(staged),
        "train_rows": len(train_rows),
        "holdout_rows": len(holdout_rows),
        "review_count": len(review),
        "high_review_count": len(high),
        "nearest_pairs_top20": nearest[:20],
        "artifact_hashes": artifact_hashes,
        "train_sha256": _sha256(train_path),
        "holdout_sha256": _sha256(holdout_path),
        "semantic_overlap_interpretation": "CPU-local embedding screen only; nearest-pair flags require human/CPU semantic adjudication and do not prove leakage or authorize admission.",
        "authority": {"vector_index_written": False, "carma_admission": False, "training_authorized": False, "run_authorized": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, action="append", required=True)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--review-threshold", type=float, default=0.70)
    parser.add_argument("--high-threshold", type=float, default=0.85)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.artifact, args.train, args.holdout, args.model_path, args.review_threshold, args.high_threshold)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "state": result["state"], "screening_decision": result["screening_decision"], "review_count": result["review_count"], "high_review_count": result["high_review_count"], "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
