#!/usr/bin/env python3
"""
Black Hole Collapse Simulator (RID-based) — PC port.

Maps mass (RSR/freq coherence), density (LTP/temp), energy (RLE/RAM)
onto live Windows telemetry. Full-core Pi stress + memory apocalypse.
Unlocked PC: all logical cores, Corsair temps, no Android throttling sandbox.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.black_hole_engine import (
    BH_ARTIFACTS,
    DENSITY_CRITICAL,
    ENERGY_CRITICAL,
    MASS_CRITICAL,
    ChannelEngine,
    append_log,
    format_line,
    launch_stressors,
    print_line,
    sample_once,
    stop_stressors,
    write_state,
)

from lib.gpu_black_hole_engine import (
    GPU_BH_ARTIFACTS,
    GpuChannelEngine,
    append_gpu_log,
    print_gpu_line,
    sample_gpu_once,
    write_gpu_state,
)
from lib.gpu_stress import launch_gpu_stress, stop_gpu_stress

from lib.coupled_black_hole import (
    COUPLED_ARTIFACTS,
    CoupledEngine,
    append_coupled_log,
    print_coupled_line,
    write_coupled_state,
)
from lib.coupled_report import generate_coupled_reports

VERSION = "2.0.0-pc"

EXTREME = {
    "mass": 0.65,
    "density": 0.40,
    "energy": 0.75,
}

GPU_EXTREME = {
    "mass": 0.60,
    "density": 0.45,
    "energy": 0.82,
}


def cmd_once(args: argparse.Namespace) -> int:
    eng = ChannelEngine()
    s = sample_once(eng, phone_compat=args.phone_compat)
    write_state(s)
    if args.json:
        print(json.dumps(s.to_dict(), indent=2))
    else:
        print(format_line(s), flush=True)
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    eng = ChannelEngine()
    thr = _thresholds(args)
    print(f"Black hole watch @ {args.interval}s | Mass>{thr['mass']} Dens>{thr['density']} En<{thr['energy']}")
    try:
        while True:
            s = sample_once(eng, phone_compat=args.phone_compat)
            if _check_custom(eng, s, thr, args.phone_compat):
                s.collapsed = True
                s.latched = eng.latched
            write_state(s)
            if args.log:
                append_log(s)
            print(format_line(s), flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped.")
        return 0


def cmd_collapse(args: argparse.Namespace) -> int:
    """Launch stressors + monitor for event horizon."""
    thr = _thresholds(args)
    n = args.cores if args.cores > 0 else None
    procs = launch_stressors(n)
    print("=== BLACK HOLE COLLAPSE SIMULATOR (PC) ===")
    print(f"Mass > {thr['mass']}  |  Density > {thr['density']}  |  Energy < {thr['energy']}")
    print(f"Pi storm on {len(procs)} cores + memory apocalypse. Ctrl+C to stop.\n")
    time.sleep(args.warmup)
    eng = ChannelEngine()
    t0 = time.time()
    duration = float(args.seconds)
    try:
        while duration <= 0 or (time.time() - t0 < duration):
            s = sample_once(eng, phone_compat=args.phone_compat)
            if _check_custom(eng, s, thr, args.phone_compat):
                s.collapsed = True
                s.latched = eng.latched
            write_state(s)
            append_log(s)
            print_line(s)
            if s.latched and args.stop_on_latch:
                print("Event horizon latched. Stressors stopping.", flush=True)
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        stop_stressors(procs)
    print(f"state: {BH_ARTIFACTS / 'collapse_state.json'}")
    return 0


def _thresholds(args: argparse.Namespace) -> dict[str, float]:
    if args.extreme:
        return dict(EXTREME)
    return {
        "mass": args.mass if args.mass is not None else MASS_CRITICAL,
        "density": args.density if args.density is not None else DENSITY_CRITICAL,
        "energy": args.energy if args.energy is not None else ENERGY_CRITICAL,
    }


def _check_custom(
    eng: ChannelEngine,
    s,
    thr: dict[str, float],
    phone_compat: bool,
) -> bool:
    event = eng.collapsed(
        s.mass,
        s.density,
        s.energy,
        phone_compat=phone_compat,
        mass_thr=thr["mass"],
        density_thr=thr["density"],
        energy_thr=thr["energy"],
    )
    return event


def cmd_gpu_once(args: argparse.Namespace) -> int:
    eng = GpuChannelEngine()
    s = sample_gpu_once(eng, index=args.gpu)
    write_gpu_state(s)
    if args.json:
        print(json.dumps(s.to_dict(), indent=2))
    else:
        print_gpu_line(s)
    return 0


def cmd_gpu_watch(args: argparse.Namespace) -> int:
    eng = GpuChannelEngine()
    thr = _gpu_thresholds(args)
    print(
        f"GPU black hole watch @ {args.interval}s | "
        f"Mass>{thr['mass']} Dens>{thr['density']} En<{thr['energy']} (air-cooled plant)"
    )
    try:
        while True:
            s = sample_gpu_once(eng, index=args.gpu)
            _gpu_check(eng, s, thr)
            write_gpu_state(s)
            if args.log:
                append_gpu_log(s)
            print_gpu_line(s)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped.")
        return 0


def cmd_gpu_collapse(args: argparse.Namespace) -> int:
    thr = _gpu_thresholds(args)
    mode = getattr(args, "gpu_stress", "extreme") or "extreme"
    procs = launch_gpu_stress(mode)
    print(f"=== GPU BLACK HOLE COLLAPSE ({mode.upper()} OpenCL on RTX) ===")
    print(f"Mass > {thr['mass']}  |  Density > {thr['density']}  |  Energy < {thr['energy']}")
    print("OpenCL matmul burn + VRAM apocalypse on NVIDIA GPU.\n")
    time.sleep(args.warmup)
    eng = GpuChannelEngine()
    t0 = time.time()
    duration = float(args.seconds)
    try:
        while duration <= 0 or (time.time() - t0 < duration):
            s = sample_gpu_once(eng, index=args.gpu)
            _gpu_check(eng, s, thr)
            write_gpu_state(s)
            append_gpu_log(s)
            print_gpu_line(s)
            if s.latched and args.stop_on_latch:
                print("GPU event horizon latched. Stressors stopping.", flush=True)
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        stop_gpu_stress(procs)
    print(f"state: {GPU_BH_ARTIFACTS / 'collapse_state.json'}")
    return 0


def _gpu_thresholds(args: argparse.Namespace) -> dict[str, float]:
    if getattr(args, "extreme", False):
        return dict(GPU_EXTREME)
    from lib.gpu_black_hole_engine import DENSITY_CRITICAL, ENERGY_CRITICAL, MASS_CRITICAL

    return {
        "mass": args.mass if getattr(args, "mass", None) is not None else MASS_CRITICAL,
        "density": args.density if getattr(args, "density", None) is not None else DENSITY_CRITICAL,
        "energy": args.energy if getattr(args, "energy", None) is not None else ENERGY_CRITICAL,
    }


def _gpu_check(eng: GpuChannelEngine, s, thr: dict[str, float]) -> None:
    if eng.collapsed(
        s.mass,
        s.density,
        s.energy,
        mass_thr=thr["mass"],
        density_thr=thr["density"],
        energy_thr=thr["energy"],
    ):
        s.collapsed = True
        s.latched = eng.latched


def cmd_coupled_collapse(args: argparse.Namespace) -> int:
    cpu_thr = _thresholds(args)
    gpu_thr = _gpu_thresholds(args)
    mode = getattr(args, "gpu_stress", "rtx") or "rtx"
    cpu_procs = launch_stressors(args.cores if args.cores > 0 else None)
    gpu_procs = launch_gpu_stress(mode)
    print(f"=== COUPLED BLACK HOLE (CPU liquid + GPU {mode.upper()}) ===")
    print(f"CPU: Mass>{cpu_thr['mass']} Dens>{cpu_thr['density']} En<{cpu_thr['energy']}")
    print(f"GPU: Mass>{gpu_thr['mass']} Dens>{gpu_thr['density']} En<{gpu_thr['energy']}")
    print(f"Pi storm + RAM apocalypse + OpenCL GPU burn. Ctrl+C to stop.\n")
    time.sleep(args.warmup)
    eng = CoupledEngine()
    t0 = time.time()
    duration = float(args.seconds)
    last_regime = ""
    last_sample = None
    try:
        while duration <= 0 or (time.time() - t0 < duration):
            s = eng.tick(
                cpu_thr=cpu_thr,
                gpu_thr=gpu_thr,
                phone_compat=args.phone_compat,
                gpu_index=args.gpu,
            )
            last_sample = s
            write_coupled_state(s)
            append_coupled_log(s)
            print_coupled_line(s)
            if s.regime != last_regime:
                print(f"  >> regime: {s.regime}", flush=True)
                last_regime = s.regime
            if args.stop_on_dual and s.dual_horizon:
                print("DUAL EVENT HORIZON latched. Stressors stopping.", flush=True)
                break
            if args.stop_on_any and (s.cpu_horizon or s.gpu_horizon):
                print(f"Horizon crossed ({s.regime}). Stressors stopping.", flush=True)
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        stop_stressors(cpu_procs)
        stop_gpu_stress(gpu_procs)
    print(f"state: {COUPLED_ARTIFACTS / 'collapse_state.json'}")
    if last_sample and (eng.cpu_eng.latched or eng.gpu_eng.latched):
        print(
            f"horizons: cpu={'yes' if eng.cpu_eng.latched else 'no'} "
            f"gpu={'yes' if eng.gpu_eng.latched else 'no'} "
            f"first={last_sample.first_plant} lag={last_sample.horizon_lag_s}s"
        )
    return 0


def cmd_coupled_run(args: argparse.Namespace) -> int:
    """Full coupled collapse + trajectory + cpu_gpu triad plots."""
    args.extreme = True
    args.stop_on_dual = getattr(args, "stop_on_dual", False)
    args.stop_on_any = getattr(args, "stop_on_any", False)
    args.phone_compat = getattr(args, "phone_compat", False)
    args.gpu = getattr(args, "gpu", 0)
    seconds = float(args.seconds) if args.seconds else 120.0
    args.seconds = seconds
    print(f"=== COUPLED RUN {seconds:.0f}s — stress, log, plot ===\n")
    rc = cmd_coupled_collapse(args)
    if rc != 0:
        return rc
    report = generate_coupled_reports()
    print("\n--- Coupled report ---")
    print(json.dumps(report, indent=2))
    return 0


def cmd_gpu_triad(args: argparse.Namespace) -> int:
    import gpu_triad_main as m

    argv: list[str] = []
    if args.seconds:
        argv.extend(["--seconds", str(args.seconds)])
    if getattr(args, "pair", None):
        argv.extend(["--pair", args.pair])
    if getattr(args, "gpu_stress", None):
        argv.extend(["--stress", args.gpu_stress])
    return m.main(argv)


def cmd_visual(args: argparse.Namespace) -> int:
    import black_hole_visual_main as m

    argv: list[str] = []
    if args.seconds:
        argv.extend(["--seconds", str(args.seconds)])
    if getattr(args, "gpu_stress", None):
        argv.extend(["--gpu-stress", args.gpu_stress])
    if getattr(args, "windowed", False):
        argv.append("--windowed")
    return m.main(argv)


def cmd_coupled_once(args: argparse.Namespace) -> int:
    eng = CoupledEngine()
    s = eng.tick(
        cpu_thr=_thresholds(args),
        gpu_thr=_gpu_thresholds(args),
        phone_compat=args.phone_compat,
        gpu_index=args.gpu,
    )
    write_coupled_state(s)
    if args.json:
        print(json.dumps(s.to_dict(), indent=2))
    else:
        print_coupled_line(s)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="black_hole_main", description="RID black hole collapse simulator (PC)")
    p.add_argument("--version", action="version", version=f"black_hole_main {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    o = sub.add_parser("once", help="Single telemetry sample")
    o.add_argument("--json", action="store_true")
    o.add_argument("--phone-compat", action="store_true", help="Use phone RLE formula")
    o.set_defaults(func=cmd_once)

    w = sub.add_parser("watch", help="Monitor without stressors")
    w.add_argument("--interval", type=float, default=1.0)
    w.add_argument("--log", action="store_true")
    w.add_argument("--phone-compat", action="store_true")
    w.add_argument("--extreme", action="store_true")
    w.add_argument("--mass", type=float, default=None)
    w.add_argument("--density", type=float, default=None)
    w.add_argument("--energy", type=float, default=None)
    w.set_defaults(func=cmd_watch)

    c = sub.add_parser("collapse", help="Pi storm + memory apocalypse + event horizon monitor")
    c.add_argument("--interval", type=float, default=1.0)
    c.add_argument("--seconds", type=float, default=0.0, help="0 = run until Ctrl+C")
    c.add_argument("--warmup", type=float, default=3.0)
    c.add_argument("--cores", type=int, default=0, help="0 = all logical cores")
    c.add_argument("--extreme", action="store_true", help="Lower thresholds + latch-friendly")
    c.add_argument("--stop-on-latch", action="store_true", help="Stop stressors once horizon latched")
    c.add_argument("--phone-compat", action="store_true")
    c.add_argument("--mass", type=float, default=None)
    c.add_argument("--density", type=float, default=None)
    c.add_argument("--energy", type=float, default=None)
    c.set_defaults(func=cmd_collapse)

    g1 = sub.add_parser("gpu-once", help="Single GPU plant sample (NVML)")
    g1.add_argument("--gpu", type=int, default=0)
    g1.add_argument("--json", action="store_true")
    g1.set_defaults(func=cmd_gpu_once)

    gw = sub.add_parser("gpu-watch", help="Monitor GPU plant without stress")
    gw.add_argument("--gpu", type=int, default=0)
    gw.add_argument("--interval", type=float, default=1.0)
    gw.add_argument("--log", action="store_true")
    gw.add_argument("--extreme", action="store_true")
    gw.add_argument("--mass", type=float, default=None)
    gw.add_argument("--density", type=float, default=None)
    gw.add_argument("--energy", type=float, default=None)
    gw.set_defaults(func=cmd_gpu_watch)

    gc = sub.add_parser("gpu-collapse", help="OpenCL GPU stress + event horizon monitor")
    gc.add_argument("--gpu", type=int, default=0)
    gc.add_argument("--interval", type=float, default=1.0)
    gc.add_argument("--seconds", type=float, default=0.0)
    gc.add_argument("--warmup", type=float, default=3.0)
    gc.add_argument("--extreme", action="store_true")
    gc.add_argument("--stop-on-latch", action="store_true")
    gc.add_argument("--mass", type=float, default=None)
    gc.add_argument("--density", type=float, default=None)
    gc.add_argument("--energy", type=float, default=None)
    gc.add_argument("--gpu-stress", default="extreme", choices=["normal", "extreme", "rtx"])
    gc.set_defaults(func=cmd_gpu_collapse)

    cp = sub.add_parser("coupled-collapse", help="CPU+GPU dual plant stress + horizon correlation")
    cp.add_argument("--gpu", type=int, default=0)
    cp.add_argument("--interval", type=float, default=1.0)
    cp.add_argument("--seconds", type=float, default=0.0)
    cp.add_argument("--warmup", type=float, default=4.0)
    cp.add_argument("--cores", type=int, default=0)
    cp.add_argument("--extreme", action="store_true", help="Use extreme thresholds for both plants")
    cp.add_argument("--gpu-stress", default="rtx", choices=["normal", "extreme", "rtx"])
    cp.add_argument("--stop-on-dual", action="store_true", help="Stop when BOTH horizons latched")
    cp.add_argument("--stop-on-any", action="store_true", help="Stop when EITHER horizon latched")
    cp.add_argument("--phone-compat", action="store_true")
    cp.set_defaults(func=cmd_coupled_collapse)

    cr = sub.add_parser("coupled-run", help="120s coupled RTX stress + trajectory + cpu_gpu triad plots")
    cr.add_argument("--seconds", type=float, default=120.0)
    cr.add_argument("--interval", type=float, default=1.0)
    cr.add_argument("--gpu-stress", default="rtx", choices=["normal", "extreme", "rtx"])
    cr.add_argument("--cores", type=int, default=0)
    cr.add_argument("--warmup", type=float, default=4.0)
    cr.set_defaults(func=cmd_coupled_run)

    gt = sub.add_parser("gpu-triad", help="GPU temp/power triad plot (NVML)")
    gt.add_argument("--seconds", type=float, default=120.0)
    gt.add_argument("--pair", default="temp_power", choices=["temp_power", "temp_vram", "temp_clock"])
    gt.add_argument("--gpu-stress", default="rtx", choices=["normal", "extreme", "rtx"])
    gt.set_defaults(func=cmd_gpu_triad)

    vis = sub.add_parser("visual", help="Black hole 3D visual (PC port blackholev3)")
    vis.add_argument("--seconds", type=float, default=180.0)
    vis.add_argument("--gpu-stress", default="rtx", choices=["normal", "extreme", "rtx"])
    vis.add_argument("--windowed", action="store_true")
    vis.set_defaults(func=cmd_visual)

    c1 = sub.add_parser("coupled-once", help="Single coupled sample (no stress)")
    c1.add_argument("--gpu", type=int, default=0)
    c1.add_argument("--json", action="store_true")
    c1.add_argument("--extreme", action="store_true")
    c1.add_argument("--phone-compat", action="store_true")
    c1.set_defaults(func=cmd_coupled_once)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
