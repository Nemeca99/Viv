#!/usr/bin/env python3
"""RID-on-PID industrial heater control software — CLI.

PID is the inner loop. RID is the outer envelope. Never the reverse.

Commands:
  ab      — prove/disprove A/B on software plant (PID vs RID+PID)
  run     — single closed-loop run (pid | rid_pid)
  status  — print contract + paths
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.pid_controller import PIDGains  # noqa: E402
from lib.rid_pid_loop import RunProfile, ab_compare, run_closed_loop, write_ab_report  # noqa: E402
from lib.rid_pid_supervisor import RIDSupervisorConfig  # noqa: E402


def cmd_status(_: argparse.Namespace) -> int:
    print(
        json.dumps(
            {
                "ok": True,
                "contract": "RID layers on PID — never replaces PID",
                "software": "WORKING (software plant). Hardware plant IO = next when heater arrives.",
                "modules": [
                    "lib/pid_controller.py",
                    "lib/rid_heater_channels.py",
                    "lib/rid_pid_supervisor.py",
                    "lib/quartz_heater_plant.py",
                    "lib/rid_pid_loop.py",
                ],
                "ab_report": "artifacts/audit/ab_rid_pid_heater_v1.{json,md}",
                "doc": "RID_PID_HEATER_CONTRACT.md",
            },
            indent=2,
        )
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    profile = RunProfile(
        setpoint_c=args.setpoint,
        duration_s=args.seconds,
        dt_s=args.dt,
        disturb_at_s=args.disturb_at,
        disturb_delta_c=args.disturb,
    )
    gains = PIDGains(kp=args.kp, ki=args.ki, kd=args.kd)
    rid = RIDSupervisorConfig(overtemp_limit=args.overtemp)
    result = run_closed_loop(mode=args.mode, profile=profile, gains=gains, rid_cfg=rid)
    # Drop row dump unless --full
    out = {k: v for k, v in result.items() if k != "rows" or args.full}
    if not args.full:
        out["rows_tail"] = result["rows"][-5:]
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_ab(args: argparse.Namespace) -> int:
    profile = RunProfile(
        setpoint_c=args.setpoint,
        duration_s=args.seconds,
        dt_s=args.dt,
        disturb_at_s=args.disturb_at,
        disturb_delta_c=args.disturb,
    )
    gains = PIDGains(kp=args.kp, ki=args.ki, kd=args.kd)
    rid = RIDSupervisorConfig(overtemp_limit=args.overtemp)
    report = ab_compare(profile=profile, gains=gains, rid_cfg=rid)
    jpath, mpath = write_ab_report(report)
    print(
        json.dumps(
            {
                "ok": True,
                "verdict": report["verdict"],
                "reason": report["reason"],
                "deltas": report["deltas_pilot_minus_baseline"],
                "json": str(jpath).replace("\\", "/"),
                "md": str(mpath).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0 if report["verdict"] != "INCONCLUSIVE" else 2


def main() -> int:
    p = argparse.ArgumentParser(description="RID-on-PID heater control software")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="Contract + module paths")
    s.set_defaults(func=cmd_status)

    r = sub.add_parser("run", help="One closed-loop run")
    r.add_argument("--mode", choices=["pid", "rid_pid"], default="rid_pid")
    r.add_argument("--setpoint", type=float, default=350.0)
    r.add_argument("--seconds", type=float, default=120.0)
    r.add_argument("--dt", type=float, default=0.5)
    r.add_argument("--disturb-at", type=float, default=60.0)
    r.add_argument("--disturb", type=float, default=-40.0)
    r.add_argument("--kp", type=float, default=1.8)
    r.add_argument("--ki", type=float, default=0.08)
    r.add_argument("--kd", type=float, default=3.5)
    r.add_argument("--overtemp", type=float, default=480.0)
    r.add_argument("--full", action="store_true")
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("ab", help="Prove/disprove: PID alone vs RID+PID")
    a.add_argument("--setpoint", type=float, default=350.0)
    a.add_argument("--seconds", type=float, default=120.0)
    a.add_argument("--dt", type=float, default=0.5)
    a.add_argument("--disturb-at", type=float, default=60.0)
    a.add_argument("--disturb", type=float, default=-40.0)
    a.add_argument("--kp", type=float, default=1.8)
    a.add_argument("--ki", type=float, default=0.08)
    a.add_argument("--kd", type=float, default=3.5)
    a.add_argument("--overtemp", type=float, default=480.0)
    a.set_defaults(func=cmd_ab)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
