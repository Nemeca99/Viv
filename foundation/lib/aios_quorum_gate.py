"""Small deterministic CPU quorum gate for the Alpha automation lane.

The gate reads only the trigger files named by the local JSON policy.  Missing,
stale, malformed, or mismatched providers fail closed.  No model or GPU call
is involved.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QuorumResult:
    allow: bool
    mode: str
    valid_count: int
    required: int
    generated_utc: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load_policy(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    return json.loads(candidate.read_text(encoding="utf-8"))


def _provider_valid(provider: dict[str, Any], now: datetime) -> bool:
    if provider.get("type") != "trigger_file":
        return False
    path = Path(str(provider.get("path") or ""))
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        age = (now - datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)).total_seconds()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    max_age = float(provider.get("max_age_seconds") or 0)
    if max_age <= 0 or age < 0 or age > max_age:
        return False
    expected = provider.get("expected_status")
    if expected is None:
        return True
    return str(payload.get("status") or "") == str(expected)


def evaluate_quorum(action: str, policy: dict[str, Any]) -> QuorumResult:
    del action  # The current Alpha policy is action-independent; remain explicit.
    now = _now()
    providers = [
        provider
        for lane in (policy.get("lanes") or {}).values()
        for provider in (lane.get("providers") or [])
        if isinstance(provider, dict)
    ]
    required = len(providers)
    valid = sum(1 for provider in providers if _provider_valid(provider, now))
    return QuorumResult(
        allow=required > 0 and valid == required,
        mode="all_required",
        valid_count=valid,
        required=required,
        generated_utc=now.isoformat(),
    )
