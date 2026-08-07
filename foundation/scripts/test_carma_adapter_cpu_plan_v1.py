"""Regression for the read-only CARMA adapter planning surface."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_adapter_carma import cpu_plan  # noqa: E402
from lib.carma_core import make_fragment  # noqa: E402


def main() -> int:
    rows = [
        make_fragment("The CPU memory boundary preserves provenance.", provenance="verified", source="test"),
        make_fragment("The CPU memory boundary preserves provenance.", provenance="verified", source="test"),
    ]
    plan = cpu_plan(rows, query="memory provenance", top=2)
    assert plan["ok"] is True, plan
    assert plan["retrieval"]["state"] == "VERIFIED", plan
    assert plan["retrieval"]["semantic_authority"] is False, plan
    assert plan["stm_ltm"]["state"] == "NOT_DUE", plan
    assert plan["writes_performed"] is False, plan
    assert plan["durable_commit_performed"] is False, plan
    assert plan["llm_authority"] is False, plan
    print(
        json.dumps(
            {
                "ok": True,
                "retrieval_state": plan["retrieval"]["state"],
                "retrieval_mode": plan["retrieval"]["retrieval_mode"],
                "stm_state": plan["stm_ltm"]["state"],
                "writes_performed": False,
                "durable_commit_performed": False,
                "llm_authority": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
