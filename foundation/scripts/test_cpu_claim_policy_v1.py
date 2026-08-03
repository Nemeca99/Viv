"""Claim provenance, privacy, conflict, and telemetry policy regression."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_claim_policy import verify_packet  # noqa: E402


def packet(value: str, **source):
    return {"version": "1.0", "authority": "test", "query": "q", "state": "VERIFIED", "facts": [{"claim": "c", "value": value, "source": {"sha256": "abc", "root": "F_AI_DATASETS", "kind": "article", **source}}], "conflicts": []}


def main() -> int:
    safe = verify_packet(packet("A fact from F:\\private\\article.txt"))
    assert safe["ok"] is True
    assert safe["packet"]["internal_paths_exposed"] is False
    assert "F:" not in safe["packet"]["facts"][0]["value"]
    assert "path" not in safe["packet"]["facts"][0]["source"]
    telemetry = verify_packet(packet("Master S_n=0.7"))
    assert telemetry["ok"] is False and telemetry["reason"] == "telemetry_in_fact"
    conflict = verify_packet({**packet("x"), "conflicts": ["c"]})
    assert conflict["ok"] is False and conflict["reason"] == "packet_conflict"
    missing = verify_packet(packet("x", sha256=""))
    assert missing["ok"] is False and missing["reason"] == "fact_missing_provenance"
    print(json.dumps({"ok": True, "redaction": True, "telemetry_blocked": True, "conflict_blocked": True, "provenance_required": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
