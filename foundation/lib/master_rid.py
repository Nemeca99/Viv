"""Hierarchical RID — per-subsystem master S_n (0-1) and system Master S_n."""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS
from lib.dormancy_config import load_threshold
from lib.piston_engine import PISTON_STATE_PATH
from lib.rid_triad import (
    THERMAL_ABORT_C,
    THERMAL_IDEAL_C,
    SensorPair,
    TriadSample,
    read_sensors,
)

MASTER_RID_PATH = AUTO_ARTIFACTS / "master_rid.json"
PISTON_STATE_MAX_AGE_S = 300.0
TELEMETRY_CLOCK_SKEW_S = 5.0


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    if math.isnan(x) or math.isinf(x):
        return lo
    return max(lo, min(hi, x))


def sn_from_channels(rsr: float, ltp: float, rle: float) -> float:
    """RID composite — all channels normalized 0-1."""
    r = _clamp(rsr)
    l = _clamp(ltp)
    e = _clamp(rle)
    return _clamp((r * l * e) ** (1.0 / 3.0))


def _geom_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    prod = 1.0
    for v in values:
        prod *= max(v, 1e-6)
    return prod ** (1.0 / len(values))


@dataclass
class SubsystemRid:
    """One plant / control domain — channels and master S_n in [0, 1]."""

    name: str
    rsr: float
    ltp: float
    rle: float
    s_n: float
    available: bool
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MasterRid:
    """Whole-system RID — geometric aggregate of subsystem master S_n values."""

    timestamp: str
    subsystems: dict[str, SubsystemRid]
    master_rsr: float
    master_ltp: float
    master_rle: float
    master_s_n: float
    status: str
    n_subsystems: int

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["subsystems"] = {k: v.to_dict() if isinstance(v, SubsystemRid) else v for k, v in self.subsystems.items()}
        return d


def _thermal_headroom(temp_c: float) -> float:
    span = max(THERMAL_ABORT_C - THERMAL_IDEAL_C, 1.0)
    return _clamp(1.0 - (temp_c - THERMAL_IDEAL_C) / span)


def piston_state_is_fresh(age_s: float) -> bool:
    """Accept only recent telemetry; future timestamps beyond skew fail closed."""
    return (
        math.isfinite(age_s)
        and -TELEMETRY_CLOCK_SKEW_S <= age_s <= PISTON_STATE_MAX_AGE_S
    )


def _iso_age_s(value: Any, *, now_s: float) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return now_s - parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def subsystem_cpu_automaton(sample: TriadSample) -> SubsystemRid:
    rsr = _clamp(sample.runtime_rsr)
    ltp = _clamp(sample.runtime_ltp)
    rle = _clamp(sample.runtime_rle)
    return SubsystemRid(
        name="cpu_automaton",
        rsr=rsr,
        ltp=ltp,
        rle=rle,
        s_n=sn_from_channels(rsr, ltp, rle),
        available=True,
        source="rid_triad.runtime_channels",
    )


def subsystem_piston() -> SubsystemRid:
    if not PISTON_STATE_PATH.is_file():
        return SubsystemRid("piston", 0, 0, 0, 0, False, "missing piston_state.json")
    try:
        st = json.loads(PISTON_STATE_PATH.read_text(encoding="utf-8"))
        modified_age_s = time.time() - PISTON_STATE_PATH.stat().st_mtime
    except (json.JSONDecodeError, OSError):
        return SubsystemRid("piston", 0, 0, 0, 0, False, "read_error")
    timestamp_age_s = _iso_age_s(st.get("timestamp"), now_s=time.time())
    if (
        not piston_state_is_fresh(modified_age_s)
        or timestamp_age_s is None
        or not piston_state_is_fresh(timestamp_age_s)
    ):
        stamp = "invalid" if timestamp_age_s is None else f"{timestamp_age_s:.1f}"
        return SubsystemRid(
            "piston",
            0,
            0,
            0,
            0,
            False,
            f"stale:mtime_age_s={modified_age_s:.1f}:timestamp_age_s={stamp}",
        )
    cores = st.get("cores") or []
    if not cores:
        pkg = float(st.get("package_s_n") or 0)
        return SubsystemRid("piston", pkg, pkg, pkg, pkg, pkg > 0, "package_only")
    rs = [_clamp(float(c.get("rsr", 0))) for c in cores]
    ls = [_clamp(float(c.get("ltp", 0))) for c in cores]
    es = [_clamp(float(c.get("rle", 0))) for c in cores]
    sns = [_clamp(float(c.get("s_n", 0))) for c in cores]
    rsr, ltp, rle = _geom_mean(rs), _geom_mean(ls), _geom_mean(es)
    sn = _geom_mean(sns)
    return SubsystemRid(
        name="piston",
        rsr=round(rsr, 4),
        ltp=round(ltp, 4),
        rle=round(rle, 4),
        s_n=round(sn, 4),
        available=True,
        source=str(PISTON_STATE_PATH),
    )


