"""Bulk contract-map regression for all manual-defined AIOS cores."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.core_contracts import contract_report, get_contract  # noqa: E402


def main() -> int:
    report = contract_report()
    assert report["ok"] is True
    assert report["contract_count"] >= 20
    ids = [row["core_id"] for row in report["cores"]]
    assert len(ids) == len(set(ids))
    for required in ("luna_core", "carma_core", "consciousness_core", "security_core", "rid_core", "main_core"):
        contract = get_contract(required)
        assert contract and contract["acceptance"]
    assert report["training_authorized"] is False
    assert report["llm_authority"] is False
    print(json.dumps({"ok": True, "contract_count": report["contract_count"], "counts": report["counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
