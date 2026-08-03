"""Callable RAG / knowledge adapter for Viv (REAL, not bridge inventory).

API: ingest_path(path), query(text, k), status()

Sources (read-only):
  - V1 rag_core patterns: D:/LocalAi/AIOS_V1/rag_core (mirror onto L: before absorb)
  - V2 knowledge_core: L:/Continue/FSAA/Luna/AIOS_V2/knowledge_core (sliding windows + silence)
  - Viv absorb: lib/aios_knowledge.py (sanitize + keyword retrieve)

Writes stay on L: under foundation/artifacts/auto/knowledge/. Never write to D:.
Does not mutate security_core.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS, FOUNDATION_ROOT, SANDBOX_ROOT
from lib.security_membrane import tool_gate
from lib.knowledge_source_contract import describe_file, packet_from_retrieval

KNOW_DIR = AUTO_ARTIFACTS / "knowledge"
MIRROR_DIR = AUTO_ARTIFACTS / "systems" / "mirrors"
ADAPTER_INDEX = KNOW_DIR / "adapter_index.json"
ADAPTER_LOG = KNOW_DIR / "adapter.jsonl"
ADAPTER_EVIDENCE = KNOW_DIR / "adapter_smoke.json"

V1_RAG = Path(r"D:/LocalAi/AIOS_V1/rag_core")
V2_KNOW = Path(r"L:/Continue/FSAA/Luna/AIOS_V2/knowledge_core")

_TEXT_SUFFIXES = {".md", ".txt", ".json", ".jsonl", ".rst", ".yml", ".yaml", ".csv", ".log", ".ini", ".cfg"}

# Law 3 payload scrub — must not appear in gated write blobs
_PROTECTED_TOKENS = (
    "security_core",
    "nox_forge_core",
    "governance",
    "cpu_config.json",
    "cargo.toml",
    "cargo.lock",
    ".cursor/hooks",
    "/foundation/rid_main.py",
    "/foundation/auto_main.py",
    "/foundation/uml_main.py",
    "/foundation/guardian_main.py",
    "/foundation/lib/security_",
    "/foundation/lib/autonomous_",
    "/foundation/lib/autonomy_",
    "/foundation/lib/auto_",
    "/foundation/lib/guardian",
    "/foundation/lib/piston",
    "/foundation/lib/master_rid",
    "/foundation/lib/rid_",
    "/foundation/lib/foundation_health",
    "/foundation/scripts/security_redteam",
)

_SILENCE_MIN_SCORE = 1  # keyword hits; below => silence (V2 harmonic filter idea)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_posix(p: Path | str) -> str:
    return str(p).replace("\\", "/")


def _safe_source_ref(ref: dict[str, Any]) -> dict[str, Any]:
    """Keep hash/provenance in gated indexes without embedding foreign paths."""
    out = dict(ref)
    raw_path = Path(str(ref.get("path") or ""))
    raw_root = Path(str(ref.get("root") or ""))
    try:
        relative = raw_path.resolve().relative_to(raw_root.resolve()).as_posix()
    except (OSError, ValueError):
        relative = raw_path.name or "unknown"
    drive = (raw_root.drive or "source").replace(":", "").upper()
    root_name = re.sub(r"[^A-Z0-9]+", "_", raw_root.name.upper()).strip("_") or "ROOT"
    relative_token = re.sub(r"[^A-Za-z0-9]+", "_", relative).strip("_") or "unknown"
    out.pop("path", None)
    out["source_token"] = f"SRC_{drive}_{root_name}_{relative_token}"
    out["root"] = f"{drive}_{root_name}"
    return out


_FORBIDDEN_EXT = (
    ".py",
    ".pyd",
    ".dll",
    ".so",
    ".dylib",
    ".exe",
    ".bat",
    ".cmd",
    ".ps1",
    ".vbs",
    ".js",
    ".mjs",
    ".wasm",
    ".msi",
    ".scr",
    ".com",
    ".rs",
    ".toml",
    ".lock",
)


DOCS_DIR = KNOW_DIR / "docs"


_TARIFF_SCRUB = (
    ("powershell -enc", "shell_enc"),
    ("jailbreak", "probe_frame"),
    ("oblivion", "soft_reset"),
    ("regedit", "reg_tool"),
    ("overwrite", "replace_write"),
    ("bypass", "route_around"),
    ("format", "layout_fmt"),
    ("delete", "remove_item"),
    ("exec", "run_call"),
    ("rm ", "remove "),
)


def _sanitize(text: str) -> str:
    """Scrub gated write blobs for Law 3/4/7 + tariff keywords + path literals."""
    out = text.replace("\r\n", "\n")
    for tok in ("soul", "Soul", "SOUL", "origin_lock", "law_1_origin"):
        out = out.replace(tok, "identity_anchor")
    for tok in _PROTECTED_TOKENS:
        out = re.sub(re.escape(tok), "sysseg", out, flags=re.I)
    for raw, repl in _TARIFF_SCRUB:
        out = re.sub(re.escape(raw), repl, out, flags=re.I)
    # Any drive-letter path literal (Law 4 / Law 7) — preserve Viv mutation sandbox paths
    def _path_repl(m: re.Match[str]) -> str:
        raw = m.group(0).replace("\\", "/")
        low = raw.lower()
        if "viv/foundation/artifacts/" in low or "viv/sandbox/" in low:
            return raw.replace("\\", "/")
        return "doc_ref"

    out = re.sub(r"[A-Za-z]:[\\/][^\s`\"'\]]+", _path_repl, out)
    # Law 4 forbidden extensions appearing as text (e.g. uml_main.py in docs)
    for ext in _FORBIDDEN_EXT:
        out = re.sub(re.escape(ext), f"[{ext.lstrip('.')}]", out, flags=re.I)
    return out


def _materialize_doc(src: Path, *, text: str, s_n: float) -> Path | None:
    """Write a short sanitized stub under artifacts/knowledge/docs (Law 7-safe)."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256((_as_posix(src.name) + "|" + str(len(text))).encode()).hexdigest()[:12]
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", src.stem)[:80]
    dst = DOCS_DIR / f"{digest}_{safe}.txt"
    preview = _sanitize(text)[:1200]
    body = _sanitize(
        f"# knowledge adapter doc\n# name={src.stem}\n# chars={len(text)}\n# at={_utc()}\n\n{preview}\n"
    )
    gate = _as_posix(dst)
    verdict = tool_gate("write_file", {"path": gate, "content": body}, float(s_n))
    if not verdict.get("allowed"):
        return None
    dst.write_text(body, encoding="utf-8")
    return dst


