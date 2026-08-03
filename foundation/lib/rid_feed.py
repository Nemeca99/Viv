"""Shared RID live sample — Viv foundation → automation / AIOS heart."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from lib.paths import RID_ARTIFACTS
from lib.rid_telemetry import DORMANCY_THRESHOLD, RidSample, sample_once, write_json_sample

LIVE_SAMPLE_PATH = RID_ARTIFACTS / "live_sample.json"
DEFAULT_MAX_AGE_S = 3.0


@dataclass
class LiveFeedMeta:
    path: Path
    age_s: float
    fresh: bool


def write_live(sample: RidSample, path: Path | None = None) -> Path:
    out = path or LIVE_SAMPLE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json_sample(out, sample)
    return out


def _parse_live(data: dict) -> RidSample:
    """Load TriadSample from JSON; tolerate legacy phone-era field names."""
    if "a_c" in data:
        avg_temp = (float(data["a_c"]) + float(data["b_c"])) / 2.0
        return RidSample(
            timestamp=str(data["timestamp"]),
            t_s=float(data.get("t_s", 0)),
            a_c=float(data["a_c"]),
            b_c=float(data["b_c"]),
            a_label=str(data.get("a_label", "cpu")),
            b_label=str(data.get("b_label", "gpu")),
            ltp=float(data["ltp"]),
            rsr=float(data["rsr"]),
            rle=float(data["rle"]),
            rle_rate=float(data.get("rle_rate", 0)),
            runtime_rsr=float(data.get("runtime_rsr", data.get("rsr", 0))),
            runtime_ltp=float(data.get("runtime_ltp", data.get("ltp", 0))),
            runtime_rle=float(data.get("runtime_rle", data.get("rle", 0))),
            s_n=float(data["s_n"]),
            cpu_load_pct=float(data.get("cpu_load_pct", data.get("cpu_load", 0))),
            ram_pct=float(data["ram_pct"]),
            status=str(data["status"]),
        )
    # legacy
    return RidSample(
        timestamp=str(data["timestamp"]),
        t_s=0.0,
        a_c=float(data.get("cpu_temp", 0)),
        b_c=float(data.get("cpu_temp", 0)),
        a_label="legacy",
        b_label="legacy",
        ltp=float(data.get("ltp", 0)),
        rsr=float(data.get("rsr", 0)),
        rle=float(data.get("rle", 0)),
        rle_rate=0.0,
        runtime_rsr=float(data.get("rsr", 0)),
        runtime_ltp=float(data.get("ltp", 0)),
        runtime_rle=float(data.get("rle", 0)),
        s_n=float(data["s_n"]),
        cpu_load_pct=float(data.get("cpu_load", 0)),
        ram_pct=float(data.get("ram_pct", 0)),
        status=str(data.get("status", "ACTIVE")),
    )


def read_live(path: Path | None = None, *, max_age_s: float = DEFAULT_MAX_AGE_S) -> Optional[RidSample]:
    src = path or LIVE_SAMPLE_PATH
    if not src.is_file():
        return None
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
        age = time.time() - src.stat().st_mtime
        if age > max_age_s:
            return None
        return _parse_live(data)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def feed_meta(path: Path | None = None) -> LiveFeedMeta:
    src = path or LIVE_SAMPLE_PATH
    if not src.is_file():
        return LiveFeedMeta(path=src, age_s=-1.0, fresh=False)
    age = time.time() - src.stat().st_mtime
    return LiveFeedMeta(path=src, age_s=age, fresh=age <= DEFAULT_MAX_AGE_S)


def pulse_once(path: Path | None = None) -> RidSample:
    sample = sample_once()
    write_live(sample, path)
    return sample


def is_dormant(sample: RidSample) -> bool:
    return sample.s_n < DORMANCY_THRESHOLD
