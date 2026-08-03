#!/usr/bin/env python3
"""Labeled dynamic workload profiles for electrical info-gain sessions.

Profiles produce real plant dynamics (CPU burn, Ollama GPU inference, mixed,
switch, coolant equilibrium). Each profile is a whole evaluation session.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

from lib.rid_stressor import start_stressor, stop_stressor


@dataclass(frozen=True)
class Phase:
    name: str
    seconds: float
    cpu: bool = False
    gpu_infer: bool = False
    cpu_cores: int | None = None


# Full (default) and smoke durations
_FULL: dict[str, list[Phase]] = {
    "cpu_ramp": [
        Phase("idle", 15.0),
        Phase("ramp", 30.0, cpu=True, cpu_cores=4),
        Phase("sustained", 60.0, cpu=True, cpu_cores=None),
        Phase("cooldown", 30.0),
    ],
    "gpu_infer": [
        Phase("idle", 15.0),
        Phase("ramp", 30.0, gpu_infer=True),
        Phase("sustained", 60.0, gpu_infer=True),
        Phase("cooldown", 30.0),
    ],
    "mixed": [
        Phase("idle", 10.0),
        Phase("ramp", 20.0, cpu=True, gpu_infer=True, cpu_cores=4),
        Phase("sustained", 60.0, cpu=True, gpu_infer=True),
        Phase("cooldown", 30.0),
    ],
    "cpu_gpu_switch": [
        Phase("idle", 10.0),
        Phase("cpu_a", 20.0, cpu=True, cpu_cores=None),
        Phase("gpu_a", 20.0, gpu_infer=True),
        Phase("cpu_b", 20.0, cpu=True, cpu_cores=None),
        Phase("gpu_b", 20.0, gpu_infer=True),
        Phase("cooldown", 20.0),
    ],
    "coolant_eq": [
        Phase("idle", 20.0),
        Phase("load", 90.0, cpu=True, cpu_cores=None),
        Phase("equilibrate", 60.0, cpu=True, cpu_cores=4),
        Phase("cooldown", 40.0),
    ],
}

_SMOKE: dict[str, list[Phase]] = {
    "cpu_ramp": [
        Phase("idle", 2.0),
        Phase("ramp", 3.0, cpu=True, cpu_cores=2),
        Phase("sustained", 4.0, cpu=True, cpu_cores=2),
        Phase("cooldown", 2.0),
    ],
    "gpu_infer": [
        Phase("idle", 2.0),
        Phase("ramp", 3.0, gpu_infer=True),
        Phase("sustained", 4.0, gpu_infer=True),
        Phase("cooldown", 2.0),
    ],
    "mixed": [
        Phase("idle", 2.0),
        Phase("ramp", 3.0, cpu=True, gpu_infer=True, cpu_cores=2),
        Phase("sustained", 4.0, cpu=True, gpu_infer=True, cpu_cores=2),
        Phase("cooldown", 2.0),
    ],
    "cpu_gpu_switch": [
        Phase("idle", 1.0),
        Phase("cpu_a", 3.0, cpu=True, cpu_cores=2),
        Phase("gpu_a", 3.0, gpu_infer=True),
        Phase("cpu_b", 3.0, cpu=True, cpu_cores=2),
        Phase("gpu_b", 3.0, gpu_infer=True),
        Phase("cooldown", 2.0),
    ],
    "coolant_eq": [
        Phase("idle", 2.0),
        Phase("load", 5.0, cpu=True, cpu_cores=2),
        Phase("equilibrate", 4.0, cpu=True, cpu_cores=2),
        Phase("cooldown", 2.0),
    ],
}

PROFILE_NAMES = tuple(_FULL.keys())
OLLAMA_MODEL = os.environ.get("VIV_ELECTRICAL_OLLAMA_MODEL", "viv-voice-qwen")


def phases_for(profile: str, *, smoke: bool = False) -> list[Phase]:
    table = _SMOKE if smoke else _FULL
    if profile not in table:
        raise ValueError(f"unknown_profile:{profile}")
    return list(table[profile])


class WorkloadController:
    """Start/stop CPU burn and GPU inference loaders for profile phases."""

    def __init__(self, *, ollama_model: str = OLLAMA_MODEL):
        self.ollama_model = ollama_model
        self._cpu_procs: list[Any] = []
        self._infer_proc: subprocess.Popen[bytes] | None = None
        self.events: list[dict[str, Any]] = []

    def _log(self, event: str, **kw: Any) -> None:
        self.events.append({"event": event, **kw, "t": time.time()})

    def apply_phase(self, phase: Phase) -> None:
        want_cpu = bool(phase.cpu)
        want_gpu = bool(phase.gpu_infer)
        if want_cpu and not self._cpu_procs:
            cores = phase.cpu_cores
            self._cpu_procs = start_stressor(cores)
            self._log("cpu_start", cores=cores or "all", n=len(self._cpu_procs))
        elif not want_cpu and self._cpu_procs:
            stop_stressor(self._cpu_procs)
            self._log("cpu_stop")
            self._cpu_procs = []
        elif want_cpu and self._cpu_procs and phase.cpu_cores is not None:
            # Restart with different core count on ramp→sustained transitions
            stop_stressor(self._cpu_procs)
            self._cpu_procs = start_stressor(phase.cpu_cores)
            self._log("cpu_restart", cores=phase.cpu_cores)

        if want_gpu and self._infer_proc is None:
            self._infer_proc = self._start_ollama_infer()
            self._log(
                "gpu_infer_start",
                model=self.ollama_model,
                pid=None if self._infer_proc is None else self._infer_proc.pid,
            )
        elif not want_gpu and self._infer_proc is not None:
            self._stop_infer()
            self._log("gpu_infer_stop")

    def stop_all(self) -> None:
        if self._cpu_procs:
            stop_stressor(self._cpu_procs)
            self._cpu_procs = []
        self._stop_infer()

    def _stop_infer(self) -> None:
        p = self._infer_proc
        self._infer_proc = None
        if p is None:
            return
        try:
            p.terminate()
            p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                p.kill()
            except Exception:  # noqa: BLE001
                pass

    def _start_ollama_infer(self) -> subprocess.Popen[bytes] | None:
        """Background loop: ollama generate to create real GPU transformer load."""
        script = (
            "import json,subprocess,sys,time\n"
            f"model={self.ollama_model!r}\n"
            "prompt='Summarize energy-aware routing for a liquid-cooled CPU and air-cooled GPU in two sentences.'\n"
            "while True:\n"
            "  try:\n"
            "    subprocess.run(['ollama','run',model,prompt],check=False,timeout=120,\n"
            "      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
            "  except Exception:\n"
            "    time.sleep(1.0)\n"
            "  time.sleep(0.2)\n"
        )
        try:
            return subprocess.Popen(
                [sys.executable, "-c", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),  # type: ignore[attr-defined]
            )
        except OSError as exc:
            self._log("gpu_infer_failed", error=str(exc))
            return None


def run_profile_phases(
    profile: str,
    *,
    smoke: bool = False,
    cadence_s: float = 1.0,
    on_tick: Callable[[str, Phase], None] | None = None,
    controller: WorkloadController | None = None,
) -> dict[str, Any]:
    """Execute profile phases; call on_tick(phase_name, phase) each sample period."""
    ctrl = controller or WorkloadController()
    owned = controller is None
    phase_list = phases_for(profile, smoke=smoke)
    t0 = time.perf_counter()
    try:
        for phase in phase_list:
            ctrl.apply_phase(phase)
            end = time.perf_counter() + float(phase.seconds)
            while time.perf_counter() < end:
                if on_tick is not None:
                    on_tick(phase.name, phase)
                # sleep remaining of cadence
                time.sleep(max(0.05, float(cadence_s)))
    finally:
        ctrl.stop_all()
        if owned:
            pass
    return {
        "profile": profile,
        "smoke": smoke,
        "duration_s": round(time.perf_counter() - t0, 3),
        "phases": [p.name for p in phase_list],
        "events": ctrl.events,
    }
