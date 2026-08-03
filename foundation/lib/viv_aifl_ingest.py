"""AIFL self-ingestion — random L: files → deterministic sense → link → memory candidates.

CPU layer owns truth extraction (no hallucinated file claims).
GPU/mouth may narrate; shadow judge stamps. Memories only from verified extract.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS, CONTINUE_ROOT, FOUNDATION_ROOT, SANDBOX_ROOT, VIV_ROOT

AIFL_DIR = AUTO_ARTIFACTS / "aifl"
INGEST_LOG = AIFL_DIR / "ingest.jsonl"
PATTERNS_JSON = AIFL_DIR / "patterns_latest.json"

# Bound to AIOS plane — not arbitrary whole-disk
_ROOTS: tuple[Path, ...] = (
    FOUNDATION_ROOT,
    SANDBOX_ROOT,
    VIV_ROOT / "sandbox" / "journal",
    VIV_ROOT / "sandbox" / "work" / "aios_build",
)

_TEXT_EXT = {".md", ".txt", ".json", ".jsonl", ".yml", ".yaml", ".csv", ".ini", ".cfg", ".toml", ".py", ".rs"}
_SKIP_DIR = {
    ".venv",
    "node_modules",
    "__pycache__",
    ".git",
    "viv_voice_lora",
    "runs_prt",
    "OpenAster1-128k-base-hf",
}
_SKIP_NAME = {".env", "credentials.json", "cpu_config.json"}  # gated / sensitive
_MAX_FILE_BYTES = 256_000
_MAX_READ_CHARS = 4000


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_posix(p: Path) -> str:
    return str(p).replace("\\", "/")


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-zA-Z0-9_]{3,}", text or "") if t}


def token_overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta | tb))


def _kind_guess(path: Path, head: str) -> str:
    s = _as_posix(path).lower()
    if "/models/cpu/" in s:
        return "cpu_model_weight"
    if "/models/gpu/" in s:
        return "gpu_model_weight"
    if path.suffix == ".py":
        return "python_source"
    if path.suffix == ".rs":
        return "rust_source"
    if "contract" in path.name.lower() or "doctrine" in path.name.lower():
        return "doctrine"
    if "/journal/" in s or path.name.upper().startswith("SELF"):
        return "self_journal"
    if "/artifacts/" in s:
        return "artifact"
    if path.suffix in {".md", ".txt"} and ("#" in head[:80] or "viv" in head.lower()):
        return "markdown_doc"
    if path.suffix in {".json", ".jsonl"}:
        return "json_data"
    return "text_file"


def _safe_under_roots(path: Path) -> bool:
    try:
        rp = path.resolve()
    except OSError:
        return False
    for root in _ROOTS:
        try:
            rp.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def list_candidate_files(*, limit_scan: int = 1200) -> list[Path]:
    """Enumerate readable text candidates under allowlisted L: AIOS roots."""
    out: list[Path] = []
    for root in _ROOTS:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in __import__("os").walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR and not d.startswith(".")]
            for name in filenames:
                if name in _SKIP_NAME:
                    continue
                p = Path(dirpath) / name
                if p.suffix.lower() not in _TEXT_EXT:
                    continue
                try:
                    if p.stat().st_size > _MAX_FILE_BYTES:
                        continue
                except OSError:
                    continue
                out.append(p)
                if len(out) >= limit_scan:
                    return out
    return out


# Tag clusters for diverse self-ingest (mandatory before next ladder).
# Match is path substring (posix lower). At least one file per available cluster when possible.
_TAG_CLUSTERS: dict[str, tuple[str, ...]] = {
    "bridges": ("/system_bridges/", "/bridges/", "system_bridges"),
    "contracts": ("contract", "doctrine", "_contract"),
    "rid": ("/artifacts/rid/", "/rid/", "rid_", "ridplot", "ridv"),
    "core": ("/security_core/", "/lib/", "/foundation/lib/"),
    "shell": ("viv_shell", "/scripts/", "viv_chat", "shell"),
}


def _cluster_for(path: Path) -> str | None:
    s = _as_posix(path).lower()
    name = path.name.lower()
    for cluster, needles in _TAG_CLUSTERS.items():
        for n in needles:
            if n in s or n in name:
                return cluster
    return None


def _bucket_by_cluster(pool: list[Path]) -> dict[str, list[Path]]:
    buckets: dict[str, list[Path]] = {k: [] for k in _TAG_CLUSTERS}
    buckets["other"] = []
    for p in pool:
        c = _cluster_for(p)
        buckets[c or "other"].append(p)
    return buckets


def sample_files(n: int = 2, *, rng: random.Random | None = None) -> list[Path]:
    """Tag-cluster + sibling bias so ingest spans bridges/contracts/rid/core/shell.

    Strategy:
      1) Ensure ≥1 file from each *available* cluster (up to n slots).
      2) Fill remaining from same-parent siblings of the first pick.
      3) Else recent-mtime / random from pool.
    """
    pool = list_candidate_files()
    r = rng or random.Random()
    if not pool:
        return []
    k = max(1, min(int(n), 5, len(pool)))
    buckets = _bucket_by_cluster(pool)
    available = [c for c in _TAG_CLUSTERS if buckets.get(c)]
    r.shuffle(available)

    picked: list[Path] = []
    used_clusters: list[str] = []
    # One from each cluster first (diversity mandate)
    for c in available:
        if len(picked) >= k:
            break
        choice = r.choice(buckets[c])
        if choice not in picked:
            picked.append(choice)
            used_clusters.append(c)

    # Sibling fill from first pick's parent
    if picked and len(picked) < k:
        seed = picked[0]
        siblings = [
            p
            for p in pool
            if p.parent == seed.parent and p not in picked and p.suffix.lower() in _TEXT_EXT
        ]
        r.shuffle(siblings)
        for p in siblings:
            if len(picked) >= k:
                break
            picked.append(p)

    # Recent mtime fill
    if len(picked) < k:
        dated: list[tuple[float, Path]] = []
        for p in pool:
            if p in picked:
                continue
            try:
                dated.append((p.stat().st_mtime, p))
            except OSError:
                continue
        dated.sort(key=lambda x: x[0], reverse=True)
        for _, p in dated:
            if len(picked) >= k:
                break
            picked.append(p)

    return picked[:k]


def scrub_law4(text: str) -> str:
    """Remove extension/path tokens that trip Security Law 4 on teach/ingest."""
    out = text or ""
    out = re.sub(
        r"\.(py|json|jsonl|rs|toml|pyd|dll|exe|bat|ps1|js|mjs|wasm)\b",
        "[src]",
        out,
        flags=re.I,
    )
    # Bracketed scrub already used by membrane sometimes — normalize
    out = out.replace("[js]on", "[src]").replace("[py]", "[src]")
    return out[:700]


def sense_file(path: Path) -> dict[str, Any]:
    """Deterministic file sense — facts only, no invention."""
    if not _safe_under_roots(path):
        return {"ok": False, "error": "outside_allowlist", "path": _as_posix(path)}
    if not path.is_file():
        return {"ok": False, "error": "not_file", "path": _as_posix(path)}
    try:
        raw = path.read_bytes()[: _MAX_FILE_BYTES + 1]
    except OSError as exc:
        return {"ok": False, "error": f"read_fail:{exc}", "path": _as_posix(path)}
    if len(raw) > _MAX_FILE_BYTES:
        return {"ok": False, "error": "too_large", "path": _as_posix(path)}
    text = raw.decode("utf-8", errors="replace")[:_MAX_READ_CHARS]
    head = "\n".join(text.splitlines()[:12])
    toks = sorted(_tokens(text), key=lambda t: (-len(t), t))[:24]
    rel = _as_posix(path)
    try:
        rel = _as_posix(path.relative_to(CONTINUE_ROOT))
    except ValueError:
        pass
    fp = hashlib.sha256(raw).hexdigest()[:16]
    kind = _kind_guess(path, head)
    facts = [
        f"path={rel}",
        f"suffix={path.suffix.lower() or '(none)'}",
        f"bytes={len(raw)}",
        f"kind={kind}",
        f"fingerprint={fp}",
        f"top_tokens={','.join(toks[:12])}",
    ]
    return {
        "ok": True,
        "path": _as_posix(path),
        "rel": rel,
        "suffix": path.suffix.lower(),
        "bytes": len(raw),
        "kind": kind,
        "fingerprint": fp,
        "head": head[:600],
        "tokens": toks,
        "facts": facts,
        "text_sample": text[:900],
    }


def link_files(senses: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic link score among 2–3 sensed files."""
    ok = [s for s in senses if s.get("ok")]
    if len(ok) < 2:
        return {"ok": True, "n": len(ok), "links": [], "note": "need_2_plus"}
    links: list[dict[str, Any]] = []
    for i in range(len(ok)):
        for j in range(i + 1, len(ok)):
            a, b = ok[i], ok[j]
            ov = token_overlap(
                " ".join(a.get("tokens") or []) + " " + (a.get("head") or ""),
                " ".join(b.get("tokens") or []) + " " + (b.get("head") or ""),
            )
            shared_stem = Path(a.get("rel") or "").stem.lower() == Path(b.get("rel") or "").stem.lower()
            same_kind = a.get("kind") == b.get("kind")
            same_parent = Path(a.get("path") or "").parent == Path(b.get("path") or "").parent
            linked = ov >= 0.08 or shared_stem or (same_kind and same_parent)
            links.append(
                {
                    "a": a.get("rel"),
                    "b": b.get("rel"),
                    "overlap": round(ov, 4),
                    "same_kind": same_kind,
                    "same_parent": same_parent,
                    "linked": linked,
                    "why": (
                        f"overlap={ov:.3f}"
                        + ("; same_stem" if shared_stem else "")
                        + ("; same_kind+parent" if same_kind and same_parent else "")
                    ),
                }
            )
    return {"ok": True, "n": len(ok), "links": links, "any_link": any(x.get("linked") for x in links)}