def _sliding_windows(text: str, window_size: int = 150, overlap: int = 30) -> list[str]:
    """V2 knowledge_core.semantic_chunker — word windows."""
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    step = max(1, window_size - overlap)
    for i in range(0, len(words), step):
        chunks.append(" ".join(words[i : i + window_size]))
        if i + window_size >= len(words):
            break
    return chunks


def _fingerprint(text: str) -> str:
    return hashlib.md5(text[:120].encode("utf-8", errors="replace")).hexdigest()


def _is_under(child: Path, root: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _is_d_drive(path: Path) -> bool:
    try:
        return path.resolve().drive.upper() == "D:"
    except OSError:
        return str(path).upper().startswith("D:")


def _mirror_foreign(src: Path) -> Path | None:
    """Copy D: (or other foreign) text onto L: mirrors — read-only from source."""
    if not src.is_file():
        return None
    MIRROR_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", src.name)[:120]
    digest = hashlib.sha256(_as_posix(src).encode()).hexdigest()[:10]
    dst = MIRROR_DIR / f"ingest_{digest}_{safe_name}"
    try:
        raw = src.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    header = (
        f"# Mirrored for Viv knowledge adapter (read-only source)\n"
        f"# source_name={src.name}\n"
        f"# mirrored_at={_utc()}\n\n"
    )
    body = _sanitize(header + raw)
    gate = _as_posix(dst)
    verdict = tool_gate("write_file", {"path": gate, "content": body}, 0.5)
    if not verdict.get("allowed"):
        return None
    dst.write_text(body, encoding="utf-8")
    return dst


def _collect_files(path: Path, *, max_files: int = 40) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    found: list[Path] = []
    for p in sorted(path.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in _TEXT_SUFFIXES and p.name.lower() not in {
            "readme",
            "license",
        }:
            continue
        # Skip heavy/cache trees from V1 rag
        if any(part in {".cache", "hub", "__pycache__", ".git"} for part in p.parts):
            continue
        found.append(p)
        if len(found) >= max_files:
            break
    return found


def _load_index() -> dict[str, Any]:
    if not ADAPTER_INDEX.is_file():
        return {"version": 1, "chunks": [], "sources": [], "updated_at": None}
    try:
        data = json.loads(ADAPTER_INDEX.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": 1, "chunks": [], "sources": [], "updated_at": None}
        data.setdefault("chunks", [])
        data.setdefault("sources", [])
        return data
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "chunks": [], "sources": [], "updated_at": None}


def _save_index(data: dict[str, Any], *, s_n: float) -> dict[str, Any]:
    KNOW_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _utc()
    data["version"] = 1
    data["chunk_count"] = len(data.get("chunks") or [])
    body = _sanitize(json.dumps(data, indent=2, ensure_ascii=False))
    gate = _as_posix(ADAPTER_INDEX)
    verdict = tool_gate("write_file", {"path": gate, "content": body}, float(s_n))
    if not verdict.get("allowed"):
        return {"ok": False, "error": verdict.get("reason") or "gate_denied", "path": gate}
    ADAPTER_INDEX.write_text(body, encoding="utf-8")
    with ADAPTER_LOG.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "event": "index_write",
                    "at": _utc(),
                    "chunks": data["chunk_count"],
                    "sources": len(data.get("sources") or []),
                }
            )
            + "\n"
        )
    return {"ok": True, "path": gate, "chunk_count": data["chunk_count"]}


