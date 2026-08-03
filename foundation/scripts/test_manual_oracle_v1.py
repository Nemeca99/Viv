"""Regression tests for the read-only CPU ManualOracle."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

VIV = Path(__file__).resolve().parents[2]
FOUNDATION = VIV / "foundation"
for path in (VIV, FOUNDATION):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.manual_oracle import ManualOracle  # noqa: E402


def main() -> int:
    oracle = ManualOracle()
    found = oracle.search("architecture manual", top_k=3)
    assert found["state"] == "VERIFIED", found
    assert found["sections"], found
    assert found["source"]["sha256"], found
    anchor = found["sections"][0]["anchor"]
    exact = oracle.lookup(anchor)
    assert exact["state"] == "VERIFIED", exact
    assert exact["sections"][0]["sha256"] == found["sections"][0]["sha256"], (exact, found)

    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "manual.md"
        path.write_text("# One\ntruth\n## Two\nsecond\n", encoding="utf-8")
        drift = ManualOracle(path)
        path.write_text("# One\nchanged\n## Two\nsecond\n", encoding="utf-8")
        abstain = drift.lookup("one")
        assert abstain["state"] == "ABSTAIN" and abstain["reason"] == "source_changed", abstain
    print("MANUAL_ORACLE_PASS verified_lookup=true drift_abstain=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
