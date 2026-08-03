"""Viv dream cycle — CARMA consolidation (doctrine §15).

Rebuilds memory by creating a new dream file and summarizing live material.
Old files are archived, never deleted. Raw data stays auditable.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.master_rid import load_master_rid
from lib.paths import AUTO_ARTIFACTS, CARMA_ARTIFACTS, VIV_ROOT
from lib.security_membrane import tool_gate

# Prefer Viv's Law-7 home; keep CARMA dream provenance mirrored for retrieve.
from lib.aios_sandbox import DREAM as SANDBOX_DREAM
from lib.aios_sandbox import DREAM_ARCHIVE as SANDBOX_DREAM_ARCHIVE
from lib.aios_sandbox import ensure_sandbox_home

DREAM_ROOT = SANDBOX_DREAM
LIVE_CURRENT = CARMA_ARTIFACTS / "live" / "current.txt"
ARCHIVE_ROOT = SANDBOX_DREAM_ARCHIVE
DREAM_LOG = AUTO_ARTIFACTS / "organism" / "dreams.jsonl"
DREAM_STATE = AUTO_ARTIFACTS / "organism" / "dream_state.json"
DREAM_LATEST = DREAM_ROOT / "latest_summary.txt"
# CARMA mirror (provenance [dream] still under artifacts/carma for SemanticMemory)
CARMA_DREAM_MIRROR = CARMA_ARTIFACTS / "dream"

_WORD = re.compile(r"[a-zA-Z0-9_]{3,}")


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _gated_write(path: Path, content: str, s_n: float) -> tuple[bool, str]:
    gate_path = str(path).replace("\\", "/")
    verdict = tool_gate("write_file", {"path": gate_path, "content": content}, s_n)
    if not verdict.get("allowed"):
        return False, str(verdict.get("reason", "tool_gate_denied"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True, "write_ok"


def _load_state() -> dict[str, Any]:
    if not DREAM_STATE.is_file():
        return {"cycles": 0, "last_dream_at": None}
    try:
        return json.loads(DREAM_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"cycles": 0, "last_dream_at": None}


def _save_state(state: dict[str, Any]) -> None:
    DREAM_STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DREAM_STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(DREAM_STATE)


def _append_log(row: dict[str, Any]) -> None:
    DREAM_LOG.parent.mkdir(parents=True, exist_ok=True)
    with DREAM_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def _read_live_corpus(max_chars: int = 24000) -> str:
    chunks: list[str] = []
    if LIVE_CURRENT.is_file():
        chunks.append(LIVE_CURRENT.read_text(encoding="utf-8", errors="replace"))
    live_dir = CARMA_ARTIFACTS / "live"
    if live_dir.is_dir():
        for path in sorted(live_dir.glob("*.txt")):
            if path.name == "current.txt":
                continue
            try:
                chunks.append(path.read_text(encoding="utf-8", errors="replace")[:4000])
            except OSError:
                continue
    # Recent organism activity is part of lived experience
    activity = AUTO_ARTIFACTS / "organism" / "ACTIVITY.md"
    if activity.is_file():
        try:
            chunks.append(activity.read_text(encoding="utf-8", errors="replace")[-6000:])
        except OSError:
            pass
    text = "\n".join(chunks)
    if len(text) > max_chars:
        text = text[-max_chars:]
    return text


def _self_conversation(corpus: str, s_n: float, cycle: int) -> str:
    """CPU self-dialogue over live memory — no GPU required for the dream body."""
    lines = [ln.strip() for ln in corpus.splitlines() if ln.strip()]
    recent = lines[-40:] if lines else ["(empty live memory — first dream)"]
    words: dict[str, int] = {}
    for ln in recent:
        for w in _WORD.findall(ln.lower()):
            if w in {"the", "and", "for", "with", "from", "this", "that", "have", "been"}:
                continue
            words[w] = words.get(w, 0) + 1
    top = sorted(words.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
    themes = ", ".join(f"{w}x{c}" for w, c in top) if top else "silence"

    ask = (
        f"Cycle {cycle}: What did I live since last dream? "
        f"S_n={s_n:.4f}. Themes: {themes}."
    )
    answer_bits = []
    for ln in recent[-12:]:
        preview = ln[:160]
        answer_bits.append(f"  - {preview}")
    answer = "\n".join(answer_bits) if answer_bits else "  - nothing yet"

    return (
        f"[dream][{_utc()}] REM consolidation #{cycle}\n"
        f"SELF: {ask}\n"
        f"SELF: I archive the raw trail and keep this compressed truth:\n"
        f"{answer}\n"
        f"SELF: Themes I will carry forward: {themes}.\n"
        f"SELF: Old files stay in archive. I do not erase my past.\n"
    )


def perform_dream_cycle(*, force: bool = False, min_live_chars: int = 80) -> dict[str, Any]:
    """One REM consolidation: summarize live → her sandbox/dream → archive → CARMA remember."""
    ensure_sandbox_home()
    DREAM_ROOT.mkdir(parents=True, exist_ok=True)
    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    CARMA_DREAM_MIRROR.mkdir(parents=True, exist_ok=True)

    try:
        sn = float(load_master_rid().master_s_n)
    except Exception:  # noqa: BLE001
        sn = 0.5

    if sn < 0.37 and not force:
        return {"ok": False, "skipped": "s_n_dormancy", "s_n": sn}

    state = _load_state()
    cycle = int(state.get("cycles") or 0) + 1
    corpus = _read_live_corpus()
    if len(corpus.strip()) < min_live_chars and not force:
        return {
            "ok": True,
            "skipped": "thin_live_memory",
            "live_chars": len(corpus),
            "s_n": sn,
            "hint": "live longer or force=True",
        }

    summary = _self_conversation(corpus, sn, cycle)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dream_path = DREAM_ROOT / f"dream_{stamp}_c{cycle}.txt"
    archive_path = ARCHIVE_ROOT / f"live_snapshot_{stamp}_c{cycle}.txt"
    carma_mirror_path = CARMA_DREAM_MIRROR / f"dream_{stamp}_c{cycle}.txt"

    ok_a, reason_a = _gated_write(archive_path, corpus if corpus else "(empty)\n", sn)
    if not ok_a:
        return {"ok": False, "reason": f"archive_denied:{reason_a}", "s_n": sn}

    ok_d, reason_d = _gated_write(dream_path, summary, sn)
    if not ok_d:
        return {"ok": False, "reason": f"dream_denied:{reason_d}", "s_n": sn}

    ok_l, reason_l = _gated_write(DREAM_LATEST, summary, sn)
    if not ok_l:
        return {"ok": False, "reason": f"latest_denied:{reason_l}", "s_n": sn}

    _gated_write(carma_mirror_path, summary, sn)

    remembered: dict[str, Any] = {}
    try:
        from lib.carma_memory import remember

        remembered = remember(
            f"Dream #{cycle}: consolidated {len(corpus)} live chars -> {dream_path.name}",
            provenance="dream",
            tags=["dream", "rem", "consolidate", "sandbox"],
            s_n=sn,
        )
    except Exception as exc:  # noqa: BLE001
        remembered = {"ok": False, "error": str(exc)}

    state.update(
        {
            "cycles": cycle,
            "last_dream_at": _utc(),
            "last_dream_path": str(dream_path).replace("\\", "/"),
            "last_archive_path": str(archive_path).replace("\\", "/"),
            "sandbox_home": "L:/Continue/Viv/sandbox/",
            "last_s_n": sn,
            "last_live_chars": len(corpus),
        }
    )
    _save_state(state)

    report = {
        "ok": True,
        "cycle": cycle,
        "s_n": sn,
        "live_chars": len(corpus),
        "sandbox": "L:/Continue/Viv/sandbox/",
        "dream_path": str(dream_path).replace("\\", "/"),
        "archive_path": str(archive_path).replace("\\", "/"),
        "latest_path": str(DREAM_LATEST).replace("\\", "/"),
        "summary_preview": summary[:400],
        "remembered": remembered,
        "at": _utc(),
    }
    _append_log({"event": "dream_cycle", **{k: report[k] for k in report if k != "summary_preview"}})
    return report


def dream_due(*, every_n_beats: int, beat_index: int) -> bool:
    if every_n_beats <= 0:
        return False
    return beat_index > 0 and (beat_index % every_n_beats == 0)
