"""Read-only source identity and typed provenance packets for Viv knowledge.

This module never writes to a source tree. It is deliberately independent from
the knowledge index so source inspection can be tested before admission.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SOURCE_ROOTS = tuple(
    Path(raw)
    for raw in (
        r"F:\AI_Datasets",
        r"F:\AIOS_Clean",
        r"D:\LocalAi",
        r"L:\Continue",
    )
)

THREE_WAY_SOURCES = ("F_AI_DATASETS", "WIKIPEDIA_REST", "runtime_authority")


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _posix(path: Path) -> str:
    return str(path).replace("\\", "/")


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _allowed(path: Path) -> bool:
    return any(_under(path, root) for root in SOURCE_ROOTS)


def _sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    path: str
    root: str
    kind: str
    bytes: int
    modified_utc: str | None
    sha256: str
    readable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "path": self.path,
            "root": self.root,
            "kind": self.kind,
            "bytes": self.bytes,
            "modified_utc": self.modified_utc,
            "sha256": self.sha256,
            "readable": self.readable,
        }


@dataclass(frozen=True)
class GroundedFact:
    claim: str
    value: str
    source: SourceRef
    confidence: str = "measured"
    scope: str = "source"

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "value": self.value,
            "confidence": self.confidence,
            "scope": self.scope,
            "source": self.source.to_dict(),
        }


def assess_three_way(
    facts: Iterable[GroundedFact],
    *,
    required_sources: tuple[str, ...] = THREE_WAY_SOURCES,
) -> dict[str, Any]:
    """Report source coverage and value conflicts without overstating certainty."""
    rows = list(facts)
    present = sorted({fact.source.root for fact in rows})
    missing = [source for source in required_sources if source not in present]
    grouped: dict[str, dict[str, set[str]]] = {}
    for fact in rows:
        claim = re.sub(r"[^a-z0-9]+", "_", fact.claim.lower()).strip("_")
        grouped.setdefault(claim, {}).setdefault(fact.source.root, set()).add(fact.value.strip())
    conflict_claims = sorted(
        claim
        for claim, source_values in grouped.items()
        if len({value for values in source_values.values() for value in values}) > 1
    )
    aligned_claims = sorted(
        claim
        for claim, source_values in grouped.items()
        if all(source in source_values for source in required_sources)
    )
    if not rows:
        state = "INSUFFICIENT"
    elif conflict_claims:
        state = "CONFLICT"
    elif missing or not aligned_claims:
        state = "PARTIAL"
    else:
        state = "AGREED"
    return {
        "state": state,
        "required_sources": list(required_sources),
        "present_sources": present,
        "missing_sources": missing,
        "conflict_claims": conflict_claims,
        "aligned_claims": aligned_claims,
    }


def describe_file(path: str | Path, *, kind: str = "text") -> SourceRef:
    """Describe and hash one explicitly allowlisted source file, read-only."""
    candidate = Path(path)
    if not _allowed(candidate):
        raise ValueError(f"source_outside_allowlist:{_posix(candidate)}")
    resolved = candidate.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(_posix(resolved))
    stat = resolved.stat()
    root = next(root for root in SOURCE_ROOTS if _under(resolved, root))
    modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0).isoformat()
    digest = _sha256(resolved)
    return SourceRef(
        source_id=f"sha256:{digest}",
        path=_posix(resolved),
        root=_posix(root),
        kind=kind,
        bytes=stat.st_size,
        modified_utc=modified,
        sha256=digest,
        readable=True,
    )


def sample_text_files(
    root: str | Path,
    *,
    max_files: int = 8,
    max_bytes_each: int = 256_000,
) -> list[dict[str, Any]]:
    """Return bounded read-only samples with source hashes; never indexes a tree."""
    base = Path(root).resolve()
    if not _allowed(base):
        raise ValueError(f"source_outside_allowlist:{_posix(base)}")
    if not base.is_dir():
        raise NotADirectoryError(_posix(base))
    suffixes = {".txt", ".md", ".json", ".jsonl", ".rst", ".csv"}
    samples: list[dict[str, Any]] = []
    pending = [base]
    visited_dirs = 0
    while pending and len(samples) < max_files and visited_dirs < 64:
        current = pending.pop(0)
        visited_dirs += 1
        try:
            entries = sorted(os.scandir(current), key=lambda entry: entry.name.lower())
        except OSError:
            continue
        for entry in entries:
            if len(samples) >= max_files:
                break
            lower_name = entry.name.lower()
            if entry.is_dir(follow_symlinks=False):
                if lower_name not in {".git", "__pycache__", "target", "node_modules"}:
                    pending.append(Path(entry.path))
                continue
            candidate = Path(entry.path)
            if not entry.is_file(follow_symlinks=False) or candidate.suffix.lower() not in suffixes:
                continue
            ref = describe_file(candidate)
            with candidate.open("r", encoding="utf-8", errors="replace") as handle:
                text = handle.read(max_bytes_each)
            samples.append({"source": ref.to_dict(), "sample_chars": len(text), "text": text})
    return samples


def build_fact_packet(
    query: str,
    facts: Iterable[GroundedFact],
    *,
    authority: str = "knowledge_source_contract_v1",
) -> dict[str, Any]:
    """Build a fail-closed typed packet and detect conflicting claim values."""
    rows = list(facts)
    grouped: dict[str, set[str]] = {}
    for fact in rows:
        key = re.sub(r"[^a-z0-9]+", "_", fact.claim.lower()).strip("_")
        grouped.setdefault(key, set()).add(fact.value.strip())
    conflicts = sorted(key for key, values in grouped.items() if len(values) > 1)
    if not rows:
        state = "INSUFFICIENT"
    elif conflicts:
        state = "CONFLICT"
    else:
        state = "VERIFIED"
    return {
        "version": "1.0",
        "authority": authority,
        "created_utc": _utc(),
        "query": query,
        "state": state,
        "facts": [fact.to_dict() for fact in rows],
        "conflicts": conflicts,
        "three_way": assess_three_way(rows),
        "render_rule": (
            "Render only supplied facts; preserve scope and uncertainty; "
            "say cannot verify when state is INSUFFICIENT or CONFLICT."
        ),
    }


def packet_from_retrieval(query: str, hits: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Convert adapter hits into a typed packet without inventing claim values."""
    facts: list[GroundedFact] = []
    for index, hit in enumerate(hits):
        raw = dict(hit.get("source_ref") or {})
        source = SourceRef(
            source_id=str(raw.get("source_id") or hit.get("source") or f"hit:{index}"),
            path=str(raw.get("source_token") or raw.get("path") or hit.get("doc") or "unknown"),
            root=str(raw.get("root") or "knowledge_index"),
            kind=str(raw.get("kind") or "retrieved_text"),
            bytes=int(raw.get("bytes") or len(str(hit.get("text") or ""))),
            modified_utc=raw.get("modified_utc"),
            sha256=str(raw.get("sha256") or ""),
            readable=bool(raw.get("readable", True)),
        )
        facts.append(
            GroundedFact(
                claim=str(hit.get("claim") or f"retrieved_evidence_{index}"),
                value=str(hit.get("text") or "").strip(),
                source=source,
                confidence="retrieved",
                scope="knowledge_search",
            )
        )
    return build_fact_packet(query, facts, authority="knowledge_retrieval_v1")
