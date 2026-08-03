"""Read-only external knowledge and runtime-authority adapters.

The adapters return the same typed evidence used by the local knowledge
contract. They do not write caches, mutate source systems, or admit training
rows.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.knowledge_claim_alignment import align_claims
from lib.knowledge_source_contract import GroundedFact, SourceRef, build_fact_packet

WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"
LEGACY_WIKIPEDIA_INDEX = Path(
    r"D:\LocalAi\5126\FSAA\Luna\AIOS_V2\dataset_core\global_index.db"
)
LEGACY_WIKIPEDIA_ROOT = Path(r"F:\AI_Datasets\wikipedia_deduplicated")
LEGACY_WIKIPEDIA_LOGICAL_ROOT = "F_AI_DATASETS"
WIKIPEDIA_TITLE_SIDECAR = Path(
    r"L:\Continue\Viv\foundation\artifacts\auto\knowledge\wikipedia_title_index_v1_checkpoint_20260803T023000Z.sqlite"
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def wikipedia_fact_from_payload(title: str, payload: dict[str, Any]) -> GroundedFact:
    """Convert a bounded Wikipedia REST response into one provenance fact."""
    clean_title = " ".join(str(title).split()).strip()
    if not clean_title:
        raise ValueError("empty_wikipedia_title")
    extract = str(payload.get("extract") or "").strip()
    if not extract:
        raise ValueError("wikipedia_summary_missing_extract")
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = _digest(canonical)
    source = SourceRef(
        source_id=f"sha256:{digest}",
        path=f"wikipedia_rest:{clean_title[:160]}",
        root="WIKIPEDIA_REST",
        kind="wikipedia_summary",
        bytes=len(canonical.encode("utf-8")),
        modified_utc=_utc(),
        sha256=digest,
        readable=True,
    )
    return GroundedFact(
        claim=f"wikipedia_summary:{clean_title.casefold()}",
        value=extract[:12000],
        source=source,
        confidence="retrieved",
        scope="wikipedia_summary",
    )


def fetch_wikipedia_summary(title: str, *, timeout_s: float = 5.0) -> dict[str, Any]:
    """Fetch one Wikipedia REST summary; return INCONCLUSIVE on transport failure."""
    clean_title = " ".join(str(title).split()).strip()
    if not clean_title or len(clean_title) > 200:
        return {"ok": False, "state": "INSUFFICIENT", "error": "invalid_title"}
    url = WIKIPEDIA_SUMMARY_URL + urllib.parse.quote(clean_title.replace(" ", "_"), safe="()_-")
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Viv-AIOS-knowledge-reader/1.0"},
        method="GET",
    )
    try:
        try:
            import certifi

            context = ssl.create_default_context(cafile=certifi.where())
        except (ImportError, OSError):
            context = ssl.create_default_context()
        with urllib.request.urlopen(request, timeout=max(0.5, float(timeout_s)), context=context) as response:
            raw = response.read(1_000_000)
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        if not isinstance(payload, dict):
            raise ValueError("wikipedia_payload_not_object")
        fact = wikipedia_fact_from_payload(clean_title, payload)
        return {"ok": True, "state": "VERIFIED", "fact": fact.to_dict(), "source": fact.source.to_dict()}
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        return {
            "ok": False,
            "state": "INCONCLUSIVE",
            "error": f"{type(exc).__name__}:{exc}",
            "source": "WIKIPEDIA_REST",
        }


def legacy_wikipedia_index_status() -> dict[str, Any]:
    """Report the archived Wikipedia filesystem index without opening it for writes."""
    try:
        stat = LEGACY_WIKIPEDIA_INDEX.stat()
        return {
            "ok": True,
            "state": "AVAILABLE",
            "path": str(LEGACY_WIKIPEDIA_INDEX),
            "bytes": stat.st_size,
            "root": str(LEGACY_WIKIPEDIA_ROOT),
            "mode": "sqlite_read_only_structural_index",
        }
    except OSError as exc:
        return {
            "ok": False,
            "state": "INCONCLUSIVE",
            "path": str(LEGACY_WIKIPEDIA_INDEX),
            "error": f"{type(exc).__name__}:{exc}",
        }


def _query_title_sidecar(title: str, *, limit: int = 32) -> list[tuple[Any, ...]] | None:
    """Return exact filename candidates from a COMPLETE derived sidecar.

    ``None`` means the sidecar is unavailable/not authoritative and callers
    may use their legacy path. An empty list means the COMPLETE sidecar has
    no candidate and must not trigger an unbounded source-index scan.
    Filename titles are only candidates: callers still verify the source
    header, containment, bytes, and redirect state before accepting content.
    """
    try:
        source_stat = LEGACY_WIKIPEDIA_INDEX.stat()
        with sqlite3.connect(f"file:{WIKIPEDIA_TITLE_SIDECAR.as_posix()}?mode=ro", uri=True, timeout=5.0) as db:
            db.execute("PRAGMA query_only=ON")
            meta = dict(db.execute("SELECT key,value FROM meta").fetchall())
            if meta.get("state") != "COMPLETE":
                return None
            source_identity = json.loads(meta.get("source_index", "{}"))
            if (
                source_identity.get("path") != str(LEGACY_WIKIPEDIA_INDEX)
                or int(source_identity.get("bytes", -1)) != source_stat.st_size
                or int(source_identity.get("mtime_ns", -1)) != source_stat.st_mtime_ns
            ):
                return None
            clean = " ".join(str(title).split()).strip().casefold()
            if not clean:
                return []
            rows = db.execute(
                "SELECT title,full_path,indexed_bytes FROM titles "
                "WHERE title_key=? ORDER BY source_rowid LIMIT ?",
                (clean, max(1, min(int(limit), 128))),
            ).fetchall()
            return [
                (Path(str(path)).name, str(path), ".txt", int(indexed_bytes or 0))
                for _title, path, indexed_bytes in rows
            ]
    except (OSError, ValueError, TypeError, sqlite3.Error):
        return None
def _resolve_local_wikipedia_title(target: str, *, cap: int = 8) -> tuple[Path | None, str]:
    """Resolve one redirect through the corpus filename/title contract."""
    clean = " ".join(str(target).split()).strip()
    if not clean or len(clean) > 240:
        return None, "invalid_target"
    # The corpus uses six numeric prefix characters followed by the exact title.
    glob_target = clean.replace("[", "[[]").replace("]", "[]]")
    sidecar_rows = _query_title_sidecar(clean, limit=cap)
    if sidecar_rows is not None:
        rows = [(row[1],) for row in sidecar_rows]
    else:
        try:
            uri = f"file:{LEGACY_WIKIPEDIA_INDEX.as_posix()}?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=5.0) as conn:
                rows = conn.execute(
                    "SELECT full_path FROM file_index "
                    "WHERE full_path LIKE ? AND extension='.txt' AND is_dir=0 AND file_name GLOB ? "
                    "ORDER BY full_path COLLATE NOCASE LIMIT ?",
                    (str(LEGACY_WIKIPEDIA_ROOT).replace("/", "\\") + "\\%", f"[0-9][0-9][0-9][0-9][0-9][0-9]_{glob_target}.txt", cap),
                ).fetchall()
        except (OSError, sqlite3.Error):
            return None, "INDEX_UNAVAILABLE"
    matches: list[Path] = []
    title_re = re.compile(r"^\s*Title:\s*(.*?)\s*$", re.I | re.M)
    redirect_re = re.compile(r"^\s*#REDIRECT\s*\[\[([^\]|#]+)", re.I | re.M)
    for (raw_path,) in rows:
        path = Path(str(raw_path))
        try:
            path.resolve().relative_to(LEGACY_WIKIPEDIA_ROOT.resolve())
        except (OSError, ValueError):
            continue
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")[:12000]
        title_match = title_re.search(text)
        if title_match and title_match.group(1).strip().casefold() == clean.casefold() and not redirect_re.search(text):
            matches.append(path)
    if len(matches) == 1:
        return matches[0], "RESOLVED_CROSS_DIRECTORY"
    if len(matches) > 1:
        return None, "AMBIGUOUS_CROSS_DIRECTORY"
    return None, "UNRESOLVED_CROSS_DIRECTORY"


def query_legacy_wikipedia(
    query: str,
    *,
    limit: int = 5,
    max_chars: int = 8000,
    resolve_redirects: bool = False,
) -> dict[str, Any]:
    """Read bounded Wikipedia articles through the recovered legacy index.

    This is intentionally filename/path retrieval, not a claim that the SQLite
    index contains article semantics. Article text is read only from the F:
    corpus and every returned fact carries the article path and digest.
    """
    status = legacy_wikipedia_index_status()
    if not status.get("ok"):
        return {"ok": False, "state": status.get("state"), "status": status}
    terms = []
    stopwords = {
        "a", "an", "and", "are", "does", "for", "how", "in", "is",
        "of", "on", "the", "to", "was", "what", "when", "where", "which",
        "who", "why",
    }
    seen: set[str] = set()
    for term in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{3,}", str(query)):
        normalized = term.casefold()
        if normalized not in stopwords and normalized not in seen:
            seen.add(normalized)
            terms.append(normalized)
    if not terms:
        return {"ok": False, "state": "INSUFFICIENT", "status": status, "facts": []}
    limit = max(1, min(int(limit), 20))
    max_chars = max(256, min(int(max_chars), 12000))
    # A natural-language question often becomes an exact article title after
    # removing question glue. Prefer the COMPLETE sidecar for that normalized
    # title before falling back to the bounded structural filename search.
    title_terms = [
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{1,}", str(query))
        if token.casefold() not in stopwords
    ]
    normalized_title = " ".join(title_terms).strip()
    clauses = " OR ".join("file_name LIKE ?" for _ in terms)
    params: list[Any] = [f"%{term}%" for term in terms]
    params.extend([str(LEGACY_WIKIPEDIA_ROOT).replace("/", "\\") + "%", limit * 32])
    sql = f"""
        SELECT file_name, full_path, extension, size_bytes
        FROM file_index
        WHERE ({clauses}) AND full_path LIKE ? AND is_dir = 0
        ORDER BY length(file_name) ASC, file_name COLLATE NOCASE ASC
        LIMIT ?
    """
    try:
        uri = f"file:{LEGACY_WIKIPEDIA_INDEX.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5.0) as conn:
            clean_title = " ".join(str(query).split()).strip()
            exact_rows: list[tuple[Any, ...]] = []
            sidecar_rows = _query_title_sidecar(clean_title, limit=limit * 32) if clean_title else []
            if not sidecar_rows and normalized_title and normalized_title.casefold() != clean_title.casefold():
                sidecar_rows = _query_title_sidecar(normalized_title, limit=limit * 32)
            if sidecar_rows:
                exact_rows = sidecar_rows
                rows = exact_rows
            elif sidecar_rows is not None and clean_title:
                # A COMPLETE sidecar can authoritatively report that the full
                # sentence is not an article title. That is not evidence that
                # the sentence has no relevant article: retain the bounded
                # structural filename fallback for natural-language queries.
                rows = conn.execute(sql, params).fetchall()
            elif clean_title:
                exact_target = clean_title.replace("[", "[[]").replace("]", "[]]")
                exact_rows = conn.execute(
                    "SELECT file_name, full_path, extension, size_bytes "
                    "FROM file_index WHERE file_name GLOB ? AND full_path LIKE ? "
                    "AND extension='.txt' AND is_dir=0 LIMIT ?",
                    (
                        f"[0-9][0-9][0-9][0-9][0-9][0-9]_{exact_target}.txt",
                        str(LEGACY_WIKIPEDIA_ROOT).replace("/", "\\") + "%",
                        limit * 32,
                    ),
                ).fetchall()
                rows = exact_rows or conn.execute(sql, params).fetchall()
            else:
                rows = conn.execute(sql, params).fetchall()
    except (OSError, sqlite3.Error) as exc:
        return {
            "ok": False,
            "state": "INCONCLUSIVE",
            "status": status,
            "error": f"{type(exc).__name__}:{exc}",
            "facts": [],
        }
    def _candidate_key(row: tuple[Any, ...]) -> tuple[int, int, int, str]:
        name = Path(str(row[0])).stem
        title = re.sub(r"^\d+_", "", name).casefold().replace("_", " ")
        title_terms = set(re.findall(r"[a-z0-9]{3,}", title))
        query_terms = set(terms)
        exact_title = int(title_terms == query_terms)
        matched = len(query_terms.intersection(title_terms))
        return (-exact_title, -matched, int(row[3] or 0), str(row[0]))

    rows = sorted(rows, key=_candidate_key)
    facts: list[dict[str, Any]] = []
    errors: list[str] = []
    redirect_resolution = {"enabled": bool(resolve_redirects), "seen": 0, "resolved": 0, "unresolved": 0, "aliases": 0}
    seen_canonical: set[str] = set()
    for file_name, full_path, extension, size_bytes in rows:
        source_path = Path(str(full_path))
        try:
            if source_path.drive.upper() != "F:" or not source_path.is_relative_to(LEGACY_WIKIPEDIA_ROOT):
                continue
            original_path = source_path
            text = source_path.read_text(encoding="utf-8", errors="replace")[:max_chars].strip()
            if not text:
                continue
            title_match = re.search(r"^\s*Title:\s*(.*?)\s*$", text, re.I | re.M)
            redirect_match = re.search(r"^\s*#REDIRECT\s*\[\[([^\]|#]+)", text, re.I | re.M)
            redirect_target = redirect_match.group(1).strip() if redirect_match else None
            if resolve_redirects and redirect_target:
                redirect_resolution["seen"] += 1
                canonical_path, resolution_state = _resolve_local_wikipedia_title(redirect_target)
                if canonical_path is None:
                    redirect_resolution["unresolved"] += 1
                    errors.append(f"redirect_unresolved:{original_path.name}:{resolution_state}")
                    continue
                source_path = canonical_path
                text = source_path.read_text(encoding="utf-8", errors="replace")[:max_chars].strip()
                redirect_resolution["resolved"] += 1
                redirect_resolution["aliases"] += 1
            canonical_key = str(source_path.resolve()).casefold()
            if canonical_key in seen_canonical:
                continue
            seen_canonical.add(canonical_key)
            payload = f"{file_name}\n{text}"
            digest = _digest(payload)
            source = SourceRef(
                source_id=f"sha256:{digest}",
                path=str(source_path),
                # Preserve the physical path above while using the governed
                # logical source family for three-way coverage and alignment.
                root=LEGACY_WIKIPEDIA_LOGICAL_ROOT,
                kind="wikipedia_local_article_resolved_redirect" if redirect_target else "wikipedia_local_article",
                bytes=int(size_bytes or 0),
                modified_utc=None,
                sha256=digest,
                readable=True,
            )
            title = (title_match.group(1).strip() if title_match else None) if not redirect_target else redirect_target
            if not title:
                title = re.sub(r"^\d+_", "", Path(str(file_name)).stem).replace("_", " ").strip()
            fact = GroundedFact(
                claim=(
                    f"wikipedia_local_redirect:{title.casefold()}"
                    if redirect_target
                    else f"wikipedia_local:{title.casefold()}"
                ),
                value=text,
                source=source,
                confidence="retrieved_local_index",
                scope="wikipedia_local_article",
            )
            facts.append(fact.to_dict())
            if len(facts) >= limit:
                break
        except (OSError, ValueError) as exc:
            errors.append(f"{file_name}:{type(exc).__name__}:{exc}")
    return {
        "ok": bool(facts),
        "state": "VERIFIED" if facts else ("INSUFFICIENT" if not rows else "INCONCLUSIVE"),
        "status": status,
        "facts": facts,
        "candidate_rows": len(rows),
        "errors": errors,
        "mode": "legacy_sqlite_index_bounded_article_read_redirect_aware" if resolve_redirects else "legacy_sqlite_index_bounded_article_read",
        "redirect_resolution": redirect_resolution,
    }


def runtime_authority_fact() -> dict[str, Any]:
    """Read the current live RID feed without falling back to a stale snapshot."""
    try:
        from lib.rid_feed import feed_meta, read_live

        sample = read_live()
        if sample is None:
            meta = feed_meta()
            value = json.dumps(
                {"state": "UNVERIFIED", "reason": "stale_or_unavailable", "age_s": meta.age_s},
                sort_keys=True,
            )
            verified = False
        else:
            value = json.dumps(
                {
                    "state": "VERIFIED",
                    "s_n": float(sample.s_n),
                    "status": str(sample.status),
                    "timestamp": str(sample.timestamp),
                },
                sort_keys=True,
            )
            verified = True
        digest = _digest(value)
        source = SourceRef(
            source_id=f"sha256:{digest}",
            path="runtime_authority:rid_feed",
            root="runtime_authority",
            kind="live_rid_authority",
            bytes=len(value.encode("utf-8")),
            modified_utc=_utc(),
            sha256=digest,
            readable=True,
        )
        fact = GroundedFact(
            claim="runtime_authority_state",
            value=value,
            source=source,
            confidence="measured" if verified else "verified_unknown",
            scope="runtime_health",
        )
        return {"ok": True, "state": "VERIFIED" if verified else "UNVERIFIED", "fact": fact.to_dict()}
    except Exception as exc:  # noqa: BLE001 — authority adapter fails closed
        return {"ok": False, "state": "INCONCLUSIVE", "error": type(exc).__name__}


def compose_multi_source_packet(
    query: str,
    *,
    wikipedia_title: str | None = None,
    include_legacy_wikipedia: bool = False,
    resolve_legacy_redirects: bool = False,
    include_runtime: bool = True,
) -> dict[str, Any]:
    """Compose local, Wikipedia, and optional runtime evidence without persistence."""
    from lib.aios_adapter_knowledge import query_packet

    local = query_packet(query, k=3, source_roots=("F_AI_DATASETS",))
    facts: list[GroundedFact] = []
    for row in (local.get("packet") or {}).get("facts") or []:
        source_data = dict(row.get("source") or {})
        source = SourceRef(
            source_id=str(source_data.get("source_id") or "local_unknown"),
            path=str(source_data.get("path") or "local_unknown"),
            root=str(source_data.get("root") or "F_AI_DATASETS"),
            kind=str(source_data.get("kind") or "retrieved_text"),
            bytes=int(source_data.get("bytes") or 0),
            modified_utc=source_data.get("modified_utc"),
            sha256=str(source_data.get("sha256") or ""),
            readable=bool(source_data.get("readable", True)),
        )
        facts.append(
            GroundedFact(
                claim=str(row.get("claim") or "local_evidence"),
                value=str(row.get("value") or ""),
                source=source,
                confidence=str(row.get("confidence") or "retrieved"),
                scope=str(row.get("scope") or "knowledge_search"),
            )
        )
    wikipedia = None
    if wikipedia_title:
        wikipedia = fetch_wikipedia_summary(wikipedia_title)
        if wikipedia.get("ok") and wikipedia.get("fact"):
            row = wikipedia["fact"]
            source_data = row["source"]
            facts.append(
                GroundedFact(
                    claim=str(row["claim"]),
                    value=str(row["value"]),
                    source=SourceRef(**source_data),
                    confidence=str(row.get("confidence") or "retrieved"),
                    scope=str(row.get("scope") or "wikipedia_summary"),
                )
            )
    legacy_wikipedia = None
    if include_legacy_wikipedia:
        legacy_wikipedia = query_legacy_wikipedia(query, resolve_redirects=resolve_legacy_redirects)
        for row in legacy_wikipedia.get("facts") or []:
            source_data = row["source"]
            facts.append(
                GroundedFact(
                    claim=str(row["claim"]),
                    value=str(row["value"]),
                    source=SourceRef(**source_data),
                    confidence=str(row.get("confidence") or "retrieved_local_index"),
                    scope=str(row.get("scope") or "wikipedia_local_article"),
                )
            )
    runtime = runtime_authority_fact() if include_runtime else None
    if runtime and runtime.get("ok") and runtime.get("fact"):
        row = runtime["fact"]
        facts.append(
            GroundedFact(
                claim=str(row["claim"]),
                value=str(row["value"]),
                source=SourceRef(**row["source"]),
                confidence=str(row.get("confidence") or "measured"),
                scope=str(row.get("scope") or "runtime_health"),
            )
        )
    packet = build_fact_packet(query, facts, authority="knowledge_multi_source_v1")
    packet["claim_alignment"] = align_claims(query, packet.get("facts") or [])
    return {
        "ok": bool(local.get("ok")) and bool(facts),
        "packet": packet,
        "local": {"ok": local.get("ok"), "hit_count": len(local.get("hits") or [])},
        "wikipedia": {"ok": wikipedia.get("ok"), "state": wikipedia.get("state")} if wikipedia else None,
        "legacy_wikipedia": (
            {"ok": legacy_wikipedia.get("ok"), "state": legacy_wikipedia.get("state"), "mode": legacy_wikipedia.get("mode")}
            if legacy_wikipedia
            else None
        ),
        "runtime": {"ok": runtime.get("ok"), "state": runtime.get("state")} if runtime else None,
    }
