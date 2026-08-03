#!/usr/bin/env python3
"""Enriched electrical sample capture for session-held-out info-gain eval.

Each JSONL row retains rails P/V, derived I, S_electrical, Master S_n,
provenance, missing flags, sensor age, cadence, and workload label.
I_GPU remains stamped derived (not independent).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from lib.hwinfo_telemetry import I_GPU_ORIGIN_OHM, read_electrical
from lib.master_rid import compute_master_rid, load_master_rid
from lib.rid_electrical import triad_availability
from lib.rid_triad import TriadSample, TriadSession


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _live_master(triad: TriadSample | None = None) -> tuple[Any, str]:
    """Compute Master from live TriadSample without publishing (no Master disk write).

    Requires TriadSample (runtime channels), not raw SensorReading.
    """
    try:
        sample = triad if triad is not None else TriadSession().sample()
        return compute_master_rid(sample), "compute_master_rid_live_no_publish"
    except Exception:  # noqa: BLE001
        return load_master_rid(), "load_master_rid_disk_fallback"


def collect_sample(
    *,
    session_id: str,
    workload: str,
    phase: str,
    sample_i: int,
    cadence_s: float,
    t0_mono: float,
    triad: TriadSample | None = None,
) -> dict[str, Any]:
    """One enriched plant sample. Never invents meters."""
    t_collect0 = time.perf_counter()
    hw = read_electrical()
    master, master_source = _live_master(triad)

    w_cpu = hw.get("w_cpu")
    w_gpu = hw.get("w_gpu")
    w_gpu_source = (hw.get("sources") or {}).get("w_gpu")
    # Prefer NVML for live GPU watts when available
    try:
        from lib.gpu_plant import read_gpu

        w_gpu = float(read_gpu(0).power_w)
        w_gpu_source = "lib.gpu_plant.read_gpu.power_w"
    except Exception:  # noqa: BLE001
        pass

    v_cpu = hw.get("v_cpu")
    v_gpu = hw.get("v_gpu")
    i_cpu = hw.get("i_cpu")
    i_gpu = hw.get("i_gpu")
    origins = dict(hw.get("origins") or {})
    independent = dict(hw.get("independent_axes") or {})
    rails = hw.get("i_gpu_rails") or {}

    triad = triad_availability(
        w_cpu=w_cpu,
        w_gpu=w_gpu,
        v_cpu=v_cpu,
        v_gpu=v_gpu,
        i_cpu=i_cpu,
        i_gpu=i_gpu,
    )

    coolant_c = None
    cpu_package_c = None
    try:
        from lib.corsair_telemetry import read_latest

        row = read_latest()
        coolant_c = row.get("coolant_c")
        cpu_package_c = row.get("cpu_c") or row.get("cpu_package_c")
    except Exception:  # noqa: BLE001
        coolant_c = None

    gpu_temp_c = None
    gpu_util_pct = None
    try:
        from lib.gpu_plant import read_gpu

        g = read_gpu(0)
        gpu_temp_c = float(g.temp_c)
        gpu_util_pct = float(g.util_pct)
    except Exception:  # noqa: BLE001
        pass

    missing = [
        k
        for k, v in (
            ("w_cpu", w_cpu),
            ("w_gpu", w_gpu),
            ("v_cpu", v_cpu),
            ("v_gpu", v_gpu),
            ("i_cpu", i_cpu),
            ("i_gpu", i_gpu),
        )
        if v is None
    ]

    csv_mtime = None
    if hw.get("path"):
        try:
            csv_mtime = Path(str(hw["path"]).replace("/", "\\")).stat().st_mtime
        except OSError:
            try:
                csv_mtime = Path(hw["path"]).stat().st_mtime
            except OSError:
                csv_mtime = None
    sensor_age_s = None
    if csv_mtime is not None:
        sensor_age_s = max(0.0, time.time() - float(csv_mtime))

    collect_ms = (time.perf_counter() - t_collect0) * 1000.0
    sample = {
        "at": _utc(),
        "mono_s": round(time.perf_counter() - t0_mono, 3),
        "session_id": session_id,
        "workload": workload,
        "phase": phase,
        "sample_i": int(sample_i),
        "cadence_s": float(cadence_s),
        "sensor_age_s": sensor_age_s,
        "collect_overhead_ms": round(collect_ms, 3),
        "P_rails": {
            "w_cpu": w_cpu,
            "w_gpu": w_gpu,
            "pcie_w": None,
            "pin8_w": None,
        },
        "V_rails": {
            "v_cpu": v_cpu,
            "v_gpu": v_gpu,
            "pcie_v": None,
            "pin8_v": None,
        },
        "I_derived": {
            "i_cpu": i_cpu,
            "i_gpu": i_gpu,
            "i_gpu_origin": origins.get("i_gpu"),
            "i_gpu_independent": bool(independent.get("i_gpu"))
            if independent.get("i_gpu") is not None
            else False,
        },
        "S_electrical": triad.get("s_electrical"),
        "electrical_available": triad.get("available"),
        "r_w": triad.get("r_w"),
        "r_v": triad.get("r_v"),
        "r_i": triad.get("r_i"),
        "master_s_n": None if master is None else float(master.master_s_n),
        "master_status": None if master is None else master.status,
        "master_subsystems": (
            [] if master is None else sorted(master.subsystems.keys())
        ),
        "coolant_c": coolant_c,
        "cpu_package_c": cpu_package_c,
        "gpu_temp_c": gpu_temp_c,
        "gpu_util_pct": gpu_util_pct,
        "missing_channels": missing,
        "provenance": {
            "hwinfo_path": hw.get("path"),
            "hwinfo_ok": bool(hw.get("ok")),
            "hwinfo_error": hw.get("error"),
            "sources": hw.get("sources") or {},
            "origins": origins,
            "w_gpu_source": w_gpu_source,
            "master_source": master_source,
            "i_gpu_stamp_expected": I_GPU_ORIGIN_OHM,
            "master_disk_published": False,
        },
        "i_gpu_rails": rails.get("rails") if isinstance(rails, dict) else None,
    }

    # Fill rail P/V from reconstruction rails when present
    if isinstance(rails, dict):
        for r in rails.get("rails") or []:
            name = str(r.get("power_col") or "")
            if "PCIe" in name:
                sample["P_rails"]["pcie_w"] = r.get("power_w")
                sample["V_rails"]["pcie_v"] = r.get("volt_v")
            elif "8-pin" in name:
                sample["P_rails"]["pin8_w"] = r.get("power_w")
                sample["V_rails"]["pin8_v"] = r.get("volt_v")

    return sample


class SessionCapture:
    """Append-only JSONL capture for one workload session."""

    def __init__(self, session_dir: Path, meta: dict[str, Any]):
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = session_dir / "samples.jsonl"
        self.meta_path = session_dir / "session_meta.json"
        self.meta = dict(meta)
        self._fh: TextIO | None = None
        self.n_samples = 0
        self.t0_mono = time.perf_counter()
        # Persistent triad session so runtime_rsr/load_hist evolve within the capture.
        self._triad_session = TriadSession()
        self.meta_path.write_text(json.dumps(self.meta, indent=2), encoding="utf-8")

    def open(self) -> None:
        self._fh = self.jsonl_path.open("a", encoding="utf-8")

    def close(self, **end_fields: Any) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        self.meta.update(end_fields)
        self.meta["n_samples"] = self.n_samples
        self.meta["ended_at"] = _utc()
        self.meta_path.write_text(json.dumps(self.meta, indent=2), encoding="utf-8")

    def record(
        self,
        *,
        workload: str,
        phase: str,
        cadence_s: float,
        session_id: str,
    ) -> dict[str, Any]:
        triad = self._triad_session.sample()
        sample = collect_sample(
            session_id=session_id,
            workload=workload,
            phase=phase,
            sample_i=self.n_samples,
            cadence_s=cadence_s,
            t0_mono=self.t0_mono,
            triad=triad,
        )
        if self._fh is None:
            self.open()
        assert self._fh is not None
        self._fh.write(json.dumps(sample, ensure_ascii=True) + "\n")
        self._fh.flush()
        self.n_samples += 1
        return sample


def load_session_samples(session_dir: Path) -> list[dict[str, Any]]:
    path = session_dir / "samples.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def load_session_meta(session_dir: Path) -> dict[str, Any]:
    path = session_dir / "session_meta.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
