"""Deterministic CPU status lines — no LLM required."""
from __future__ import annotations

from lib.master_rid import MasterRid, compute_master_rid, publish_master_rid
from lib.rid_telemetry import DORMANCY_THRESHOLD, RidSample


def _channels(sample: RidSample) -> tuple[float, float, float]:
    """Runtime RID channels (0-1) for cpu_automaton subsystem display."""
    return (
        float(sample.runtime_rsr),
        float(sample.runtime_ltp),
        float(sample.runtime_rle),
    )


def format_pulse_line(sample: RidSample, master: MasterRid | None = None) -> str:
    cpu_load = float(getattr(sample, "cpu_load_pct", getattr(sample, "cpu_load", 0)))
    if master is not None:
        parts = " ".join(
            f"{k[:3]}={v.s_n:.3f}"
            for k, v in master.subsystems.items()
            if v.available
        )
        return (
            f"[VIV] Master_S_n={master.master_s_n:.4f} ({master.status}) | "
            f"RSR={master.master_rsr:.4f} LTP={master.master_ltp:.4f} RLE={master.master_rle:.4f} | "
            f"[{parts}] | CPU={cpu_load:.1f}% RAM={sample.ram_pct:.1f}%"
        )
    rsr, ltp, rle = _channels(sample)
    return (
        f"[VIV] {sample.status} | S_n={sample.s_n:.4f} | "
        f"RSR={rsr:.4f} LTP={ltp:.4f} RLE={rle:.4f} | "
        f"CPU={cpu_load:.1f}% RAM={sample.ram_pct:.1f}%"
    )


def format_pulse_message(sample: RidSample, master: MasterRid | None = None) -> str:
    if master is not None:
        if master.master_s_n < DORMANCY_THRESHOLD:
            return (
                f"DORMANT: Master S_n {master.master_s_n:.4f} below {DORMANCY_THRESHOLD:.2f} "
                f"({master.n_subsystems} subsystems)."
            )
        return (
            f"ACTIVE: Master S_n {master.master_s_n:.4f} from {master.n_subsystems} subsystems. "
            f"Channels RSR={master.master_rsr:.4f}, LTP={master.master_ltp:.4f}, "
            f"RLE={master.master_rle:.4f}."
        )
    rsr, ltp, rle = _channels(sample)
    if sample.s_n < DORMANCY_THRESHOLD:
        return (
            f"DORMANT: S_n {sample.s_n:.4f} is below {DORMANCY_THRESHOLD:.2f}. "
            "Privileged actions and speech are blocked until stability returns."
        )
    return (
        f"ACTIVE: S_n {sample.s_n:.4f} within safe bounds. "
        f"Channels RSR={rsr:.4f}, LTP={ltp:.4f}, RLE={rle:.4f}."
    )


def pulse_payload(sample: RidSample, master: MasterRid | None = None) -> dict:
    if master is None:
        master = compute_master_rid(sample)
        publish_master_rid(master)
    dormant = master.master_s_n < DORMANCY_THRESHOLD
    cpu_load = float(getattr(sample, "cpu_load_pct", getattr(sample, "cpu_load", 0)))
    cpu_temp = float(
        getattr(sample, "a_c", getattr(sample, "cpu_temp", (sample.a_c + sample.b_c) / 2.0))
    )
    rsr, ltp, rle = master.master_rsr, master.master_ltp, master.master_rle
    return {
        "timestamp": sample.timestamp,
        "s_n": master.master_s_n,
        "master_s_n": master.master_s_n,
        "rsr": rsr,
        "ltp": ltp,
        "rle": rle,
        "master_rid": master.to_dict(),
        "subsystems": {k: v.to_dict() for k, v in master.subsystems.items()},
        "runtime_rsr": master.master_rsr,
        "runtime_ltp": master.master_ltp,
        "runtime_rle": master.master_rle,
        "cpu_automaton_s_n": sample.s_n,
        "sensor_rsr": sample.rsr,
        "sensor_ltp": sample.ltp,
        "sensor_rle": sample.rle,
        "status": master.status,
        "dormant": dormant,
        "dormancy_threshold": DORMANCY_THRESHOLD,
        "cpu_load": cpu_load,
        "ram_pct": sample.ram_pct,
        "cpu_temp": cpu_temp,
        "line": format_pulse_line(sample, master),
        "message": format_pulse_message(sample, master),
        "voice_required": False,
    }
