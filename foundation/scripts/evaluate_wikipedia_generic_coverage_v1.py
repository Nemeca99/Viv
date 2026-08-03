"""Evaluate bounded natural-language Wikipedia coverage without embeddings."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from lib.knowledge_external_adapters import LEGACY_WIKIPEDIA_ROOT, query_legacy_wikipedia


CASES = (
    ("What is autism?", "Autism"),
    ("What causes autism?", "Causes of autism"),
    ("What is photosynthesis?", "Photosynthesis"),
    ("Who was Albert Einstein?", "Albert Einstein"),
    ("What is evolution?", "Evolution"),
    ("What is quantum mechanics?", "Quantum mechanics"),
    ("What is artificial intelligence?", "Artificial intelligence"),
    ("What is a transformer?", "Transformer"),
    ("What is anarchism?", "Anarchism"),
    ("What is mathematics?", "Mathematics"),
    ("What is biology?", "Biology"),
    ("What is computer science?", "Computer science"),
    ("What was World War II?", "World War II"),
    ("What is machine learning?", "Machine learning"),
    ("What is a neural network?", "Neural network"),
    ("What is climate change?", "Climate change"),
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_check(path_text: str, expected_title: str) -> dict[str, object]:
    path = Path(path_text)
    result: dict[str, object] = {"path": str(path), "source_ok": False, "title_matches": False}
    try:
        path.resolve().relative_to(LEGACY_WIKIPEDIA_ROOT.resolve())
        if not path.is_file():
            result["error"] = "source_missing"
            return result
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"^\s*Title:\s*(.*?)\s*$", text, flags=re.I | re.M)
        actual_title = match.group(1).strip() if match else ""
        result.update(
            {
                "source_ok": True,
                "title_matches": actual_title.casefold() == expected_title.casefold(),
                "title": actual_title,
                "expected_title": expected_title,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    except (OSError, ValueError) as exc:
        result["error"] = f"{type(exc).__name__}:{exc}"
    return result


def evaluate() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for query, expected_title in CASES:
        result = query_legacy_wikipedia(query, limit=3, max_chars=512, resolve_redirects=True)
        sources = []
        for fact in result.get("facts") or []:
            source = fact.get("source") or {}
            path_text = str(source.get("path") or "")
            if path_text:
                sources.append(_source_check(path_text, expected_title))
        matched = any(bool(row.get("title_matches")) for row in sources)
        rows.append(
            {
                "query": query,
                "expected_title": expected_title,
                "retrieval_state": result.get("state"),
                "candidate_rows": result.get("candidate_rows", 0),
                "matched": matched,
                "source_checks": sources,
                "errors": result.get("errors", []),
            }
        )
    matched = sum(1 for row in rows if row["matched"])
    source_checks = [check for row in rows for check in row["source_checks"]]
    source_ok = sum(1 for check in source_checks if check.get("source_ok"))
    return {
        "schema_version": "wikipedia_generic_coverage_evaluation_v1",
        "created_utc": _utc(),
        "state": "VERIFIED",
        "coverage_state": "COMPLETE" if matched == len(rows) else "PARTIAL",
        "source_integrity_state": "VERIFIED" if source_ok == len(source_checks) else "HOLD",
        "scope": {
            "query_count": len(rows),
            "limit_per_query": 3,
            "max_chars_per_article": 512,
            "source_root": str(LEGACY_WIKIPEDIA_ROOT),
            "index_mode": "sqlite_read_only_structural_index_plus_complete_title_sidecar",
            "semantic_embeddings_used": False,
        },
        "metrics": {
            "queries": len(rows),
            "matched_expected_titles": matched,
            "coverage_rate": round(matched / max(1, len(rows)), 4),
            "source_checks": len(source_checks),
            "source_checks_passed": source_ok,
        },
        "authority": {
            "source_index_written": False,
            "title_sidecar_written": False,
            "vector_index_written": False,
            "carma_admission": False,
            "training_authorized": False,
            "run_authorized": False,
        },
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": payload["state"] == "VERIFIED", "coverage": payload["metrics"], "coverage_state": payload["coverage_state"], "source_integrity_state": payload["source_integrity_state"], "output": str(args.output)}, indent=2))
    return 0 if payload["state"] == "VERIFIED" and payload["source_integrity_state"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
