"""Focused contract tests for the reversible RID shadow."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.rid_recursive_shadow import probe, transform, verify  # noqa: E402


def main() -> None:
    good = verify((0.2, 0.3, 0.5), tick=4, phase="A")
    assert good.ok and good.status == "VERIFIED"
    assert good.magnitude == 1.0
    assert verify((2.0, 3.0, 5.0), tick=1, phase="B").ok
    assert not verify((0.0, 0.3, 0.7)).ok
    assert not verify((0.2, 0.3, 0.5), tick=4, phase="B").ok
    assert not verify((0.2, 0.3, 0.5), tick=4, phase="C").ok
    assert not verify((0.2, 0.3, 0.5), tick=4, phase="A", tolerance=-1).ok
    tampered = transform(transform((0.2, 0.3, 0.5)))
    assert all(abs(a - b) < 1e-10 for a, b in zip(tampered, (0.2, 0.3, 0.5)))
    result = probe({"triad": [0.2, 0.3, 0.5], "tick": 0, "phase": "A"})
    assert result["ok"] and result["writes"] is False and result["llm"] is False
    assert result["master_rid_mutated"] is False
    print({"ok": True, "involution": True, "phase_gate": True, "magnitude_preserved": True, "side_effects": False})


if __name__ == "__main__":
    main()
