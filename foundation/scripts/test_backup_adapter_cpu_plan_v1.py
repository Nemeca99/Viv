"""Focused tests for the governed backup adapter's pure planner."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_adapter_backup import cpu_plan  # noqa: E402


def main() -> int:
    plan = cpu_plan(
        trigger="pre-coder-edit",
        source_paths=["L:/Continue/Viv/foundation/lib/example.py"],
        manifest_items=[{"path": "L:/Continue/Viv/foundation/lib/example.py", "bytes": 10, "sha256": "a" * 64}],
        manifest_created_at="2026-08-04T12:00:00Z",
    )
    assert plan["ok"], plan
    assert plan["sections"]["manifest_verification"]["ok"], plan
    assert plan["sections"]["snapshot"]["execution_approved"] is False, plan
    assert plan["filesystem_write_performed"] is False, plan
    assert plan["security_authorization_requested"] is False, plan
    assert plan["live_restore_performed"] is False, plan
    print(
        json.dumps(
            {
                "ok": True,
                "failed_sections": plan["failed_sections"],
                "manifest_verified": plan["sections"]["manifest_verification"]["ok"],
                "execution_approved": plan["sections"]["snapshot"]["execution_approved"],
                "filesystem_write_performed": False,
                "security_authorization_requested": False,
                "llm_authority": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
