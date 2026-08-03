"""First-order thermal plant for quartz-heater software validation.

Simulates: duty → heat input → first-order lag + optional disturbance.
Used so the RID-on-PID stack is testable BEFORE hardware arrives.
Hardware plant later implements the same interface: step(duty_pct, dt) → pv.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QuartzHeaterPlant:
    """Lumped first-order heater model (software stand-in for real quartz + TC)."""

    ambient_c: float = 25.0
    # Max steady-state rise above ambient at 100% duty (°C)
    gain_c_per_full_duty: float = 480.0
    # Thermal time constant (s) — quartz filament is fast; process lag slower
    tau_s: float = 18.0
    # Sensor lag (s)
    sensor_tau_s: float = 2.5
    pv: float = 25.0
    _true_temp: float = 25.0
    noise_c: float = 0.15
    _t: float = 0.0
    disturbance_c: float = 0.0  # additive load disturbance

    def reset(self, temp_c: float | None = None) -> None:
        t0 = float(self.ambient_c if temp_c is None else temp_c)
        self.pv = t0
        self._true_temp = t0
        self._t = 0.0
        self.disturbance_c = 0.0

    def set_disturbance(self, delta_c: float) -> None:
        self.disturbance_c = float(delta_c)

    def step(self, duty_pct: float, dt: float) -> dict[str, Any]:
        dt = max(float(dt), 1e-6)
        duty = max(0.0, min(100.0, float(duty_pct))) / 100.0
        target = self.ambient_c + self.gain_c_per_full_duty * duty + self.disturbance_c
        # First-order approach to target
        alpha = 1.0 - math.exp(-dt / max(self.tau_s, 1e-3))
        self._true_temp = self._true_temp + alpha * (target - self._true_temp)
        # Sensor lag
        beta = 1.0 - math.exp(-dt / max(self.sensor_tau_s, 1e-3))
        measured = self.pv + beta * (self._true_temp - self.pv)
        # Tiny deterministic pseudo-noise from time (reproducible)
        self._t += dt
        noise = self.noise_c * math.sin(self._t * 1.7) * 0.5
        self.pv = measured + noise
        return {
            "pv": round(self.pv, 4),
            "true_temp": round(self._true_temp, 4),
            "duty_pct": round(duty * 100.0, 4),
            "t": round(self._t, 4),
        }
