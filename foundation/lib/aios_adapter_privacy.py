"""Read-only CPU adapter for privacy mode and consent policy."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.cpu_privacy_policy import authorize_learning, evaluate
from lib.privacy_core import plan_data_action, plan_mode_change, plan_retention, transparency_report

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


def cpu_plan(
    config: dict[str, Any] | None = None,
    *,
    requested_mode: str | None = None,
    explicit_consent: bool = False,
    records: list[dict[str, Any]] | None = None,
    retention_category: str = "conversations",
    data_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "state": "VERIFIED",
        "retention": plan_retention(config, category=retention_category),
        "transparency": transparency_report(records or []),
        "writes_performed": False,
        "llm_authority": False,
    }
    if requested_mode is not None:
        result["mode_change"] = plan_mode_change(config, requested_mode, explicit_consent=explicit_consent)
    if data_action is not None:
        result["data_action"] = plan_data_action(str(data_action.get("action") or ""), str(data_action.get("target") or ""), confirmation=str(data_action.get("confirmation") or ""))
    return result


def run_smoke() -> dict[str, Any]:
    semi = authorize_learning("behavior")
    explicit = authorize_learning("explicit_user_input")
    return {"ok": semi["allowed"] is False and explicit["allowed"] is True, "evidence": {"adapter": ADAPTER_ID, "semi_behavior_denied": not semi["allowed"], "explicit_input_allowed": explicit["allowed"], "at": _utc()}}
