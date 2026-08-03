"""Focused tests for the manual-led consciousness core slice."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_adapter_consciousness import consciousness_state, run_smoke  # noqa: E402
from lib.consciousness_core import (  # noqa: E402
    LongTermMemory,
    ShortTermMemory,
    identity_drift,
    select_soul_fragment,
)


def main() -> int:
    assert select_soul_fragment("repair the broken security boundary") ["selected"] == "healer"
    assert select_soul_fragment("search the manual for truthful knowledge") ["selected"] == "oracle"
    assert select_soul_fragment("write the journal evidence") ["selected"] == "scribe"

    stm = ShortTermMemory()
    for i in range(80):
        result = stm.add(f"event {i}", provenance="test")
        assert result["ok"] is True
    assert stm.consolidation_due is True
    package = stm.prepare_consolidation()
    assert package["ok"] is True and package["record_count"] == 80
    ltm = LongTermMemory()
    committed = ltm.commit_consolidation(package)
    assert committed["ok"] is True and committed["summary"]["semantic_claims"] is False
    cleared = stm.clear_after_commit(committed["summary"]["record_ids"])
    assert cleared["removed"] == 80 and len(stm.records) == 0

    drift = identity_drift(expected_name="Viv", observed_name="Other")
    assert drift["drift"] is True and drift["status"] == "DRIFT_DETECTED"

    state = consciousness_state(prompt="truthful system documentation")
    evidence = state["evidence"]
    assert evidence["fragment"]["selected"] == "oracle"
    assert evidence["writes_performed"] is False
    assert evidence["llm_authority"] is False

    smoke = run_smoke()
    assert smoke["ok"] is True, json.dumps(smoke, indent=2, default=str)
    print(json.dumps({"ok": True, "state": evidence, "smoke_ok": smoke["ok"]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
