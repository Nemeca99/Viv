"""Build a reversible clean-text semantic shard from the verified read-only shard."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from lib.knowledge_semantic_backend import _local_embedding


ROOT = Path(__file__).resolve().parents[1]
WIKIPEDIA_ROOT = Path(r"F:\AI_Datasets\wikipedia_deduplicated")
DEFAULT_INPUT = ROOT / "artifacts" / "auto" / "knowledge" / "wikipedia_semantic_shard_v1_20260803T114500Z.json"
_TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _clean_preview(path: Path) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8", errors="replace")[:12000]
    title_match = re.search(r"^\s*Title:\s*(.*?)\s*$", raw, re.I | re.M)
    title = (title_match.group(1).strip() if title_match else path.stem)
    short_match = re.search(r"\{\{Short description\|([^{}]+)\}\}", raw, re.I)
    short = short_match.group(1).strip() if short_match else ""
    body = raw.split("\n", 2)[-1]
    body = re.sub(r"^\s*#REDIRECT.*$", "", body, flags=re.I | re.M)
    body = _TEMPLATE_RE.sub(" ", body)
    body = _LINK_RE.sub(lambda m: m.group(2) or m.group(1), body)
    body = _TAG_RE.sub(" ", body)
    body = re.sub(r"'{2,}", "", body)
    body = re.sub(r"\s+", " ", body).strip()
    clean = f"Title: {title}. {short}. {body[:1800]}".strip()
    return clean, hashlib.sha256(clean.encode("utf-8")).hexdigest()


def build(source: Path) -> dict:
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("state") != "VERIFIED":
        raise ValueError("source_shard_not_verified")
    authority = payload.get("authority") or {}
    if any(bool(authority.get(k)) for k in ("vector_index_written", "persistent_index_written", "carma_admission", "training_authorized", "run_authorized")):
        raise ValueError("source_shard_authority_open")
    rows = []
    for original in payload.get("rows") or []:
        path = Path(str(original.get("path") or ""))
        try:
            path.resolve().relative_to(WIKIPEDIA_ROOT.resolve())
        except (OSError, ValueError) as exc:
            raise ValueError(f"source_outside_root:{path}") from exc
        if not path.is_file() or _sha256(path) != str(original.get("source_sha256") or "").lower():
            raise ValueError(f"source_hash_mismatch:{path}")
        clean, clean_sha256 = _clean_preview(path)
        row = dict(original)
        row["embedding"] = [float(v) for v in _local_embedding(clean)]
        row["embedding_dimensions"] = len(row["embedding"])
        row["embedding_representation"] = "verified_title_short_description_clean_opening_v1"
        row["clean_preview_sha256"] = clean_sha256
        rows.append(row)
    return {
        "schema_version": "wikipedia_semantic_shard_clean_v1",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "state": "VERIFIED",
        "source_shard": {"path": str(source).replace("\\", "/"), "sha256": _sha256(source), "rows": len(payload.get("rows") or [])},
        "rows": rows,
        "authority": {"vector_index_written": False, "persistent_index_written": False, "carma_admission": False, "training_authorized": False, "run_authorized": False},
        "interpretation": "Reversible read-only comparison shard; clean source representation, not persistent index or training authority.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "state": result["state"], "rows": len(result["rows"]), "output": str(args.output), "authority": result["authority"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
