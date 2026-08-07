"""Read-only adapter regression tests for data_core."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_adapter_data import cpu_plan, run_smoke, status  # noqa: E402
from lib.data_core import make_record  # noqa: E402


def main() -> int:
    row = make_record(
        {"kind": "adapter-fixture"},
        record_id="data-adapter-fixture",
        record_type="fixture",
        source="test",
        provenance="fixture",
        created_utc="2025-12-31T00:00:00Z",
    )
    planned = cpu_plan([row], now_utc="2026-01-01T00:00:00Z")
    smoke = run_smoke()
    observed = status()
    assert planned["ok"] is True, planned
    assert planned["manifest"]["state"] == "VERIFIED", planned
    assert planned["cleanup_plan"]["delete_performed"] is False, planned
    assert smoke["ok"] is True, smoke
    assert observed["ok"] is True and observed["evidence"]["writes_performed"] is False, observed
    print(
        json.dumps(
            {
                "ok": True,
                "manifest": planned["manifest"]["state"],
                "cleanup": planned["cleanup_plan"]["state"],
                "smoke": smoke["evidence"],
                "writes_performed": False,
                "execution_performed": False,
                "llm_authority": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
