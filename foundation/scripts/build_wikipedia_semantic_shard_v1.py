"""Combine verified Wikipedia canary windows into one read-only semantic shard."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "auto" / "knowledge"
DEFAULT_INPUTS = tuple(sorted(set(
    KNOWLEDGE_DIR.glob("wikipedia_32_article_canary_v1_manifest_bound_offset*.json")
).union(
    KNOWLEDGE_DIR.glob("wikipedia_32_article_canary_v1_offset96_*.json")
).union(
    KNOWLEDGE_DIR.glob("wikipedia_32_article_canary_v1_20260803T000000Z.json")
)))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(inputs: tuple[Path, ...]) -> dict:
    if not inputs:
        raise ValueError("no_canary_inputs")
    rows: list[dict] = []
    seen: set[str] = set()
    input_records = []
    for path in inputs:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("state") != "VERIFIED":
            raise ValueError(f"canary_not_verified:{path.name}")
        if payload.get("staged_only") is not True or payload.get("vector_index_written") is not False or payload.get("training_authorized") is not False:
            raise ValueError(f"canary_authority_open:{path.name}")
        for row in payload.get("rows") or []:
            key = str(row.get("path") or "").casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            rows.append(dict(row))
        input_records.append({"path": str(path).replace("\\", "/"), "sha256": _sha256(path), "rows": len(payload.get("rows") or [])})
    return {
        "schema_version": "wikipedia_semantic_shard_v1",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "state": "VERIFIED",
        "source": "verified_manifest_bound_canaries",
        "rows": rows,
        "input_artifacts": input_records,
        "authority": {
            "vector_index_written": False,
            "persistent_index_written": False,
            "carma_admission": False,
            "training_authorized": False,
            "run_authorized": False,
        },
        "interpretation": "Bounded read-only semantic shard; not full-corpus semantic coverage or training authority.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input", type=Path, action="append")
    args = parser.parse_args()
    inputs = tuple(args.input) if args.input else DEFAULT_INPUTS
    payload = build(inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "state": payload["state"], "rows": len(payload["rows"]), "output": str(args.output), "authority": payload["authority"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
