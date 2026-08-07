"""Focused tests for deterministic CARMA fragment planning."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.carma_core import (  # noqa: E402
    consolidation_package,
    extract_concepts,
    make_fragment,
    module_status,
    plan_stm_ltm,
    retrieval_packet,
    validate_fragment,
)


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
    assert validate_fragment(left)["state"] == "VERIFIED"
    assert validate_fragment({**left, "content": "tampered"})["reason"] == "fragment_hash_mismatch"
    packet = retrieval_packet("neural network", [left, right], top=2)
    assert packet["state"] == "VERIFIED" and packet["hits"], packet
    assert packet["retrieval_mode"] == "lexical_overlap" and packet["semantic_authority"] is False, packet
    not_due = plan_stm_ltm([left], capacity=4, consolidation_threshold=0.5)
    hold = plan_stm_ltm([left, right], capacity=2, consolidation_threshold=0.5)
    ready = plan_stm_ltm([left, right], capacity=2, consolidation_threshold=0.5, explicit_commit=True)
    assert not_due["state"] == "NOT_DUE", not_due
    assert hold["state"] == "HOLD" and hold["durable_commit_performed"] is False, hold
    assert ready["state"] == "READY_FOR_GOVERNED_EXECUTOR" and ready["writes_performed"] is False, ready
    assert module_status()["llm_authority"] is False
    print(json.dumps({"ok": True, "package": package}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
