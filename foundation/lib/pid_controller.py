"""Classic PID — inner loop only. RID does not live here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PIDGains:
    kp: float = 2.0
    ki: float = 0.15
    kd: float = 0.4
    out_min: float = 0.0
    out_max: float = 100.0
    integral_limit: float = 200.0


@dataclass
class PIDController:
    """Standard positional PID with anti-windup clamp. Output = duty %."""

    gains: PIDGains = field(default_factory=PIDGains)
    _integral: float = 0.0
    _prev_error: float | None = None
    _prev_pv: float | None = None

    def reset(self) -> None:
        self._integral = 0.0
        self._prev_error = None
        self._prev_pv = None

    def step(self, *, setpoint: float, pv: float, dt: float) -> dict[str, Any]:
        dt = max(float(dt), 1e-6)
        err = float(setpoint) - float(pv)
        g = self.gains

        # Proportional
        p = g.kp * err

        # Integral with clamp
        self._integral += err * dt
        if self._integral > g.integral_limit:
            self._integral = g.integral_limit
        elif self._integral < -g.integral_limit:
            self._integral = -g.integral_limit
        i = g.ki * self._integral

        # Derivative on measurement (reduces setpoint kick)
        if self._prev_pv is None:
            d = 0.0
        else:
            d = -g.kd * (float(pv) - self._prev_pv) / dt
        self._prev_pv = float(pv)
        self._prev_error = err

        raw = p + i + d
        duty = max(g.out_min, min(g.out_max, raw))
        # Simple anti-windup: if saturated against error direction, freeze integral a bit
        if duty >= g.out_max and err > 0:
            self._integral -= err * dt * 0.5
        elif duty <= g.out_min and err < 0:
            self._integral -= err * dt * 0.5

        return {
            "duty_pct": round(duty, 4),
            "error": round(err, 4),
            "p": round(p, 4),
            "i": round(i, 4),
            "d": round(d, 4),
            "raw": round(raw, 4),
            "kp": g.kp,
            "ki": g.ki,
            "kd": g.kd,
        }
