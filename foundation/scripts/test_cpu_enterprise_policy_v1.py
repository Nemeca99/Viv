"""Focused tests for the fail-closed CPU enterprise policy surface."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_enterprise_policy import probe  # noqa: E402


def main() -> None:
    assert probe({"operation": "read"})["allowed"] is True
    assert probe({"operation": "integrate"})["allowed"] is False
    assert probe({"operation": "integrate", "explicit_consent": True, "authority": "architect"})["allowed"] is True
    assert probe({"operation": "shell"})["allowed"] is False
    result = probe({"operation": "data_export", "explicit_consent": True, "authority": "architect", "payload": {"rows": 1}})
    assert result["effect_authorized"] is False and result["external_effect"] is False and result["writes"] is False
    print({"ok": True, "read_allowed": True, "consent_gate": True, "unknown_denied": True, "effects": False})


if __name__ == "__main__":
    main()
