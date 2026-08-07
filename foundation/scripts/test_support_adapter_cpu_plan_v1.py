"""Read-only adapter regression for support_core."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_adapter_support import cpu_plan, status  # noqa: E402
from lib.support_core import make_cache_entry  # noqa: E402


def main() -> int:
    planned = cpu_plan(
        [{"name": "fixture", "ok": True, "detail": "pass"}],
        [make_cache_entry("adapter fixture", cache_id="adapter-cache", source="test")],
        sample_text="user@example.com",
    )
    observed = status()
    assert planned["ok"] is True, planned
    assert planned["report"]["state"] == "HEALTHY", planned
    assert planned["writes_performed"] is False, planned
    assert observed["ok"] is True, observed
    assert observed["evidence"]["cpu_planner"]["module"] == "support_core", observed
    print(
        json.dumps(
            {
                "ok": True,
                "state": planned["report"]["state"],
                "cache": planned["report"]["cache"]["state"],
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
