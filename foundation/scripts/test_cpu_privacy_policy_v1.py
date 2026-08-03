"""Regression for fail-closed CPU privacy and consent policy."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_adapter_privacy import run_smoke, status  # noqa: E402
from lib.cpu_privacy_policy import authorize_learning, evaluate  # noqa: E402


def main() -> int:
    default = evaluate()
    assert default["mode"] == "semi-auto" and default["consent_valid"] is False
    assert authorize_learning("conversation")["allowed"] is True
    assert authorize_learning("behavior")["allowed"] is False
    full = evaluate({"mode": "full-auto", "learning": {"behavior_tracking": True}, "consent": {"full_auto_enabled": True, "user_acknowledged": True}})
    assert full["mode"] == "full-auto" and authorize_learning("behavior", {"mode": "full-auto", "consent": {"full_auto_enabled": True, "user_acknowledged": True}})["allowed"] is True
    assert run_smoke()["ok"] is True and status()["evidence"]["source_read_only"] is True
    print(json.dumps({"ok": True, "default_mode": default["mode"], "behavior_default_denied": True, "explicit_consent_required": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
