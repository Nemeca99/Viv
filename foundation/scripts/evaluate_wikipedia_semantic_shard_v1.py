"""Evaluate the bounded read-only semantic shard against verified query packs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from lib.knowledge_staged_adapter import query


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = ROOT / "artifacts" / "auto" / "knowledge"
DEFAULT_SHARD = KNOWLEDGE_DIR / "wikipedia_semantic_shard_v1_20260803T114500Z.json"
DEFAULT_PACKS = tuple(sorted(KNOWLEDGE_DIR.glob("wikipedia_staged_manifest_query_pack_offset*.json")))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_queries(packs: tuple[Path, ...]) -> list[dict]:
    rows = []
    for path in packs:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload:
            rows.append({**row, "query_pack": str(path).replace("\\", "/"), "query_pack_sha256": _sha256(path)})
    return rows


def evaluate(shard: Path, packs: tuple[Path, ...], *, k: int = 5, threshold: float = 0.35) -> dict:
    queries = _load_queries(packs)
    rows = []
    for row in queries:
        result = query(row["query"], artifact_path=shard, k=k, threshold=threshold)
        target = Path(row["target_path"]).name
        hits = result.get("hits") or []
        names = [str(hit.get("doc") or "") for hit in hits]
        rank = names.index(target) + 1 if target in names else None
        rows.append(
            {
                "query": row["query"],
                "target": target,
                "rank": rank,
                "target_present": rank is not None,
                "retrieval_state": result.get("state"),
                "hits": [{"doc": hit.get("doc"), "score": hit.get("score"), "ranking_score": hit.get("ranking_score")} for hit in hits],
                "evidence": result.get("evidence") or {},
            }
        )
    present = sum(1 for row in rows if row["target_present"])
    top1 = sum(1 for row in rows if row["rank"] == 1)
    reciprocal = sum((1.0 / row["rank"]) if row["rank"] else 0.0 for row in rows) / max(1, len(rows))
    ranks = [row["rank"] for row in rows if row["rank"]]
    source_verified = all(not (row["evidence"].get("rejected") or {}) for row in rows)
    return {
        "schema_version": "wikipedia_semantic_shard_evaluation_v1",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "state": "VERIFIED" if source_verified else "HOLD",
        "shard": {"path": str(shard).replace("\\", "/"), "sha256": _sha256(shard), "rows": len(json.loads(shard.read_text(encoding="utf-8")).get("rows") or [])},
        "query_packs": [{"path": str(path).replace("\\", "/"), "sha256": _sha256(path)} for path in packs],
        "metrics": {"queries": len(rows), "target_presence": f"{present}/{len(rows)}", "top1": f"{top1}/{len(rows)}", "mean_reciprocal_rank": round(reciprocal, 6), "max_rank": max(ranks) if ranks else None, "source_revalidation_rejections": sum(len(row["evidence"].get("rejected") or {}) for row in rows)},
        "authority": {"vector_index_written": False, "persistent_index_written": False, "carma_admission": False, "training_authorized": False, "run_authorized": False},
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shard", type=Path, default=DEFAULT_SHARD)
    args = parser.parse_args()
    if os.environ.get("VIV_EMBED_BACKEND") != "hf_local":
        raise SystemExit("set VIV_EMBED_BACKEND=hf_local")
    payload = evaluate(args.shard, DEFAULT_PACKS)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": payload["state"] == "VERIFIED", "state": payload["state"], "metrics": payload["metrics"], "output": str(args.output)}, indent=2))
    return 0 if payload["state"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
