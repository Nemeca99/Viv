"""Load Viv model_config.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parents[1] / "model_config.json"


def load_config(path: Path | None = None) -> dict[str, Any]:
    p = path or CONFIG_PATH
    if not p.is_file():
        raise FileNotFoundError(f"model config missing: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def models_root(cfg: dict[str, Any]) -> Path:
    return Path(cfg.get("models_root", "L:/Continue/models"))
