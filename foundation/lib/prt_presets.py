"""PRT train presets: quick (day) vs deep (night)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.paths import ARTIFACTS

PRESETS_PATH = ARTIFACTS / "models" / "prt_presets.json"

_FALLBACK = {
    "quick": {
        "observe_cycles": 4,
        "speak_cycles": 2,
        "settle_s": 3.0,
        "steps": 40,
        "lr": 1e-4,
    },
    "deep": {
        "observe_cycles": 20,
        "speak_cycles": 10,
        "settle_s": 4.0,
        "steps": 400,
        "lr": 5e-5,
        "max_rounds": 8,
        "max_hours": 8.0,
        "cooldown_s": 600,
    },
}


def load_presets() -> dict[str, Any]:
    if PRESETS_PATH.is_file():
        try:
            data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return dict(_FALLBACK)


def get_preset(name: str) -> dict[str, Any]:
    key = (name or "quick").strip().lower()
    presets = load_presets()
    if key not in presets:
        raise KeyError(f"unknown preset {name!r}; have {sorted(presets)}")
    return dict(presets[key])
