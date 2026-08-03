"""RID supervisory layer ON TOP of PID — not a PID replacement.

Contract (binding):
  1. Inner loop always computes a PID duty from SP/PV.
  2. RID observes SP/PV/duty → RSR/LTP/RLE/S_n.
  3. RID may: scale gains, clamp duty by RLE headroom, interlock (cut duty).
  4. RID never invents the tracking law — PID does.

Gain schedule modes:
  boost_when_stable — industrial default: base PID on ramp; boost near SP when S_n high
  multiply_sn       — literal Phone Kp*=S_n (theory A/B; harsh on heat-up)
  off               — safety envelope only (clamp + interlock)
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from lib.pid_controller import PIDController, PIDGains
from lib.rid_heater_channels import heater_rid_channels


@dataclass
class RIDSupervisorConfig:
    """Outer-loop RID envelope parameters."""

    enable_gain_schedule: bool = True
    enable_duty_clamp: bool = True
    enable_interlock: bool = True
    # "boost_when_stable" = industrial default (don't starve heat-up).
    # "multiply_sn" = literal Phone Kp*=S_n (harsh on ramp; use for theory A/B).
    # "off" = safety envelope only.
    gain_schedule_mode: str = "boost_when_stable"
    sn_gain_floor: float = 0.15
    # Only apply S_n gain effects inside this |error| band (°C); outside = base PID.
    gain_error_band_c: float = 15.0
    # When stable (S_n high), allow up to this multiplicative boost on Kp/Ki/Kd.
    sn_boost_max: float = 0.35
    rle_clamp_threshold: float = 0.25
    rle_clamp_max_duty: float = 40.0
    sn_interlock: float = 0.08
    temp_lo: float = 50.0
    temp_hi: float = 600.0
    overtemp_limit: float = 550.0
    capacity_pct: float = 100.0


@dataclass
class RIDOnPIDController:
    """PID inner + RID outer. Use mode='pid' for baseline, mode='rid_pid' for pilot."""

    base_gains: PIDGains = field(default_factory=PIDGains)
    rid: RIDSupervisorConfig = field(default_factory=RIDSupervisorConfig)
    mode: str = "rid_pid"  # "pid" | "rid_pid"
    _pid: PIDController = field(init=False)
    _last_sn: float = 1.0

    def __post_init__(self) -> None:
        self._pid = PIDController(gains=deepcopy(self.base_gains))
        self._last_sn = 1.0

    def reset(self) -> None:
        self._pid = PIDController(gains=deepcopy(self.base_gains))
        self._last_sn = 1.0

    def _scheduled_gains(self, *, setpoint: float, pv: float) -> PIDGains:
        """Apply RID gain policy. PID tracking law unchanged — only gain magnitudes."""
        g = self.base_gains
        mode = str(self.rid.gain_schedule_mode or "boost_when_stable").lower()
        if mode == "off" or not self.rid.enable_gain_schedule:
            return deepcopy(g)

        err = abs(float(setpoint) - float(pv))
        sn = float(self._last_sn)

        if mode == "multiply_sn":
            # Literal Phone formula — valid theory test, harsh on large-error ramps.
            scale = max(self.rid.sn_gain_floor, sn)
            return PIDGains(
                kp=g.kp * scale,
                ki=g.ki * scale,
                kd=g.kd * scale,
                out_min=g.out_min,
                out_max=g.out_max,
                integral_limit=g.integral_limit,
            )

        # boost_when_stable (default): base gains during approach; boost near SP when S_n high.
        if err > self.rid.gain_error_band_c:
            return deepcopy(g)
        boost = max(0.0, (sn - 0.5) * 2.0) * self.rid.sn_boost_max
        scale = 1.0 + boost
        return PIDGains(
            kp=g.kp * scale,
            ki=g.ki * scale,
            kd=g.kd * scale,
            out_min=g.out_min,
            out_max=g.out_max,
            integral_limit=g.integral_limit,
        )

    def step(self, *, setpoint: float, pv: float, dt: float) -> dict[str, Any]:
        mode = str(self.mode).lower().strip()
        if mode not in ("pid", "rid_pid"):
            mode = "rid_pid"

        # --- Always run PID first (inner loop owns tracking) ---
        if mode == "rid_pid":
            self._pid.gains = self._scheduled_gains(setpoint=setpoint, pv=pv)
        else:
            self._pid.gains = deepcopy(self.base_gains)

        pid_out = self._pid.step(setpoint=setpoint, pv=pv, dt=dt)
        duty = float(pid_out["duty_pct"])

        channels = heater_rid_channels(
            setpoint=setpoint,
            pv=pv,
            duty_pct=duty,
            temp_lo=self.rid.temp_lo,
            temp_hi=self.rid.temp_hi,
            overtemp_limit=self.rid.overtemp_limit,
            capacity_pct=self.rid.capacity_pct,
        )
        self._last_sn = float(channels["s_n"])

        actions: list[str] = []
        final_duty = duty
        interlocked = False

        if mode == "rid_pid":
            if self.rid.enable_interlock and channels["s_n"] < self.rid.sn_interlock:
                final_duty = 0.0
                interlocked = True
                actions.append("interlock_cut")
            elif self.rid.enable_duty_clamp and channels["rle"] < self.rid.rle_clamp_threshold:
                # Only clamp when thermally at risk: overshooting SP or near overtemp wall.
                near_wall = float(pv) >= (self.rid.overtemp_limit - 25.0)
                overshooting = float(pv) > float(setpoint) + 2.0
                if (near_wall or overshooting) and final_duty > self.rid.rle_clamp_max_duty:
                    final_duty = self.rid.rle_clamp_max_duty
                    actions.append("rle_duty_clamp")
            if self.rid.enable_gain_schedule and self.rid.gain_schedule_mode != "off":
                actions.append(f"gain:{self.rid.gain_schedule_mode}")

            channels = heater_rid_channels(
                setpoint=setpoint,
                pv=pv,
                duty_pct=final_duty,
                temp_lo=self.rid.temp_lo,
                temp_hi=self.rid.temp_hi,
                overtemp_limit=self.rid.overtemp_limit,
                capacity_pct=self.rid.capacity_pct,
            )
            self._last_sn = float(channels["s_n"])

        return {
            "mode": mode,
            "setpoint": round(float(setpoint), 4),
            "pv": round(float(pv), 4),
            "duty_pct": round(final_duty, 4),
            "pid_duty_pct": round(duty, 4),
            "pid": pid_out,
            "rid": channels,
            "actions": actions,
            "interlocked": interlocked,
        }
