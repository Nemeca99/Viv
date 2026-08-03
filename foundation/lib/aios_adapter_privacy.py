"""Read-only CPU adapter for privacy mode and consent policy."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.cpu_privacy_policy import authorize_learning, evaluate

ADAPTER_ID = "privacy_core"
REGISTRY_ID = "privacy_core"
F_PRIVACY = Path(r"F:\AIOS_Clean\privacy_core")
D_PRIVACY = Path(r"D:\LocalAi\AIOS_V1\privacy_core")


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def status() -> dict[str, Any]:
    policy = evaluate()
    policy.update({"adapter": ADAPTER_ID, "at": _utc(), "f_source_present": F_PRIVACY.is_dir(), "d_source_present": D_PRIVACY.is_dir(), "source_read_only": True})
    return {"ok": True, "evidence": policy}


def run_smoke() -> dict[str, Any]:
    semi = authorize_learning("behavior")
    explicit = authorize_learning("explicit_user_input")
    return {"ok": semi["allowed"] is False and explicit["allowed"] is True, "evidence": {"adapter": ADAPTER_ID, "semi_behavior_denied": not semi["allowed"], "explicit_input_allowed": explicit["allowed"], "at": _utc()}}
