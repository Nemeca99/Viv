"""Focused tests for the read-only CPU sandbox policy boundary."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_sandbox_boundary import evaluate_request, scan_code, validate_path  # noqa: E402


def main() -> None:
    good = evaluate_request({"operation": "write_file", "path": "code/probe.txt", "source": "print('ok')"})
    assert good["ok"] and good["state"] == "VERIFIED_PLAN_ONLY" and good["effect_authorized"] is False
    assert good["backup_required_before_effect"] is True and good["writes"] is False
    assert not validate_path("../outside.txt")["ok"]
    assert not validate_path("C:/Windows/system32/x.dll")["ok"]
    assert not scan_code("import subprocess\nsubprocess.run([])")["ok"]
    assert not evaluate_request({"operation": "shell", "path": "code/x.txt"})["ok"]
    print({"ok": True, "plan_only": True, "path_escape_denied": True, "code_scan_denied": True, "effect_authorized": False})


if __name__ == "__main__":
    main()
