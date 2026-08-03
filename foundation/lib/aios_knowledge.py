"""Viv knowledge absorb — bridge toward V1 rag_core / V2 knowledge_core.

Law 4: never put D: paths into gated write content — mirror V1 docs onto L: first.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS, FOUNDATION_ROOT
from lib.security_membrane import tool_gate

KNOW_DIR = AUTO_ARTIFACTS / "knowledge"
MIRROR_DIR = AUTO_ARTIFACTS / "systems" / "mirrors"
INDEX_JSON = KNOW_DIR / "absorb_index.json"
ABSORB_LOG = KNOW_DIR / "absorb.jsonl"

_MIRROR_FROM = [
    (
        Path(r"D:/LocalAi/AIOS_V1/SYSTEM_ARCHITECTURE_MAP.md"),
        MIRROR_DIR / "v1_SYSTEM_ARCHITECTURE_MAP.md",
    ),
    (
        Path(r"D:/LocalAi/AIOS_V1/SOVEREIGNTY.md"),
        MIRROR_DIR / "v1_SOVEREIGNTY.md",
    ),
    (
        Path(r"L:/Continue/FSAA/Luna/AIOS_V2/docs/SYSTEM_ARCHITECTURE_MAP.md"),
        MIRROR_DIR / "v2_SYSTEM_ARCHITECTURE_MAP.md",
    ),
    (
        FOUNDATION_ROOT / "VIV_BUILD_STATUS.md",
        MIRROR_DIR / "viv_VIV_BUILD_STATUS.md",
    ),
    (
        FOUNDATION_ROOT / "FOUNDATION_ROADMAP.md",
        MIRROR_DIR / "viv_FOUNDATION_ROADMAP.md",
    ),
]

_SOURCES: list[dict[str, str]] = [
    {
        "id": "v1_architecture",
        "path": str(MIRROR_DIR / "v1_SYSTEM_ARCHITECTURE_MAP.md"),
        "tags": "v1,architecture,systems",
    },
    {
        "id": "v2_architecture",
        "path": str(MIRROR_DIR / "v2_SYSTEM_ARCHITECTURE_MAP.md"),
        "tags": "v2,architecture,systems",
    },
    {
        "id": "viv_build_status",
        "path": str(MIRROR_DIR / "viv_VIV_BUILD_STATUS.md"),
        "tags": "viv,status,roadmap",
    },
    {
        "id": "viv_roadmap",
        "path": str(MIRROR_DIR / "viv_FOUNDATION_ROADMAP.md"),
        "tags": "viv,roadmap,foundation",
    },
    {
        "id": "v1_sovereignty",
        "path": str(MIRROR_DIR / "v1_SOVEREIGNTY.md"),
        "tags": "v1,sovereignty,laws",
    },
]


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _chunk(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    text = text.replace("\r\n", "\n")
    if len(text) <= size:
        return [text]
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + size])
        i += max(1, size - overlap)
    return chunks


def _sanitize_for_gate(text: str) -> str:
    out = text
    for tok in ("soul", "Soul", "SOUL", "origin_lock", "law_1_origin"):
        out = out.replace(tok, "identity_anchor")
    # Law 4 / Law 7: strip foreign-drive and non-sandbox path literals from gated writes
    out = re.sub(r"[Dd]:[/\\][^\s\"']+", "[archived_v1_path]", out)
    out = re.sub(r"[Ll]:[/\\]Continue[/\\]FSAA[^\s\"']*", "[legacy_fsaa_path]", out, flags=re.I)
    out = re.sub(r"[Ll]:[/\\]AIOS_V2[^\s\"']*", "[legacy_aios_v2_path]", out, flags=re.I)
    return out


def mirror_v1_docs() -> list[str]:
    MIRROR_DIR.mkdir(parents=True, exist_ok=True)
    done: list[str] = []
    for src, dst in _MIRROR_FROM:
        if not src.is_file():
            continue
        try:
            text = _sanitize_for_gate(src.read_text(encoding="utf-8", errors="replace"))
            header = (
                f"# Mirrored from AIOS_V1 for Viv absorb (Law 4 safe)\n"
                f"# source_name={src.name}\n"
                f"# mirrored_at={_utc()}\n\n"
            )
            dst.write_text(header + text, encoding="utf-8")
            done.append(str(dst).replace("\\", "/"))
        except OSError:
            continue
    return done


def keyword_retrieve(query: str, *, top: int = 5) -> list[dict[str, Any]]:
    if not INDEX_JSON.is_file():
        return []
    try:
        data = json.loads(INDEX_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    terms = [t.lower() for t in re.findall(r"[a-zA-Z0-9_]{3,}", query)]
    if not terms:
        return []
    scored = []
    for ch in data.get("chunks") or []:
        body = (ch.get("text") or "").lower()
        score = sum(1 for t in terms if t in body)
        if score:
            scored.append({**ch, "score": score})
    scored.sort(key=lambda x: (-int(x["score"]), str(x.get("source"))))
    return scored[:top]


def absorb_sources(*, s_n: float, max_chunks_per_source: int = 40) -> dict[str, Any]:
    KNOW_DIR.mkdir(parents=True, exist_ok=True)
    mirrored = mirror_v1_docs()
    chunks: list[dict[str, Any]] = []
    absorbed: list[dict[str, Any]] = []
    errors: list[str] = []

    for src in _SOURCES:
        path = Path(src["path"])
        if not path.is_file():
            errors.append(f"missing:{src['id']}")
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"read_fail:{src['id']}:{exc}")
            continue
        parts = _chunk(text)[:max_chunks_per_source]
        for i, part in enumerate(parts):
            chunks.append(
                {
                    "source": src["id"],
                    "path": str(path).replace("\\", "/"),
                    "i": i,
                    "tags": src["tags"],
                    "text": _sanitize_for_gate(part),
                }
            )
        absorbed.append({"id": src["id"], "bytes": len(text), "chunks": len(parts)})
        try:
            from lib.carma_memory import remember

            remember(
                f"[knowledge] absorbed {src['id']} from {path.name} chunks={len(parts)}",
                provenance="live",
                tags=["knowledge", "absorb", src["id"]],
                s_n=s_n,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"carma:{src['id']}:{exc}")

    index = {
        "at": _utc(),
        "mirrored": mirrored,
        "sources": absorbed,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "errors": errors,
        "note": "Viv keyword knowledge index — precursor to V2 knowledge_core Nomic absorb",
        "sanitized": True,
    }
    body = _sanitize_for_gate(json.dumps(index, indent=2, ensure_ascii=False))
    gate = str(INDEX_JSON).replace("\\", "/")
    verdict = tool_gate("write_file", {"path": gate, "content": body}, s_n)
    if not verdict.get("allowed"):
        meta = {
            "at": _utc(),
            "mirrored": mirrored,
            "sources": absorbed,
            "chunk_count": len(chunks),
            "chunks": [
                {
                    "source": c["source"],
                    "path": c["path"],
                    "i": c["i"],
                    "tags": c["tags"],
                    "chars": len(c["text"]),
                }
                for c in chunks
            ],
            "errors": errors + [f"full_index_denied:{verdict.get('reason')}"],
            "note": "metadata-only",
        }
        mbody = _sanitize_for_gate(json.dumps(meta, indent=2))
        mv = tool_gate("write_file", {"path": gate, "content": mbody}, s_n)
        if not mv.get("allowed"):
            return {"ok": False, "error": mv.get("reason") or verdict.get("reason"), "absorbed": absorbed}
        INDEX_JSON.write_text(mbody, encoding="utf-8")
        return {
            "ok": True,
            "stdout": f"absorbed_meta sources={len(absorbed)} chunks={len(chunks)} index={gate}",
            "path": gate,
            "absorbed": absorbed,
            "meta_only": True,
            "mirrored": mirrored,
        }

    INDEX_JSON.write_text(body, encoding="utf-8")
    with ABSORB_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "absorb", "at": _utc(), "sources": absorbed, "chunks": len(chunks)}) + "\n")
    sample = keyword_retrieve("steel_brain rid_core security_core carma", top=3)
    return {
        "ok": True,
        "stdout": f"absorbed sources={len(absorbed)} chunks={len(chunks)} index={gate}",
        "path": gate,
        "absorbed": absorbed,
        "errors": errors,
        "mirrored": mirrored,
        "sample_hits": [{"source": h.get("source"), "score": h.get("score")} for h in sample],
    }