def build_ingest_prompts(senses: list[dict[str, Any]], links: dict[str, Any]) -> list[str]:
    """Self-asks grounded only in deterministic facts (anti-hallucination)."""
    prompts: list[str] = []
    for s in senses:
        if not s.get("ok"):
            continue
        fact_line = "; ".join(s.get("facts") or [])
        prompts.append(
            f"Self-ingest: I sampled file {s.get('rel')}. "
            f"Verified facts only: {fact_line}. "
            f"Head: {(s.get('head') or '')[:180]!r}. "
            f"In your own words: what is this file in the AIOS system, without inventing paths or claims?"
        )
    if links.get("any_link"):
        bits = []
        for lk in links.get("links") or []:
            if lk.get("linked"):
                bits.append(f"{lk.get('a')} ↔ {lk.get('b')} ({lk.get('why')})")
        prompts.append(
            "Self-ingest link check: deterministic overlap found between: "
            + " | ".join(bits[:3])
            + ". What pattern do these files share? Cite only the verified link reasons."
        )
    elif len([s for s in senses if s.get("ok")]) >= 2:
        prompts.append(
            "Self-ingest link check: sampled files show weak or no token overlap. "
            "Say honestly they may be unrelated for now — do not invent a connection."
        )
    prompts.append(
        "From this ingest, state one memory about yourself (Viv) that is proven by the file facts — "
        "or say you learned a system fact, not a self fact. No theater."
    )
    return prompts


