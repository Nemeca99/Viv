#!/usr/bin/env python3
"""Viv supercooling growth CLI — PC Master RID strain + dynamic LoRA widen."""
from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.growth_gate import check_growth  # noqa: E402
from lib.growth_lora_widen import apply_pending_widen, widen_lora  # noqa: E402
from lib.growth_plant_pressure import PlantPressure, seek_strain_band  # noqa: E402
from lib.growth_chamber_ledger import load_chambers  # noqa: E402
from lib.growth_strain import (  # noqa: E402
    calibrate,
    load_growth_config,
    run_strain_loop,
    status_snapshot,
    strain_tick,
)


def cmd_status(_: argparse.Namespace) -> int:
    snap = status_snapshot()
    snap["chambers"] = load_chambers()
    print(json.dumps(snap, indent=2, default=str))
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    report = calibrate(seconds=args.seconds, interval=args.interval)
    print(json.dumps(report, indent=2))
    return 0


def cmd_breathe(args: argparse.Namespace) -> int:
    """One breath: crystallize (PRT observe) → strain ticks → optional apply pending."""
    out: dict = {"ok": True, "phases": []}
    if args.observe > 0:
        from lib.prt_cycle import collect

        xtal = collect(
            cycles=int(args.observe),
            act="observe",
            settle_s=float(args.settle),
            skip_model_predict=False,
        )
        out["phases"].append({"crystallize": xtal})

    gcfg = load_growth_config()
    ticks = int(args.ticks if args.ticks is not None else gcfg.get("overnight_strain_ticks") or 5)
    last: dict = {}
    for _ in range(max(0, ticks)):
        last = strain_tick(apply_growth=False)
        if last.get("near_dead") or last.get("fired"):
            break
    out["phases"].append({"strain": last})

    if args.apply_pending and last.get("pending_growth"):
        applied = apply_pending_widen()
        out["phases"].append({"grow": applied})
        out["ok"] = bool(applied.get("ok"))

    out["chambers"] = load_chambers()
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


def cmd_chambers(_: argparse.Namespace) -> int:
    print(json.dumps(load_chambers(), indent=2, default=str))
    return 0

def cmd_run(args: argparse.Namespace) -> int:
    report = run_strain_loop(seconds=args.seconds, apply_growth=bool(args.apply))
    print(json.dumps(report, indent=2, default=str))
    return 0


def cmd_run_pressured(args: argparse.Namespace) -> int:
    """Seek strain band with GovernedFleet duty, then run strain loop."""
    pressure = PlantPressure(cores=args.cores, duty=args.duty)
    started = pressure.start()
    print(json.dumps({"pressure_start": started}, indent=2), flush=True)
    try:
        seek = seek_strain_band(
            pressure,
            warm_s=args.warm,
            duty_lo=args.duty_lo,
            duty_hi=args.duty_hi,
        )
        print(json.dumps({"seek": {k: v for k, v in seek.items() if k != "history"}}, indent=2), flush=True)
        if not seek.get("ok") and not args.force_run:
            print("strain band not reached — abort (pass --force-run to strain anyway)", flush=True)
            return 2
        report = run_strain_loop(seconds=args.seconds, apply_growth=bool(args.apply))
        out = {"ok": True, "seek_ok": seek.get("ok"), "seek": seek, "strain": report}
        print(json.dumps({k: v for k, v in out.items() if k != "seek"}, indent=2, default=str), flush=True)
        path = _ROOT / "artifacts" / "audit" / "growth_strain_moderate_pressure.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print("wrote", path, flush=True)
        return 0 if report.get("ok") else 1
    finally:
        print("stopping pressure…", flush=True)
        pressure.stop()
        time.sleep(1.0)
        print(json.dumps({"post": status_snapshot().get("plant")}, indent=2, default=str), flush=True)


def cmd_widen(args: argparse.Namespace) -> int:
    if args.pending:
        result = apply_pending_widen()
    else:
        result = widen_lora(delta_r=args.delta_r, force=bool(args.force))
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


def cmd_check(args: argparse.Namespace) -> int:
    gate = check_growth(args.actuator, delta_r=args.delta_r)
    print(json.dumps(gate, indent=2, default=str))
    return 0 if gate.get("allowed") else 2


def main() -> int:
    p = argparse.ArgumentParser(description="Viv supercooling growth (PC AIOS plant)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="Config + baseline + plant + pending")
    s.set_defaults(func=cmd_status)

    b = sub.add_parser("breathe", help="Crystallize observe → strain ticks → optional pending grow")
    b.add_argument("--observe", type=int, default=1, help="PRT observe cycles (0=skip)")
    b.add_argument("--settle", type=float, default=3.0)
    b.add_argument("--ticks", type=int, default=None, help="Strain ticks after crystallize")
    b.add_argument(
        "--apply-pending",
        action="store_true",
        help="If strain left pending_growth, apply LoRA widen",
    )
    b.set_defaults(func=cmd_breathe)

    ch = sub.add_parser("chambers", help="Cascade chamber ledger (not real MoE yet)")
    ch.set_defaults(func=cmd_chambers)

    c = sub.add_parser("calibrate", help="Idle Master S_n baseline (PC plant)")
    c.add_argument("--seconds", type=int, default=30)
    c.add_argument("--interval", type=float, default=1.0)
    c.set_defaults(func=cmd_calibrate)

    r = sub.add_parser("run", help="Strain loop on Master RID")
    r.add_argument("--seconds", type=float, default=120.0)
    r.add_argument("--apply", action="store_true", help="Apply pending widen when strain fires")
    r.set_defaults(func=cmd_run)

    rp = sub.add_parser(
        "run-pressured",
        help="Moderate GovernedFleet duty → seek strain band → run (not full blast)",
    )
    rp.add_argument("--seconds", type=float, default=90.0)
    rp.add_argument("--warm", type=float, default=25.0, help="Seconds to seek band")
    rp.add_argument("--duty", type=float, default=0.30, help="Initial duty fraction")
    rp.add_argument("--duty-lo", type=float, default=0.12)
    rp.add_argument("--duty-hi", type=float, default=0.55)
    rp.add_argument("--cores", type=int, default=None, help="Worker count (default half cores)")
    rp.add_argument("--apply", action="store_true")
    rp.add_argument(
        "--force-run",
        action="store_true",
        help="Run strain even if seek missed the band",
    )
    rp.set_defaults(func=cmd_run_pressured)

    w = sub.add_parser("widen", help="Function-preserving LoRA rank widen")
    w.add_argument("--delta-r", type=int, default=4)
    w.add_argument("--pending", action="store_true", help="Apply pending strain event")
    w.add_argument("--force", action="store_true", help="Bypass cooldown (not ceilings)")
    w.set_defaults(func=cmd_widen)

    k = sub.add_parser("check", help="Ask growth gate without mutating")
    k.add_argument("--actuator", default="lora_widen")
    k.add_argument("--delta-r", type=int, default=4)
    k.set_defaults(func=cmd_check)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
