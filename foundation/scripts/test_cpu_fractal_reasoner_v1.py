"""Bounded recursive CPU fractal decomposition regression."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_fractal_reasoner import decompose  # noqa: E402


def main() -> int:
    result = decompose("Why does retrieval work and how does the CPU verify facts then render them?", max_depth=3, max_nodes=64)
    assert result["ok"] is True and result["bounded"] is True
    assert result["node_count"] > 1 and result["depth_limit"] == 3
    shallow = decompose("a and b and c and d", max_depth=0, max_nodes=1)
    assert shallow["node_count"] == 1 and shallow["leaf_count"] == 1
    empty = decompose("")
    assert empty["ok"] is False
    assert result["facts_asserted"] is False and result["llm_authority"] is False
    print(json.dumps({"ok": True, "node_count": result["node_count"], "leaf_count": result["leaf_count"], "bounded": result["bounded"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
