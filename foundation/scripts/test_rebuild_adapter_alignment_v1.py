"""Read-only proof that the current rebuild planner sees adapter-backed cores."""
from __future__ import annotations

import sys
from pathlib import Path

VIV = Path(__file__).resolve().parents[2]
FOUNDATION = VIV / "foundation"
for path in (VIV, FOUNDATION):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.viv_ide import _ADAPTER_DONE, tool_rebuild_ticket  # noqa: E402


def main() -> int:
    missing = []
    for adapter in sorted(set(_ADAPTER_DONE.values())):
        if not (FOUNDATION / "lib" / f"{adapter}.py").is_file():
            missing.append(adapter)
    ticket = tool_rebuild_ticket()
    assert not missing, missing
    assert ticket.get("ok") is True
    assert ticket.get("next_ids") == []
    assert ticket.get("partial_n") == 0
    assert ticket.get("legacy_n") == 0
    print(
        "REBUILD_ADAPTER_ALIGNMENT_PASS "
        f"adapter_files={len(set(_ADAPTER_DONE.values()))} "
        f"planner_next=0 registry_snapshot_documentation_hold=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
