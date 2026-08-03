#!/usr/bin/env python3
"""Ensure invented capitalized acronym compounds fail closed at egress."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for path in (FOUNDATION, REPO):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from voice_core.acronym_registry import repair_acronym_usage, validate_acronym_usage  # noqa: E402
from voice_core.runtime_contract import finalize_draft  # noqa: E402


def main() -> int:
    malformed = "The Graphics Processing Unit (GPU-Speech) handles rendering."
    repaired = repair_acronym_usage(malformed)
    assert repaired["pass"] is False, repaired
    assert any(item.get("token") == "GPU-Speech" for item in repaired["unresolved"]), repaired
    assert repaired["repaired"] == malformed, repaired

    packet = {"mode": "converse", "semantic_key": "architecture_cpu_gpu_role"}
    final = finalize_draft(
        query="Give CPU-mind versus GPU-mouth in plain speech.",
        packet=packet,
        raw_text=malformed,
        voice_source="test",
    )
    assert final["acronym_pass"] is True, final
    assert not validate_acronym_usage(final["text"]), final
    assert "GPU-Speech" not in final["text"], final
    print({"ok": True, "unresolved_compound": "GPU-Speech", "regenerated": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
