"""Callable dream_core adapter — wrap Viv REM artifacts (REAL, not bridge inventory).

Registry id: dream_core
V2 source (read-only): L:/Continue/FSAA/Luna/AIOS_V2/dream_core

API: status(), latest(), list_recent(n), run_smoke()

Prefers Viv sandbox/dream + carma/dream mirror + organism dream_state under
foundation. Does not execute V2 DreamCore (Luna deps). Does not mutate
security_core.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.aios_dream import (  # noqa: E402
    CARMA_DREAM_MIRROR,
    DREAM_LATEST,
    DREAM_LOG,
    DREAM_ROOT,
    DREAM_STATE,
)
from lib.paths import AUTO_ARTIFACTS, SANDBOX_ROOT  # noqa: E402
from lib.dream_core import (  # noqa: E402
    archive_plan,
    metrics,
    module_status as cpu_module_status,
    plan_trigger,
    scan_fragments,
)

ADAPTER_ID = "dream_core"
REGISTRY_ID = "dream_core"

V2_DREAM = Path(r"L:/Continue/FSAA/Luna/AIOS_V2/dream_core")
JOURNAL_DIR = SANDBOX_ROOT / "journal"
EVIDENCE_DIR = AUTO_ARTIFACTS / "dream"
ADAPTER_EVIDENCE = EVIDENCE_DIR / "adapter_smoke.json"

_MAX_PREVIEW = 480
_MAX_LIST = 50


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


def _load_state() -> dict[str, Any]:
    if not DREAM_STATE.is_file():
        return {}
    try:
        raw = json.loads(DREAM_STATE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _dream_files() -> list[Path]:
    """Newest-first dream_*.txt from sandbox dream root (preferred) + CARMA mirror."""
    seen: set[str] = set()
    files: list[Path] = []
    for root in (DREAM_ROOT, CARMA_DREAM_MIRROR):
        if not root.is_dir():
            continue
        for path in root.glob("dream_*.txt"):
            key = path.name
            if key in seen:
                continue
            seen.add(key)
            files.append(path)
    files.sort(key=lambda p: p.stat().st_mtime if p.is_file() else 0.0, reverse=True)
    return files


def _preview(text: str, n: int = _MAX_PREVIEW) -> str:
    body = (text or "").replace("\r\n", "\n").strip()
    if len(body) <= n:
        return body
    return body[:n] + "…"


def _v2_presence() -> dict[str, Any]:
    core_py = V2_DREAM / "dream_core.py"
    cycles = V2_DREAM / "core_functions" / "dream_cycles.py"
    return {
        "v2_dream_readable": V2_DREAM.is_dir(),
        "v2_dream_core_py": core_py.is_file(),
        "v2_dream_cycles_py": cycles.is_file(),
        "viv_executes_v2": False,
        "note": "V2 DreamCore surveyed read-only; Viv uses lib/aios_dream artifacts.",
    }


def status() -> dict[str, Any]:
    """Dream roots + organism state snapshot. Returns {ok, evidence}."""
    try:
        files = _dream_files()
        state = _load_state()
        journal_n = 0
        if JOURNAL_DIR.is_dir():
            journal_n = sum(1 for p in JOURNAL_DIR.iterdir() if p.is_file())
        latest_exists = DREAM_LATEST.is_file()
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "registry_id": REGISTRY_ID,
                "op": "status",
                "at": _utc(),
                "s_n": _s_n(),
                "dream_root": _as_posix(DREAM_ROOT),
                "dream_root_exists": DREAM_ROOT.is_dir(),
                "carma_mirror": _as_posix(CARMA_DREAM_MIRROR),
                "carma_mirror_exists": CARMA_DREAM_MIRROR.is_dir(),
                "dream_state_path": _as_posix(DREAM_STATE),
                "dream_state_exists": DREAM_STATE.is_file(),
                "dream_log_path": _as_posix(DREAM_LOG),
                "dream_log_exists": DREAM_LOG.is_file(),
                "latest_path": _as_posix(DREAM_LATEST),
                "latest_exists": latest_exists,
                "dream_file_count": len(files),
                "cycles": state.get("cycles"),
                "last_dream_at": state.get("last_dream_at"),
                "last_dream_path": state.get("last_dream_path"),
                "journal_dir": _as_posix(JOURNAL_DIR),
                "journal_file_count": journal_n,
                "viv_module": "lib.aios_dream",
                "cpu_planner": cpu_module_status(),
                "v2": _v2_presence(),
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


def cycle_plan(
    *,
    idle_minutes: float = 0.0,
    active_conversation: bool = False,
    fragments_since_last: int | None = None,
    hours_since_last: float | None = None,
    manual_request: bool = False,
    pulse_elapsed_seconds: float = 0.0,
    pulse_bpm: float | None = None,
    s_n: float | None = None,
) -> dict[str, Any]:
    """Return a CPU-only trigger plan from supplied or current artifact metadata."""
    state = _load_state()
    live_chars = int(state.get("last_live_chars") or 0)
    fragments = int(state.get("fragments_since_last") or 0) if fragments_since_last is None else int(fragments_since_last)
    hours = float(state.get("hours_since_last") or 0.0) if hours_since_last is None else float(hours_since_last)
    return plan_trigger(
        active_conversation=active_conversation,
        idle_minutes=idle_minutes,
        fragments_since_last=fragments,
        hours_since_last=hours,
        manual_request=manual_request,
        pulse_elapsed_seconds=pulse_elapsed_seconds,
        pulse_bpm=pulse_bpm,
        s_n=_s_n() if s_n is None else s_n,
    ) | {"live_chars_observed": live_chars, "artifact_reads_performed": True}


def consolidation_plan(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Scan caller-supplied records and return a non-mutating archive plan."""
    scan = scan_fragments(records)
    archive = archive_plan(scan)
    return {
        "ok": bool(scan.get("ok") and archive.get("ok")),
        "scan": scan,
        "archive": archive,
        "metrics": metrics(scan),
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
    }


