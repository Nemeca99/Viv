"""Evaluate a disjoint, read-only semantic query family over the verified shard."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from lib.knowledge_staged_adapter import query


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHARD = ROOT / "artifacts" / "auto" / "knowledge" / "wikipedia_semantic_shard_v1_20260803T114500Z.json"
CASES = (
    ("a theoretical physicist associated with the theory of relativity", "000105_Albert Einstein.txt"),
    ("observing celestial objects as a recreational activity", "000111_Amateur astronomy.txt"),
    ("a Semitic language used throughout the Arab world", "000141_Arabic.txt"),
    ("an inert noble gas used in lighting and industry", "000181_Argon.txt"),
    ("a nineteenth-century mathematician linked to early computing", "000217_Ada Lovelace.txt"),
    ("the major mountain system extending across central Europe", "000219_Alps.txt"),
    ("the proportion between the width and height of an image", "000244_Aspect ratio.txt"),
    ("a localized collection of pus caused by infection", "000251_Abscess.txt"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def evaluate(shard: Path) -> dict:
    payload = json.loads(shard.read_text(encoding="utf-8"))
    if payload.get("state") != "VERIFIED":
        raise ValueError("shard_not_verified")
    authority = payload.get("authority") or {}
    if any(bool(authority.get(key)) for key in ("vector_index_written", "persistent_index_written", "carma_admission", "training_authorized", "run_authorized")):
        raise ValueError("shard_authority_open")
    rows = []
    for text, target in CASES:
        result = query(text, artifact_path=shard, k=5, threshold=0.35)
        hits = result.get("hits") or []
        names = [str(hit.get("doc") or "") for hit in hits]
        rank = names.index(target) + 1 if target in names else None
        rows.append({
            "query": text,
            "target": target,
            "rank": rank,
            "target_present": rank is not None,
            "retrieval_state": result.get("state"),
            "hits": [{"doc": hit.get("doc"), "score": hit.get("score"), "ranking_score": hit.get("ranking_score")} for hit in hits],
            "evidence": result.get("evidence") or {},
        })
    present = sum(1 for row in rows if row["target_present"])
    top1 = sum(1 for row in rows if row["rank"] == 1)
    reciprocal = sum((1.0 / row["rank"]) if row["rank"] else 0.0 for row in rows) / len(rows)
    ranks = [row["rank"] for row in rows if row["rank"]]
    rejected = sum(len(row["evidence"].get("rejected") or {}) for row in rows)
    return {
        "schema_version": "wikipedia_semantic_disjoint_evaluation_v1",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "state": "VERIFIED" if rejected == 0 else "HOLD",
        "shard": {"path": str(shard).replace("\\", "/"), "sha256": _sha256(shard), "rows": len(payload.get("rows") or [])},
        "query_family": "disjoint_manual_paraphrases_v1",
        "metrics": {
            "queries": len(rows),
            "target_presence": f"{present}/{len(rows)}",
            "top1": f"{top1}/{len(rows)}",
            "mean_reciprocal_rank": round(reciprocal, 6),
            "max_rank": max(ranks) if ranks else None,
            "source_revalidation_rejections": rejected,
        },
        "authority": {
            "vector_index_written": False,
            "persistent_index_written": False,
            "carma_admission": False,
            "training_authorized": False,
            "run_authorized": False,
        },
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shard", type=Path, default=DEFAULT_SHARD)
    args = parser.parse_args()
    if os.environ.get("VIV_EMBED_BACKEND") != "hf_local":
        raise SystemExit("set VIV_EMBED_BACKEND=hf_local")
    result = evaluate(args.shard)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["state"] == "VERIFIED", "state": result["state"], "metrics": result["metrics"], "output": str(args.output)}, indent=2))
    return 0 if result["state"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
