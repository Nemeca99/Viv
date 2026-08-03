"""Callable audit_core adapter — real foundation audit file surface.

Registry id: audit_core
V2 source (read-only): L:/Continue/FSAA/Luna/AIOS_V2/audit_core

API: status(), tail(log_name, n), search(query, n), run_smoke()

Reads real Viv audit artifacts (e.g. prt_autonomous.log) under
foundation/artifacts/audit. Optional V2 jsonl logs are read-only fallback.
Does not mutate security_core.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.paths import ARTIFACTS, AUTO_ARTIFACTS  # noqa: E402

ADAPTER_ID = "audit_core"
REGISTRY_ID = "audit_core"

AUDIT_DIR = ARTIFACTS / "audit"
V2_AUDIT = Path(r"L:/Continue/FSAA/Luna/AIOS_V2/audit_core")
V2_LOGS = V2_AUDIT / "logs"
EVIDENCE_DIR = AUTO_ARTIFACTS / "audit_adapter"
ADAPTER_EVIDENCE = EVIDENCE_DIR / "adapter_smoke.json"

PRIMARY_LOG = "prt_autonomous.log"
_LOG_SUFFIXES = {".log", ".jsonl", ".json", ".md", ".txt"}
_MAX_TAIL = 200
_MAX_SEARCH_FILES = 40
_MAX_LINE_CHARS = 400
_MAX_READ_BYTES = 8_000_000


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_posix(p: Path | str) -> str:
    return str(p).replace("\\", "/")


def _s_n() -> float:
    try:
        from lib.master_rid import load_master_rid

        return float(load_master_rid().master_s_n)
    except Exception:  # noqa: BLE001
        return 0.5


def _safe_name(log_name: str) -> str | None:
    """Basename-only log name; reject path traversal."""
    raw = (log_name or "").strip().replace("\\", "/")
    if not raw or "/" in raw or ".." in raw:
        return None
    name = Path(raw).name
    if not name or name in {".", ".."}:
        return None
    return name


def _resolve_log(log_name: str) -> tuple[Path | None, str]:
    """Resolve to Viv audit file first, then V2 logs (read-only)."""
    name = _safe_name(log_name)
    if name is None:
        return None, "invalid_log_name"
    viv = AUDIT_DIR / name
    if viv.is_file():
        return viv, "viv_audit"
    # Allow stem match (prt_autonomous -> prt_autonomous.log)
    if "." not in name:
        for suf in (".log", ".jsonl", ".json", ".md", ".txt"):
            cand = AUDIT_DIR / f"{name}{suf}"
            if cand.is_file():
                return cand, "viv_audit"
    v2 = V2_LOGS / name
    if v2.is_file():
        return v2, "v2_audit_ro"
    return None, "not_found"


def _list_viv_logs(limit: int = 80) -> list[dict[str, Any]]:
    if not AUDIT_DIR.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in AUDIT_DIR.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in _LOG_SUFFIXES and path.name != PRIMARY_LOG:
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        rows.append(
            {
                "name": path.name,
                "path": _as_posix(path),
                "bytes": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
            }
        )
    rows.sort(key=lambda r: str(r.get("mtime") or ""), reverse=True)
    return rows[:limit]


def _tail_lines(path: Path, n: int) -> list[str]:
    top = max(1, min(int(n), _MAX_TAIL))
    size = path.stat().st_size
    if size > _MAX_READ_BYTES:
        # Read trailing window only for huge logs
        with path.open("rb") as fh:
            fh.seek(max(0, size - _MAX_READ_BYTES))
            raw = fh.read().decode("utf-8", errors="replace")
        # Drop partial first line after seek
        if size > _MAX_READ_BYTES and "\n" in raw:
            raw = raw.split("\n", 1)[1]
    else:
        raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    return lines[-top:]


def _clip(line: str) -> str:
    s = line.replace("\r", "").rstrip()
    if len(s) <= _MAX_LINE_CHARS:
        return s
    return s[:_MAX_LINE_CHARS] + "…"


def status() -> dict[str, Any]:
    """Audit directory + primary log presence. Returns {ok, evidence}."""
    try:
        logs = _list_viv_logs()
        primary = AUDIT_DIR / PRIMARY_LOG
        v2_n = 0
        if V2_LOGS.is_dir():
            v2_n = sum(1 for p in V2_LOGS.glob("audit_*.jsonl") if p.is_file())
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "registry_id": REGISTRY_ID,
                "op": "status",
                "at": _utc(),
                "s_n": _s_n(),
                "audit_dir": _as_posix(AUDIT_DIR),
                "audit_dir_exists": AUDIT_DIR.is_dir(),
                "primary_log": PRIMARY_LOG,
                "primary_exists": primary.is_file(),
                "primary_bytes": primary.stat().st_size if primary.is_file() else 0,
                "viv_log_count": len(logs),
                "logs_sample": logs[:12],
                "v2_audit_readable": V2_AUDIT.is_dir(),
                "v2_logs_dir": _as_posix(V2_LOGS) if V2_LOGS.is_dir() else None,
                "v2_audit_jsonl_count": v2_n,
                "viv_writes_v2": False,
                "note": "Prefer Viv artifacts/audit; V2 audit_core logs are read-only.",
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "status",
                "at": _utc(),
                "error": str(exc),
            },
        }


def tail(log_name: str, n: int = 20) -> dict[str, Any]:
    """Tail last n lines of a named audit log (Viv first)."""
    top = max(1, min(int(n), _MAX_TAIL))
    path, source = _resolve_log(log_name)
    if path is None:
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "tail",
                "at": _utc(),
                "log_name": log_name,
                "error": source,
                "audit_dir": _as_posix(AUDIT_DIR),
            },
        }
    try:
        lines = [_clip(ln) for ln in _tail_lines(path, top)]
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "tail",
                "at": _utc(),
                "log_name": path.name,
                "path": _as_posix(path),
                "source": source,
                "n_requested": top,
                "n_returned": len(lines),
                "lines": lines,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "tail",
                "at": _utc(),
                "log_name": path.name,
                "path": _as_posix(path),
                "error": str(exc),
            },
        }


def search(query: str, n: int = 20) -> dict[str, Any]:
    """Search recent Viv audit logs for query (case-insensitive substring)."""
    q = (query or "").strip()
    top = max(1, min(int(n), _MAX_TAIL))
    if not q:
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "search",
                "at": _utc(),
                "error": "empty_query",
            },
        }
    try:
        pattern = re.compile(re.escape(q), re.IGNORECASE)
        hits: list[dict[str, Any]] = []
        # Prefer primary + newest logs
        candidates: list[Path] = []
        primary = AUDIT_DIR / PRIMARY_LOG
        if primary.is_file():
            candidates.append(primary)
        for row in _list_viv_logs(_MAX_SEARCH_FILES):
            p = Path(str(row.get("path") or ""))
            if p.is_file() and p not in candidates:
                candidates.append(p)
        files_scanned = 0
        for path in candidates[:_MAX_SEARCH_FILES]:
            files_scanned += 1
            try:
                for ln in _tail_lines(path, 500):
                    if pattern.search(ln):
                        hits.append(
                            {
                                "log": path.name,
                                "path": _as_posix(path),
                                "line": _clip(ln),
                            }
                        )
                        if len(hits) >= top:
                            break
            except OSError:
                continue
            if len(hits) >= top:
                break
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "search",
                "at": _utc(),
                "query": q,
                "n_requested": top,
                "n_hits": len(hits),
                "files_scanned": files_scanned,
                "hits": hits,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "search",
                "at": _utc(),
                "query": q,
                "error": str(exc),
            },
        }


def run_smoke() -> dict[str, Any]:
    """Prove real prt_autonomous.log tail + search + status."""
    st = status()
    ta = tail(PRIMARY_LOG, 5)
    # Prefer a token that appears in real autonomous audit rows
    sq = search("autonomous", 5)
    if not (sq.get("evidence") or {}).get("n_hits"):
        sq = search("integrity", 5)
    sev = st.get("evidence") or {}
    tev = ta.get("evidence") or {}
    qev = sq.get("evidence") or {}
    ok = (
        bool(st.get("ok"))
        and bool(sev.get("primary_exists"))
        and bool(ta.get("ok"))
        and int(tev.get("n_returned") or 0) > 0
        and bool(sq.get("ok"))
        and int(qev.get("n_hits") or 0) > 0
        and tev.get("source") == "viv_audit"
        and sev.get("viv_writes_v2") is False
    )
    evidence = {
        "adapter": ADAPTER_ID,
        "op": "smoke",
        "at": _utc(),
        "status_ok": bool(st.get("ok")),
        "tail_ok": bool(ta.get("ok")),
        "search_ok": bool(sq.get("ok")),
        "primary_exists": sev.get("primary_exists"),
        "primary_bytes": sev.get("primary_bytes"),
        "tail_n": tev.get("n_returned"),
        "tail_path": tev.get("path"),
        "search_query": qev.get("query"),
        "search_hits": qev.get("n_hits"),
        "viv_log_count": sev.get("viv_log_count"),
        "status": st,
        "tail": ta,
        "search": sq,
    }
    try:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        slim = {
            "ok": ok,
            "at": evidence["at"],
            "primary_exists": sev.get("primary_exists"),
            "tail_n": tev.get("n_returned"),
            "tail_path": tev.get("path"),
            "search_query": qev.get("query"),
            "search_hits": qev.get("n_hits"),
        }
        ADAPTER_EVIDENCE.write_text(json.dumps(slim, indent=2), encoding="utf-8")
        evidence["evidence_path"] = _as_posix(ADAPTER_EVIDENCE)
    except OSError as exc:
        evidence["evidence_write_error"] = str(exc)
    return {"ok": ok, "evidence": evidence}


if __name__ == "__main__":
    result = run_smoke()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("ok") else 1)
