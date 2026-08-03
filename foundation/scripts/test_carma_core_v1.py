"""Focused tests for deterministic CARMA fragment planning."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.carma_core import consolidation_package, extract_concepts, make_fragment  # noqa: E402


def main() -> int:
    assert extract_concepts("Neural network training uses neural network backpropagation")[:2] == ["network", "neural"]
    left = make_fragment("Neural network training uses backpropagation", provenance="verified")
    right = make_fragment("Backpropagation trains a neural network", provenance="verified")
    package = consolidation_package([left, right])
    assert package["ok"] is True
    assert package["fragment_count"] == 2
    assert package["links"] and "neural" in package["links"][0]["shared_concepts"]
    assert package["semantic_compression"] == "not_performed"
    assert package["llm_authority"] is False
    print(json.dumps({"ok": True, "package": package}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