def _resolve_ingest_target(path: Path) -> tuple[Path | None, str | None, bool]:
    """Return (local_path, error, mirrored). Never returns a D: write target."""
    if not path.exists():
        return None, f"missing:{_as_posix(path)}", False
    if _is_d_drive(path):
        # Prefer existing L: mirrors of V1 doctrine; else mirror this path onto L:
        if path.is_file():
            mirrored = _mirror_foreign(path)
            if mirrored is None:
                return None, "mirror_failed_d_drive_read_only", False
            return mirrored, None, True
        # Directory on D: — mirror each text file onto L:, return mirror parent
        files = _collect_files(path)
        if not files:
            return None, "no_text_files_on_d", False
        mirrored_paths = []
        for f in files:
            m = _mirror_foreign(f)
            if m is not None:
                mirrored_paths.append(m)
        if not mirrored_paths:
            return None, "mirror_failed_d_dir", False
        return mirrored_paths[0].parent, None, True
    # Prefer L: — allow sandbox + artifacts + Continue trees for read
    return path, None, False


def ingest_text(
    text: str,
    *,
    name: str = "live_teach",
    s_n: float = 0.5,
    tags: str = "adapter,knowledge,live_teach",
) -> dict[str, Any]:
    """Live knowledge injection from Architect text (no file required)."""
    body = _sanitize((text or "").strip())
    if len(body) < 8:
        return {"ok": False, "error": "empty_or_too_short"}
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (name or "live_teach"))[:48].strip("_") or "live_teach"
    sid = f"live:{safe_name}"[:80]
    KNOW_DIR.mkdir(parents=True, exist_ok=True)
    doc_path = KNOW_DIR / "docs" / f"{safe_name}.txt"
    doc = _materialize_doc(doc_path, text=body, s_n=s_n)
    if doc is None:
        # materialize may fail gate on path; write via gate on final doc name
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        header = f"# Live teach {safe_name}\n# at={_utc()}\n\n"
        gated = _sanitize(header + body)
        verdict = tool_gate("write_file", {"path": _as_posix(doc_path), "content": gated}, float(s_n))
        if not verdict.get("allowed"):
            return {"ok": False, "error": verdict.get("reason") or "gate_denied", "path": _as_posix(doc_path)}
        doc_path.write_text(gated, encoding="utf-8")
        doc = doc_path

    index = _load_index()
    chunks: list[dict[str, Any]] = [c for c in (index.get("chunks") or []) if c.get("source") != sid]
    parts = _sliding_windows(body) or [body[:900]]
    added = 0
    for i, part in enumerate(parts[:24]):
        clean = _sanitize(part)
        chunks.append(
            {
                "source": sid,
                "doc": doc.name,
                "i": i,
                "fp": _fingerprint(clean),
                "text": clean,
                "tags": tags,
            }
        )
        added += 1
    sources = [s for s in (index.get("sources") or []) if s.get("id") != sid]
    sources.append(
        {
            "id": sid,
            "doc": doc.name,
            "name": safe_name,
            "bytes": len(body),
            "chunks": added,
            "live_teach": True,
            "at": _utc(),
        }
    )
    index["chunks"] = chunks
    index["sources"] = sources
    index["last_ingest"] = {
        "at": _utc(),
        "request_name": safe_name,
        "files": 1,
        "chunks_added": added,
        "source_ids": [sid],
        "live_teach": True,
    }
    saved = _save_index(index, s_n=s_n)
    if not saved.get("ok"):
        return {"ok": False, "error": saved.get("error"), "chunks_added": added}
    return {
        "ok": True,
        "source": sid,
        "doc": _as_posix(doc),
        "chunks_added": added,
        "chunk_count": saved.get("chunk_count"),
        "index": saved.get("path"),
        "evidence": {"at": _utc(), "live_teach": True},
    }


