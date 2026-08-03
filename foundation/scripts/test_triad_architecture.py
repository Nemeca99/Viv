"""Static package coverage, bridge isolation, and frozen boundary inventory."""
from __future__ import annotations

import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.triad_architecture import scan_architecture  # noqa: E402


def main() -> int:
    report = scan_architecture()
    assert report["coverage_pct"] == 100.0, report["uncovered"]
    assert not report["direct_bridge_violations"], report["direct_bridge_violations"]
    assert not report["syntax_errors"], report["syntax_errors"]
    assert report["boundary_registry_error"] is None, report["boundary_registry_error"]
    assert report["ok"], report["errors"]
    print(
        json.dumps(
            {
                "ok": True,
                "python_files": report["python_files"],
                "coverage_pct": report["coverage_pct"],
                "boundary_modules": report["boundary_modules"],
                "direct_bridge_violations": 0,
                "registry_drift": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
