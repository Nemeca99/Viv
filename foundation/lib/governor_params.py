"""Runtime governor parameters — loaded from disk, env, or defaults."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS

PISTON_ARTIFACTS = AUTO_ARTIFACTS / "piston"
PARAMS_PATH = PISTON_ARTIFACTS / "governor_params.json"
PARAMS_BACKUP_PATH = PISTON_ARTIFACTS / "governor_params.backup.json"
HISTORY_PATH = PISTON_ARTIFACTS / "governor_history.jsonl"
TUNE_LOG_PATH = PISTON_ARTIFACTS / "governor_tune_log.jsonl"

# Safe bounds — self-tune never escapes these (fail-closed envelope).
BOUNDS = {
    "t_max_c": (60.0, 90.0),
    "max_delta_c": (2.0, 12.0),
    "swap_s_n": (0.35, 0.65),
    "budget_ema": (0.15, 0.85),
    "budget_floor": (0.0, 0.1),
}


@dataclass
class GovernorParams:
    t_max_c: float = 72.0
    max_delta_c: float = 5.0
    swap_s_n: float = 0.5
    budget_ema: float = 0.4
    budget_floor: float = 0.0
    version: int = 0
    source: str = "default"

    def clamped(self) -> "GovernorParams":
        out = GovernorParams(
            t_max_c=_b("t_max_c", self.t_max_c),
            max_delta_c=_b("max_delta_c", self.max_delta_c),
            swap_s_n=_b("swap_s_n", self.swap_s_n),
            budget_ema=_b("budget_ema", self.budget_ema),
            budget_floor=_b("budget_floor", self.budget_floor),
            version=self.version,
            source=self.source,
        )
        return out

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _b(key: str, val: float) -> float:
    lo, hi = BOUNDS[key]
    return max(lo, min(hi, float(val)))


def _from_env() -> GovernorParams:
    return GovernorParams(
        t_max_c=float(os.environ.get("VIV_PISTON_T_MAX", "72")),
        max_delta_c=float(os.environ.get("VIV_PISTON_MAX_DELTA", "5")),
        swap_s_n=float(os.environ.get("VIV_PISTON_SWAP_S_N", "0.5")),
        budget_ema=float(os.environ.get("VIV_GOV_EMA", "0.4")),
        budget_floor=float(os.environ.get("VIV_GOV_FLOOR", "0.0")),
        source="env",
    ).clamped()


def load_params() -> GovernorParams:
    """Priority: env overrides > governor_params.json > defaults."""
    base = GovernorParams(source="default")
    if PARAMS_PATH.is_file():
        try:
            raw = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
            base = GovernorParams(
                t_max_c=float(raw.get("t_max_c", base.t_max_c)),
                max_delta_c=float(raw.get("max_delta_c", base.max_delta_c)),
                swap_s_n=float(raw.get("swap_s_n", base.swap_s_n)),
                budget_ema=float(raw.get("budget_ema", base.budget_ema)),
                budget_floor=float(raw.get("budget_floor", base.budget_floor)),
                version=int(raw.get("version", 0)),
                source=str(raw.get("source", "file")),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    env = _from_env()
    if os.environ.get("VIV_PISTON_T_MAX"):
        base.t_max_c = env.t_max_c
    if os.environ.get("VIV_PISTON_MAX_DELTA"):
        base.max_delta_c = env.max_delta_c
    if os.environ.get("VIV_PISTON_SWAP_S_N"):
        base.swap_s_n = env.swap_s_n
    if os.environ.get("VIV_GOV_EMA"):
        base.budget_ema = env.budget_ema
    if os.environ.get("VIV_GOV_FLOOR"):
        base.budget_floor = env.budget_floor
    if any(
        os.environ.get(k)
        for k in (
            "VIV_PISTON_T_MAX",
            "VIV_PISTON_MAX_DELTA",
            "VIV_PISTON_SWAP_S_N",
            "VIV_GOV_EMA",
            "VIV_GOV_FLOOR",
        )
    ):
        base.source = "env"
    return base.clamped()


def save_params(params: GovernorParams, *, backup: bool = True) -> Path:
    PISTON_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    params = params.clamped()
    if backup and PARAMS_PATH.is_file():
        PARAMS_BACKUP_PATH.write_text(PARAMS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    payload = params.to_dict()
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    PARAMS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return PARAMS_PATH


def rollback_params() -> tuple[bool, GovernorParams]:
    if not PARAMS_BACKUP_PATH.is_file():
        return False, load_params()
    raw = json.loads(PARAMS_BACKUP_PATH.read_text(encoding="utf-8"))
    prev = GovernorParams(
        t_max_c=float(raw["t_max_c"]),
        max_delta_c=float(raw["max_delta_c"]),
        swap_s_n=float(raw["swap_s_n"]),
        budget_ema=float(raw["budget_ema"]),
        budget_floor=float(raw.get("budget_floor", 0.0)),
        version=int(raw.get("version", 0)),
        source="rollback",
    ).clamped()
    save_params(prev, backup=False)
    return True, prev


def append_history(record: dict[str, Any]) -> None:
    PISTON_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")


def append_tune_log(record: dict[str, Any]) -> None:
    PISTON_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with TUNE_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")
