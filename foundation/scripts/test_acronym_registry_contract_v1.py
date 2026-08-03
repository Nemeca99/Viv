#!/usr/bin/env python3
"""Focused regression checks for CPU-owned acronym repair."""
from __future__ import annotations

from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from voice_core.acronym_registry import repair_acronym_usage, validate_acronym_usage


def main() -> int:
    malformed = "Viv remains inside Adaptive Intelligent Operating System (Adaptive Intelligent Operating Suite = AIOS)."
    repaired = repair_acronym_usage(malformed)
    assert repaired["repaired"] == "Viv remains inside Adaptive Intelligent Operating System (AIOS)."
    assert repaired["pass"] is True
    assert not validate_acronym_usage(str(repaired["repaired"]))

    unknown = "The ZXQ layer is not in the CPU registry."
    unresolved = repair_acronym_usage(unknown)
    assert unresolved["pass"] is False
    assert any(item.get("token") == "ZXQ" for item in unresolved["unresolved"])
    print("ACRONYM_REGISTRY_CONTRACT_PASS cases=2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
