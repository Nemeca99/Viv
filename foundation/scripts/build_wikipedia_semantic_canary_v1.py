#!/usr/bin/env python3
"""Build a bounded semantic retrieval canary from an immutable lexical pack."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.knowledge_semantic_backend import semantic_compare  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build(lexical_pack: Path, *, model_path: Path) -> dict:
    source = json.loads(lexical_pack.read_text(encoding="utf-8"))
    if source.get("state") != "VERIFIED":
        raise ValueError("lexical_pack_not_verified")
    os.environ["VIV_EMBED_BACKEND"] = "hf_local"
    os.environ["VIV_EMBED_MODEL_PATH"] = str(model_path)
    rows = []
    for row in source.get("rows", []):
        query = str(row.get("query") or "")
        sources = []
        for item in row.get("sources", []):
            content = str(item.get("content_prefix") or "")
            score = semantic_compare(query, content)
            sources.append(
                {
                    "path": item.get("path"),
                    "source_sha256": item.get("source_sha256"),
                    "observed_prefix_sha256": item.get("observed_prefix_sha256"),
                    "semantic_score": score,
                }
            )
        sources.sort(key=lambda value: float(value["semantic_score"].get("score", -1.0)), reverse=True)
        rows.append({"query": query, "sources": sources})
    scores = [
        float(source["semantic_score"]["score"])
        for row in rows
        for source in row["sources"]
        if source["semantic_score"].get("ok")
    ]
    return {
        "schema_version": "wikipedia_semantic_canary_v1",
        "created_utc": _utc_now(),
        "state": "VERIFIED" if scores else "INCONCLUSIVE",
        "semantic_backend": "huggingface_local",
        "model_path": str(model_path),
        "model_sha256": _sha256(model_path / "model.safetensors"),
        "lexical_pack": str(lexical_pack),
        "lexical_pack_sha256": _sha256(lexical_pack),
        "source_count": sum(len(row["sources"]) for row in rows),
        "rows": rows,
        "staged_only": True,
        "vector_index_written": False,
        "carma_admission": False,
        "training_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lexical-pack", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.model_path.is_dir() or not (args.model_path / "model.safetensors").is_file():
        raise SystemExit("embedding model path is not a local safetensors model")
    result = build(args.lexical_pack, model_path=args.model_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["state"] == "VERIFIED", "state": result["state"], "source_count": result["source_count"], "output": str(args.output), "vector_index_written": False, "carma_admission": False, "training_authorized": False}, indent=2))
    return 0 if result["state"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