def memory_candidate(senses: list[dict[str, Any]], links: dict[str, Any]) -> str:
    """Compact memory line for CARMA/teach — facts only (Law-4 safe)."""
    parts = [f"AIFL ingest at {_utc()}"]
    for s in senses:
        if s.get("ok"):
            rel = scrub_law4(str(s.get("rel") or ""))
            parts.append(f"{s.get('kind')}:{rel} fp={s.get('fingerprint')}")
    if links.get("any_link"):
        for lk in links.get("links") or []:
            if lk.get("linked"):
                a = scrub_law4(str(lk.get("a") or ""))
                b = scrub_law4(str(lk.get("b") or ""))
                parts.append(f"link:{a}~{b} ov={lk.get('overlap')}")
    return scrub_law4(" | ".join(parts))[:700]


def run_ingest_sample(*, n_files: int = 2, seed: int | None = None) -> dict[str, Any]:
    """One ingest episode: sample → sense → link → prompts + memory candidate."""
    rng = random.Random(seed if seed is not None else int(datetime.now().timestamp() * 1000) % 1_000_000)
    # Prefer enough slots to hit multiple tag clusters (min 3 when operator asks ≥2)
    n_eff = max(int(n_files), 3) if int(n_files) >= 2 else int(n_files)
    paths = sample_files(n_eff, rng=rng)
    senses = [sense_file(p) for p in paths]
    links = link_files(senses)
    prompts = build_ingest_prompts(senses, links)
    mem = memory_candidate(senses, links)
    same_parent = False
    if len(paths) >= 2:
        same_parent = all(p.parent == paths[0].parent for p in paths)
    clusters = [_cluster_for(p) or "other" for p in paths]
    row = {
        "at": _utc(),
        "n_files": len(paths),
        "paths": [_as_posix(p) for p in paths],
        "sample_bias": {
            "strategy": "tag_cluster_plus_siblings",
            "same_parent_cluster": same_parent,
            "clusters": clusters,
            "clusters_unique": sorted(set(clusters)),
            "tag_cluster_keys": list(_TAG_CLUSTERS.keys()),
        },
        "senses": [{k: v for k, v in s.items() if k != "text_sample"} for s in senses],
        "links": links,
        "memory_candidate": mem,
        "prompts_n": len(prompts),
        "cpu_models_note": "models/cpu: viv-embed BERT + goemotions + populism — geometry/sensors, not chat soul",
        "gpu_note": "models/gpu: OpenAster base mouth — drafts only under judge",
    }
    AIFL_DIR.mkdir(parents=True, exist_ok=True)
    with INGEST_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    PATTERNS_JSON.write_text(json.dumps({"at": _utc(), "latest": row}, indent=2, default=str), encoding="utf-8")
    return {**row, "prompts": prompts, "ok": True}
