"""Ensure live-memory priority cannot create unrelated knowledge hits."""
from __future__ import annotations

import sys
from pathlib import Path

VIV = Path(__file__).resolve().parents[2]
FOUNDATION = VIV / "foundation"
for path in (VIV, FOUNDATION):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.aios_adapter_knowledge import query  # noqa: E402


def main() -> int:
    result = query("Autism spectrum", k=5)
    hits = result.get("hits") or []
    assert all(
        "autism" in str(hit.get("text") or "").casefold()
        or "spectrum" in str(hit.get("text") or "").casefold()
        for hit in hits
    ), hits
    assert not any(str(hit.get("source") or "").startswith("live:") for hit in hits), hits
    print(f"KNOWLEDGE_RELEVANCE_GATE_PASS hits={len(hits)} live_unrelated_rejected=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