def latest() -> dict[str, Any]:
    """Read newest dream summary (latest_summary.txt or newest dream_*.txt)."""
    try:
        path: Path | None = None
        source = "none"
        if DREAM_LATEST.is_file():
            path = DREAM_LATEST
            source = "latest_summary"
        else:
            files = _dream_files()
            if files:
                path = files[0]
                source = "newest_dream_file"
        if path is None:
            return {
                "ok": False,
                "evidence": {
                    "adapter": ADAPTER_ID,
                    "op": "latest",
                    "at": _utc(),
                    "error": "no_dream_artifacts",
                    "dream_root": _as_posix(DREAM_ROOT),
                },
            }
        text = path.read_text(encoding="utf-8", errors="replace")
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "latest",
                "at": _utc(),
                "source": source,
                "path": _as_posix(path),
                "bytes": path.stat().st_size,
                "chars": len(text),
                "preview": _preview(text),
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "latest",
                "at": _utc(),
                "error": str(exc),
            },
        }


def list_recent(n: int = 5) -> dict[str, Any]:
    """List newest-first dream files (metadata + short preview)."""
    top = max(1, min(int(n), _MAX_LIST))
    try:
        rows: list[dict[str, Any]] = []
        for path in _dream_files()[:top]:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                st = path.stat()
                rows.append(
                    {
                        "name": path.name,
                        "path": _as_posix(path),
                        "bytes": st.st_size,
                        "mtime": datetime.fromtimestamp(
                            st.st_mtime, tz=timezone.utc
                        )
                        .replace(microsecond=0)
                        .isoformat(),
                        "preview": _preview(text, 160),
                    }
                )
            except OSError as exc:
                rows.append({"name": path.name, "path": _as_posix(path), "error": str(exc)})
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "list_recent",
                "at": _utc(),
                "n_requested": top,
                "n_returned": len(rows),
                "dreams": rows,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "list_recent",
                "at": _utc(),
                "error": str(exc),
            },
        }


def run_smoke() -> dict[str, Any]:
    """Prove artifact reads plus the deterministic CPU planning boundary."""
    st = status()
    lat = latest()
    recent = list_recent(3)
    plan = plan_trigger(
        idle_minutes=10,
        fragments_since_last=100,
        hours_since_last=24,
        pulse_bpm=0.1,
        s_n=0.8,
    )
    candidates = consolidation_plan(
        [
            {"id": "a", "text": "Dream records preserve provenance."},
            {"id": "b", "text": "Dream records preserve provenance."},
        ]
    )
    sev = st.get("evidence") or {}
    lev = lat.get("evidence") or {}
    rev = recent.get("evidence") or {}
    count = int(sev.get("dream_file_count") or 0)
    n_returned = int(rev.get("n_returned") or 0)
    ok = (
        bool(st.get("ok"))
        and bool(lat.get("ok"))
        and bool(recent.get("ok"))
        and count > 0
        and n_returned > 0
        and bool(lev.get("preview"))
        and sev.get("v2", {}).get("viv_executes_v2") is False
        and plan.get("state") == "PLANNED"
        and candidates.get("archive", {}).get("delete_source_records") is False
        and candidates.get("writes_performed") is False
    )
    evidence = {
        "adapter": ADAPTER_ID,
        "op": "smoke",
        "at": _utc(),
        "status_ok": bool(st.get("ok")),
        "latest_ok": bool(lat.get("ok")),
        "list_ok": bool(recent.get("ok")),
        "dream_file_count": count,
        "n_returned": n_returned,
        "latest_source": lev.get("source"),
        "latest_path": lev.get("path"),
        "cycles": sev.get("cycles"),
        "v2_dream_readable": (sev.get("v2") or {}).get("v2_dream_readable"),
        "viv_executes_v2": (sev.get("v2") or {}).get("viv_executes_v2"),
        "cpu_plan_state": plan.get("state"),
        "cpu_plan_mode": plan.get("mode"),
        "duplicate_groups": len(candidates.get("scan", {}).get("duplicate_groups") or []),
        "archive_delete_source_records": candidates.get("archive", {}).get("delete_source_records"),
        "status": st,
        "latest": lat,
        "list_recent": recent,
    }
    try:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        slim = {
            "ok": ok,
            "at": evidence["at"],
            "dream_file_count": count,
            "n_returned": n_returned,
            "latest_source": lev.get("source"),
            "latest_path": lev.get("path"),
            "cycles": sev.get("cycles"),
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