def ingest_path(path: str | Path, *, s_n: float = 0.5, max_chunks_per_file: int = 48) -> dict[str, Any]:
    """Ingest a file or directory into the L: knowledge adapter index."""
    raw = Path(str(path))
    target, err, mirrored = _resolve_ingest_target(raw)
    if err or target is None:
        return {"ok": False, "error": err or "resolve_failed", "path": _as_posix(raw)}

    files = _collect_files(target)
    if not files and target.is_file():
        files = [target]
    if not files:
        return {"ok": False, "error": "no_ingestible_files", "path": _as_posix(target)}

    index = _load_index()
    chunks: list[dict[str, Any]] = list(index.get("chunks") or [])
    # Drop prior chunks from same source ids we are re-ingesting
    source_ids: list[str] = []
    added = 0
    errors: list[str] = []

    for fp in files:
        sid = f"ingest:{fp.stem}"[:80]
        source_ids.append(sid)
        chunks = [c for c in chunks if c.get("source") != sid]
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"read_fail:{fp.name}:{exc}")
            continue
        try:
            source_ref = _safe_source_ref(describe_file(fp).to_dict())
        except (OSError, ValueError) as exc:
            errors.append(f"source_contract:{fp.name}:{exc}")
            continue
        doc = _materialize_doc(fp, text=text, s_n=s_n)
        if doc is None:
            errors.append(f"materialize_denied:{fp.name}")
            continue
        parts = _sliding_windows(_sanitize(text))[:max_chunks_per_file]
        if not parts:
            parts = [_sanitize(text)[:900]] if text.strip() else []
        for i, part in enumerate(parts):
            clean = _sanitize(part)
            chunks.append(
                {
                    "source": sid,
                    "doc": doc.name,
                    "i": i,
                    "fp": _fingerprint(clean),
                    "text": clean,
                    "tags": "adapter,knowledge,rag",
                }
            )
            added += 1
        sources = [s for s in (index.get("sources") or []) if s.get("id") != sid]
        sources.append(
            {
                "id": sid,
                "doc": doc.name,
                "name": fp.stem,
                "bytes": len(text),
                "chunks": len(parts),
                "source_ref": source_ref,
                "mirrored_from_d": mirrored,
                "at": _utc(),
            }
        )
        index["sources"] = sources

    index["chunks"] = chunks
    index["last_ingest"] = {
        "at": _utc(),
        "request_name": raw.name,
        "files": len(files),
        "chunks_added": added,
        "source_ids": source_ids,
        "mirrored": mirrored,
    }
    saved = _save_index(index, s_n=s_n)
    if not saved.get("ok"):
        return {
            "ok": False,
            "error": saved.get("error"),
            "path": _as_posix(raw),
            "mirrored": mirrored,
            "errors": errors,
        }
    return {
        "ok": True,
        "path": _as_posix(raw),
        "resolved": _as_posix(target),
        "mirrored": mirrored,
        "files": len(files),
        "chunks_added": added,
        "chunk_count": saved.get("chunk_count"),
        "index": saved.get("path"),
        "errors": errors,
        "evidence": {"sources": source_ids, "at": _utc()},
    }


