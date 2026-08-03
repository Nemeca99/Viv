"""Callable CARMA adapter — thin wrap over lib/carma_memory (plain-text past layer).

V2 carma_core/carma.py was reviewed read-only: offline hash-embed + cosine grid is
not ported here. Viv CARMA is gated plain-text via memory_core; writes already pass
security_membrane.tool_gate inside carma_memory / memory_core.gate.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.carma_memory import remember as _carma_remember  # noqa: E402
from lib.carma_memory import retrieve as _carma_retrieve  # noqa: E402
from lib.carma_memory import status as _carma_status  # noqa: E402
from lib.security_membrane import membrane_status  # noqa: E402

ADAPTER_ID = "carma"
_SMOKE_TAG = "adapter_carma_smoke"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _s_n() -> float:
    try:
        from lib.master_rid import load_master_rid

        return float(load_master_rid().master_s_n)
    except Exception:  # noqa: BLE001
        return 0.5


def remember(text: str, *, provenance: str = "live", tags: list[str] | None = None) -> dict[str, Any]:
    """Store text in CARMA. Returns {ok, evidence}."""
    body = (text or "").strip()
    if not body:
        return {"ok": False, "evidence": {"error": "empty_text", "adapter": ADAPTER_ID}}
    sn = _s_n()
    out = _carma_remember(
        body,
        provenance=provenance,
        tags=tags or ["carma_adapter"],
        s_n=sn,
    )
    ok = bool(out.get("ok"))
    return {
        "ok": ok,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "remember",
            "at": _utc(),
            "s_n": sn,
            "carma": out,
            "id": out.get("id"),
            "path": out.get("path"),
            "reason": out.get("reason"),
        },
    }


def recall(query: str, k: int = 5, *, tags: list[str] | None = None) -> dict[str, Any]:
    """Retrieve top-k CARMA hits for query. Returns {ok, evidence}."""
    q = (query or "").strip()
    top = max(1, int(k))
    if not q:
        return {"ok": False, "evidence": {"error": "empty_query", "adapter": ADAPTER_ID, "k": top}}
    hits = _carma_retrieve(q, top=top, tags=tags)
    return {
        "ok": True,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "recall",
            "at": _utc(),
            "query": q,
            "k": top,
            "n_hits": len(hits),
            "hits": hits,
        },
    }


def status() -> dict[str, Any]:
    """CARMA + membrane snapshot. Returns {ok, evidence}."""
    try:
        carma = _carma_status()
        mem = membrane_status()
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "status",
                "at": _utc(),
                "carma": carma,
                "membrane": mem,
                "s_n": _s_n(),
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


def run_smoke() -> dict[str, Any]:
    """Prove remember + recall round-trip with a unique marker."""
    marker = f"CARMA_ADAPTER_SMOKE_{_utc().replace(':', '').replace('-', '')}"
    text = f"{marker} rebuild adapter carma callable proof"
    rem = remember(text, provenance="live", tags=[_SMOKE_TAG, "smoke"])
    rec = recall(marker, k=5, tags=[_SMOKE_TAG])
    hits = (rec.get("evidence") or {}).get("hits") or []
    found = any(marker in str(h.get("text") or "") for h in hits)
    st = status()
    ok = bool(rem.get("ok")) and bool(rec.get("ok")) and found
    return {
        "ok": ok,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "smoke",
            "at": _utc(),
            "marker": marker,
            "found": found,
            "remember": rem,
            "recall": rec,
            "status_ok": bool(st.get("ok")),
            "n_hits": len(hits),
        },
    }


if __name__ == "__main__":
    import json
    import sys

    result = run_smoke()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("ok") else 1)
