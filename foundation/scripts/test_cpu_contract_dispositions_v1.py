"""Truthful dispositions for non-authoritative source-only cores."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.core_contracts import contract_report  # noqa: E402


def main() -> None:
    report = contract_report()
    assert report["counts"] == {"wired": 29, "optional": 2, "ui_only": 1, "retired": 1}
    assert "source_only" not in report["counts"]
    rows = {row["core_id"]: row for row in report["cores"]}
    assert rows["streamlit_core"]["state"] == "ui_only"
    assert rows["marketplace_core"]["state"] == "optional"
    assert rows["music_core"]["state"] == "optional"
    assert rows["template_core"]["state"] == "retired"
    for core_id in ("streamlit_core", "marketplace_core", "music_core", "template_core"):
        assert rows[core_id]["disposition_reason"]
    print({"ok": True, "counts": report["counts"], "ambiguous_source_only": 0})


if __name__ == "__main__":
    main()