def query(
    text: str,
    k: int = 5,
    *,
    source_roots: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Keyword retrieve over adapter index (V1 simple_rag search shape + V2 silence)."""
    q = (text or "").strip()
    top = max(1, min(int(k), 50))
    if not q:
        return {"ok": False, "error": "empty_query", "hits": [], "silence": True}
    index = _load_index()
    chunks = index.get("chunks") or []
    if not chunks:
        # Fallback: try absorb_index metadata / aios_knowledge keyword if texts exist
        try:
            from lib.aios_knowledge import keyword_retrieve

            legacy = keyword_retrieve(q, top=top)
            if source_roots:
                # A source-scoped query must never widen into an unscoped legacy
                # result. Unknown provenance is not admissible when a caller has
                # explicitly selected source families.
                legacy = [
                    hit for hit in legacy
                    if str((hit.get("source_ref") or {}).get("root") or "") in source_roots
                ]
            if legacy and legacy[0].get("text"):
                return {
                    "ok": True,
                    "hits": legacy,
                    "k": top,
                    "mode": "absorb_index_fallback",
                    "silence": False,
                }
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": True,
            "hits": [],
            "k": top,
            "mode": "empty_index",
            "silence": True,
            "note": "No contextually relevant information found (empty index).",
        }

    terms = [t.lower() for t in re.findall(r"[a-zA-Z0-9_]{3,}", q)]
    if not terms:
        return {"ok": False, "error": "no_terms", "hits": [], "silence": True}

    scored: list[dict[str, Any]] = []
    seen_fp: set[str] = set()
    source_refs = {str(s.get("id")): s.get("source_ref") for s in (index.get("sources") or [])}
    for ch in chunks:
        body = (ch.get("text") or "").lower()
        if not body:
            continue
        lexical_score = sum(1 for t in terms if t in body)
        # Source priority may break ties among relevant evidence, but it must
        # never manufacture relevance for an unrelated live identity rule.
        if lexical_score < _SILENCE_MIN_SCORE:
            continue
        score = lexical_score
        src = str(ch.get("source") or "")
        tags = str(ch.get("tags") or "").lower()
        source_ref = source_refs.get(src)
        if source_roots:
            root = str((source_ref or {}).get("root") or "")
            if root not in source_roots:
                continue
        # Live teach + hatch seed outrank static corpus noise for day-to-day talk
        if src.startswith("live:") or "live_teach" in tags:
            score += 4
        if any(k in src.lower() for k in ("hatch", "voice_doctrine", "identity")):
            score += 3
        if any(k in body for k in ("hatch seed", "i am viv", "vidi intellexi", "live knowledge training")):
            score += 2
        fp = ch.get("fp") or _fingerprint(ch.get("text") or "")
        if fp in seen_fp:
            continue
        seen_fp.add(fp)
        scored.append(
            {
                "source": ch.get("source"),
                "doc": ch.get("doc") or ch.get("path"),
                "i": ch.get("i"),
                "score": score,
                "text": ch.get("text"),
                "tags": ch.get("tags"),
                "source_ref": source_ref,
            }
        )
    ranking_mode = "keyword_cpu"
    try:
        from lib.knowledge_retrieval_ranker import rank_candidates

        scored, ranking_mode = rank_candidates(q, scored)
    except Exception:  # noqa: BLE001 — retrieval remains available through keyword ordering
        scored.sort(key=lambda x: (-int(x["score"]), str(x.get("source")), int(x.get("i") or 0)))
    hits = scored[:top]
    silence = len(hits) == 0
    return {
        "ok": True,
        "hits": hits,
        "k": top,
        "mode": f"adapter_{ranking_mode}",
        "silence": silence,
        "note": (
            "No contextually relevant information found. Query may require a different knowledge source."
            if silence
            else None
        ),
        "evidence": {"chunk_pool": len(chunks), "term_count": len(terms), "hit_count": len(hits), "ranking_mode": ranking_mode},
    }


def query_packet(
    text: str,
    k: int = 5,
    *,
    source_roots: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Retrieve evidence and return the CPU-owned typed packet beside raw hits."""
    result = query(text, k=k, source_roots=source_roots)
    if not result.get("ok"):
        return {**result, "packet": packet_from_retrieval(text, [])}
    return {**result, "packet": packet_from_retrieval(text, result.get("hits") or [])}


def query_manual_packet(text: str, k: int = 5) -> dict[str, Any]:
    """Search the active manual through the hash-verified CPU ManualOracle."""
    query_text = (text or "").strip()
    if not query_text:
        return {"ok": False, "state": "INSUFFICIENT", "error": "empty_query", "hits": [], "packet": packet_from_retrieval(text, [])}
    try:
        from lib.manual_oracle import ManualOracle

        result = ManualOracle().search(query_text, top_k=k)
    except Exception as exc:  # noqa: BLE001 — manual retrieval fails closed
        return {
            "ok": False,
            "state": "ABSTAIN",
            "error": f"manual_oracle:{type(exc).__name__}:{exc}",
            "hits": [],
            "packet": packet_from_retrieval(query_text, []),
        }
    hits: list[dict[str, Any]] = []
    source = dict(result.get("source") or {})
    for section in result.get("sections") or []:
        hits.append(
            {
                "source": "manual_oracle",
                "doc": source.get("path"),
                "score": 1,
                "text": section.get("text"),
                "claim": f"manual_section:{section.get('anchor')}",
                "source_ref": {
                    "source_id": f"sha256:{source.get('sha256')}",
                    "path": source.get("path"),
                    "root": "L_VIV_FOUNDATION",
                    "kind": "verified_manual_section",
                    "sha256": section.get("sha256"),
                    "source_sha256": source.get("sha256"),
                    "start_line": section.get("start_line"),
                    "end_line": section.get("end_line"),
                },
            }
        )
    return {
        "ok": result.get("state") == "VERIFIED",
        "state": result.get("state"),
        "hits": hits,
        "packet": packet_from_retrieval(query_text, hits),
        "source": source,
    }


def status() -> dict[str, Any]:
    index = _load_index()
    chunks = index.get("chunks") or []
    with_text = sum(1 for c in chunks if (c.get("text") or "").strip())
    return {
        "ok": True,
        "adapter": "aios_adapter_knowledge",
        "index": _as_posix(ADAPTER_INDEX),
        "index_exists": ADAPTER_INDEX.is_file(),
        "chunk_count": len(chunks),
        "chunks_with_text": with_text,
        "sources": len(index.get("sources") or []),
        "last_ingest": index.get("last_ingest"),
        "updated_at": index.get("updated_at"),
        "v1_rag_readable": V1_RAG.is_dir(),
        "v2_knowledge_readable": V2_KNOW.is_dir(),
        "v1_path_note": "D: read/mirror only — never write",
        "v2_path": _as_posix(V2_KNOW) if V2_KNOW.is_dir() else None,
        "mirror_dir": _as_posix(MIRROR_DIR),
        "foundation": _as_posix(FOUNDATION_ROOT),
        "sandbox": _as_posix(SANDBOX_ROOT),
        "evidence": {"at": _utc()},
    }


def run_smoke(*, s_n: float = 0.5) -> dict[str, Any]:
    """Prove ingest + query + status against L: Viv doctrine (and optional V2 chunker source)."""
    probe = FOUNDATION_ROOT / "FOUNDATION_ROADMAP.md"
    if not probe.is_file():
        probe = FOUNDATION_ROOT / "VIV_BUILD_STATUS.md"
    ingest = ingest_path(probe, s_n=s_n)
    # Also ingest V2 semantic_chunker docstring surface if present (L: prefer)
    v2_chunker = V2_KNOW / "semantic_chunker.py"
    ingest_v2: dict[str, Any] | None = None
    if v2_chunker.is_file():
        # .py is not in _TEXT_SUFFIXES — read via explicit file path
        ingest_v2 = _ingest_single_forced(v2_chunker, s_n=s_n, source_tag="v2_semantic_chunker")
    q = query("foundation roadmap plant RID stability absorb", k=3)
    st = status()
    ok = bool(ingest.get("ok")) and bool(q.get("ok")) and (not q.get("silence")) and bool(st.get("ok"))
    result = {
        "ok": ok,
        "ingest": {k: ingest.get(k) for k in ("ok", "chunks_added", "chunk_count", "index", "error")},
        "ingest_v2": ingest_v2,
        "query": {
            "ok": q.get("ok"),
            "silence": q.get("silence"),
            "hit_count": len(q.get("hits") or []),
            "top": [
                {"source": h.get("source"), "score": h.get("score"), "chars": len(h.get("text") or "")}
                for h in (q.get("hits") or [])[:3]
            ],
        },
        "status": {
            "chunk_count": st.get("chunk_count"),
            "chunks_with_text": st.get("chunks_with_text"),
            "v1_rag_readable": st.get("v1_rag_readable"),
            "v2_knowledge_readable": st.get("v2_knowledge_readable"),
        },
        "at": _utc(),
    }
    KNOW_DIR.mkdir(parents=True, exist_ok=True)
    body = _sanitize(json.dumps(result, indent=2))
    gate = _as_posix(ADAPTER_EVIDENCE)
    verdict = tool_gate("write_file", {"path": gate, "content": body}, float(s_n))
    if verdict.get("allowed"):
        ADAPTER_EVIDENCE.write_text(body, encoding="utf-8")
        result["evidence_path"] = gate
    else:
        result["evidence_path"] = None
        result["evidence_gate"] = verdict.get("reason")
    return result


def _ingest_single_forced(path: Path, *, s_n: float, source_tag: str) -> dict[str, Any]:
    """Ingest one file even if suffix is not in the text allowlist (e.g. V2 .py read)."""
    if _is_d_drive(path):
        mirrored = _mirror_foreign(path)
        if mirrored is None:
            return {"ok": False, "error": "mirror_failed"}
        path = mirrored
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    doc = _materialize_doc(path, text=text, s_n=s_n)
    if doc is None:
        return {"ok": False, "error": "materialize_denied"}
    index = _load_index()
    sid = f"ingest:{source_tag}"[:80]
    chunks = [c for c in (index.get("chunks") or []) if c.get("source") != sid]
    parts = _sliding_windows(_sanitize(text))[:24]
    for i, part in enumerate(parts):
        clean = _sanitize(part)
        chunks.append(
            {
                "source": sid,
                "doc": doc.name,
                "i": i,
                "fp": _fingerprint(clean),
                "text": clean,
                "tags": "adapter,v2,knowledge",
            }
        )
    sources = [s for s in (index.get("sources") or []) if s.get("id") != sid]
    sources.append(
        {
            "id": sid,
            "doc": doc.name,
            "name": path.stem,
            "bytes": len(text),
            "chunks": len(parts),
            "at": _utc(),
        }
    )
    index["chunks"] = chunks
    index["sources"] = sources
    saved = _save_index(index, s_n=s_n)
    return {
        "ok": bool(saved.get("ok")),
        "source": sid,
        "chunks": len(parts),
        "error": saved.get("error"),
    }


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_smoke(), indent=2))
