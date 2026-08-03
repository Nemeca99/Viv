"""CARMA storage paths — all data under foundation/artifacts/carma (Law 7 sandbox)."""
from __future__ import annotations

from pathlib import Path

VIV_ROOT = Path(__file__).resolve().parents[1]
FOUNDATION_ROOT = VIV_ROOT / "foundation"
CARMA_ROOT = FOUNDATION_ROOT / "artifacts" / "carma"

MASTER_TAGS_PATH = CARMA_ROOT / "master_tags.json"
INDEX_PATH = CARMA_ROOT / "index.json"
HEARTBEAT_PATH = CARMA_ROOT / "heartbeat.jsonl"

PROVENANCE_DIRS = {
    "live": CARMA_ROOT / "live",
    "dream": CARMA_ROOT / "dream",
    "simulation": CARMA_ROOT / "simulation",
}

SPLIT_BYTES = 1_048_576  # 1 MB
CURRENT_TXT = PROVENANCE_DIRS["live"] / "current.txt"


def as_gate_path(path: Path) -> str:
    return str(path).replace("\\", "/")
