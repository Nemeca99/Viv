"""Capture clean spoken lines as PRT-friendly gold English (CPU side)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import ARTIFACTS

VOICE_GOLD_PATH = ARTIFACTS / "models" / "voice_gold_speaks.jsonl"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_gold_speak(
    *,
    query: str,
    text: str,
    s_n: float,
    status: str,
    voice_source: str,
    packet: dict[str, Any] | None = None,
) -> Path | None:
    """Persist a clean egress-allowed line for later PRT / SFT oversample."""
    t = (text or "").strip()
    if len(t) < 40 or len(t) > 320:
        return None
    if "only only" in t or "rather rather" in t:
        return None
    if "SECURITY OUT" in t or t.startswith("["):
        return None
    facts = (packet or {}).get("facts") or []
    prompt = (
        "Translate measured facts into clear English only. Do not invent. Do not gaslight. Do not decide. "
        "Master S_n is life.\n"
        f"Tone: measured.\nQuery: {query or 'state summary'}\n"
        f"Status: {status} S_n={float(s_n):.4f}\n"
        f"Facts:\n" + "\n".join(f"- {f}" for f in facts[:6]) + "\n"
        "Spoken report:\nArchitect: "
    )
    row = {
        "timestamp": _utc(),
        "source": voice_source,
        "s_n": float(s_n),
        "status": status,
        "query": query,
        "text": prompt + t,
        "completion": t,
    }
    VOICE_GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    with VOICE_GOLD_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return VOICE_GOLD_PATH