def subsystem_gpu() -> SubsystemRid:
    try:
        from lib.gpu_plant import GPU_TEMP_MAX, read_gpu

        g = read_gpu(0)
    except Exception as exc:
        return SubsystemRid("gpu", 0, 0, 0, 0, False, f"unavailable:{exc}")
    span = max(GPU_TEMP_MAX - THERMAL_IDEAL_C, 1.0)
    rsr = _clamp(1.0 - g.util_pct / 100.0)
    ltp = _clamp(1.0 - (g.temp_c - THERMAL_IDEAL_C) / span)
    total = max(g.mem_total_mib, 1)
    rle = _clamp(g.mem_free_mib / total)
    return SubsystemRid(
        name="gpu",
        rsr=round(rsr, 4),
        ltp=round(ltp, 4),
        rle=round(rle, 4),
        s_n=sn_from_channels(rsr, ltp, rle),
        available=True,
        source="nvml",
    )


def subsystem_coolant_loop() -> SubsystemRid:
    sens = read_sensors(SensorPair.CPU_COOLANT)
    if sens.a_c <= 0 or sens.b_c <= 0:
        return SubsystemRid("coolant_loop", 0, 0, 0, 0, False, "no_corsair_temps")
    h_a = _thermal_headroom(sens.a_c)
    h_b = _thermal_headroom(sens.b_c)
    ltp = (h_a + h_b) / 2.0
    gap = abs(sens.a_c - sens.b_c)
    rle = _clamp(1.0 - gap / 30.0)
    rsr = _clamp(1.0 - sens.cpu_load_pct / 100.0)
    return SubsystemRid(
        name="coolant_loop",
        rsr=round(rsr, 4),
        ltp=round(ltp, 4),
        rle=round(rle, 4),
        s_n=sn_from_channels(rsr, ltp, rle),
        available=True,
        source="cpu_package_c+coolant_c",
    )


def compute_master_rid(sample: TriadSample) -> MasterRid:
    """Aggregate all available subsystem master S_n into system Master S_n."""
    subs = {
        "cpu_automaton": subsystem_cpu_automaton(sample),
        "piston": subsystem_piston(),
        "gpu": subsystem_gpu(),
        "coolant_loop": subsystem_coolant_loop(),
    }
    avail = [s for s in subs.values() if s.available]
    if not avail:
        return MasterRid(
            timestamp=datetime.now(timezone.utc).isoformat(),
            subsystems=subs,
            master_rsr=0.0,
            master_ltp=0.0,
            master_rle=0.0,
            master_s_n=0.0,
            status="DORMANT",
            n_subsystems=0,
        )
    master_rsr = _geom_mean([s.rsr for s in avail])
    master_ltp = _geom_mean([s.ltp for s in avail])
    master_rle = _geom_mean([s.rle for s in avail])
    master_s_n = _geom_mean([s.s_n for s in avail])
    status = "ACTIVE" if master_s_n >= load_threshold() else "DORMANT"
    return MasterRid(
        timestamp=datetime.now(timezone.utc).isoformat(),
        subsystems=subs,
        master_rsr=round(master_rsr, 4),
        master_ltp=round(master_ltp, 4),
        master_rle=round(master_rle, 4),
        master_s_n=round(master_s_n, 4),
        status=status,
        n_subsystems=len(avail),
    )


def publish_master_rid(master: MasterRid, *, patch_supervisor: bool = True) -> Path:
    MASTER_RID_PATH.parent.mkdir(parents=True, exist_ok=True)
    MASTER_RID_PATH.write_text(json.dumps(master.to_dict(), indent=2), encoding="utf-8")
    if patch_supervisor:
        _patch_supervisor_master(master)
    return MASTER_RID_PATH


def _patch_supervisor_master(master: MasterRid) -> None:
    """Promote hierarchical Master S_n into automation supervisor state."""
    from lib.piston_engine import SUPERVISOR_PATH

    if not SUPERVISOR_PATH.is_file():
        return
    try:
        sup = json.loads(SUPERVISOR_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    payload = {
        "master_s_n": master.master_s_n,
        "master_rsr": master.master_rsr,
        "master_ltp": master.master_ltp,
        "master_rle": master.master_rle,
        "status": master.status,
        "n_subsystems": master.n_subsystems,
        "timestamp": master.timestamp,
        "subsystems": {
            k: {"s_n": v.s_n, "rsr": v.rsr, "ltp": v.ltp, "rle": v.rle, "available": v.available}
            for k, v in master.subsystems.items()
        },
    }
    sup["master_rid"] = payload
    rid = sup.get("system_rid")
    if isinstance(rid, dict):
        rid["master_s_n"] = master.master_s_n
        rid["s_n"] = master.master_s_n
    SUPERVISOR_PATH.write_text(json.dumps(sup, indent=2), encoding="utf-8")


def load_master_rid() -> MasterRid | None:
    if not MASTER_RID_PATH.is_file():
        return None
    try:
        data = json.loads(MASTER_RID_PATH.read_text(encoding="utf-8"))
        subs = {
            k: SubsystemRid(**v) if isinstance(v, dict) else v
            for k, v in (data.get("subsystems") or {}).items()
        }
        return MasterRid(
            timestamp=data["timestamp"],
            subsystems=subs,
            master_rsr=float(data["master_rsr"]),
            master_ltp=float(data["master_ltp"]),
            master_rle=float(data["master_rle"]),
            master_s_n=float(data["master_s_n"]),
            status=data["status"],
            n_subsystems=int(data.get("n_subsystems", len(subs))),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
