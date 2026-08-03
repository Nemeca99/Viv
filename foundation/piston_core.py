#!/usr/bin/env python3
"""
Viv foundation — Piston-core thermal control (RID per-core).

8-cylinder model: paired cores (0-1, 2-3, 4-5, 6-7), one active per pair,
dynamic swap when S_n,i drops below threshold. Uses Corsair iCUE per-core temps.
"""
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

from lib.governor_params import load_params, rollback_params
from lib.governor_self_tune import evaluate_tune_window, read_history, tune_once
from lib.piston_engine import (
    PISTON_STATE_PATH,
    PistonController,
    detect_hardware,
    format_status_line,
    halt,
    is_halted,
    journal_piston_event,
    resume,
    sn_to_budget,
    write_piston_state,
)
from lib.cpu_governor import GovernedFleet
from lib.rid_stressor import cpu_burn, stop_stressor

VERSION = "1.3.0"


def cmd_status(_: argparse.Namespace) -> int:
    if not PISTON_STATE_PATH.is_file():
        print("No piston state yet. Run: piston_core.py once")
        return 2
    print(PISTON_STATE_PATH.read_text(encoding="utf-8"))
    return 0


def cmd_once(args: argparse.Namespace) -> int:
    ctl = PistonController()
    state = ctl.tick()
    path = write_piston_state(state)
    if not args.no_journal:
        journal_piston_event(state)
    if args.json:
        print(json.dumps(state.to_dict(), indent=2))
    else:
        print(format_status_line(state))
        print(f"wrote {path}")
    return 0


def cmd_loop(args: argparse.Namespace) -> int:
    ctl = PistonController()
    print(f"Piston-core @ {args.interval}s — Corsair per-core temps. Ctrl+C to stop.")
    try:
        while True:
            state = ctl.tick()
            write_piston_state(state)
            if not args.no_journal:
                journal_piston_event(state)
            print(format_status_line(state))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped.")
        return 0


def cmd_stress_demo(args: argparse.Namespace) -> int:
    """Pin one burner to active core of pair 0; swap on S_n threshold."""
    ctl = PistonController()
    pair_idx = 0
    duration = max(5.0, float(args.seconds))
    print(f"Stress demo {duration:.0f}s - single-core burner on pair {pair_idx}, auto-swap enabled.")
    proc = multiprocessing.Process(target=cpu_burn, daemon=True)
    proc.start()
    active = ctl.active_by_pair[pair_idx]
    ctl.set_affinity(proc.pid, active)
    print(f"burner pid={proc.pid} on core {active}")
    t0 = time.time()
    try:
        while time.time() - t0 < duration:
            state = ctl.tick()
            state.stress_pid = proc.pid
            new_active = int(state.active_by_pair[str(pair_idx)])
            if new_active != active:
                print(f"  SWAP core {active} -> {new_active} (S_n low)")
                active = new_active
                ctl.set_affinity(proc.pid, active)
            write_piston_state(state)
            if not args.no_journal:
                journal_piston_event(state)
            print(format_status_line(state))
            for c in state.cores:
                if c.core in (ctl.pairs[pair_idx][0], ctl.pairs[pair_idx][1]):
                    print(
                        f"    core {c.core}: T={c.temp_c:.1f}C load={c.load_pct:.0f}% "
                        f"S_n={c.s_n:.3f} RSR={c.rsr:.2f} LTP={c.ltp:.2f} RLE={c.rle:.2f}"
                    )
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        stop_stressor([proc])
    print("demo complete.")
    return 0


def cmd_budget(args: argparse.Namespace) -> int:
    """Show the S_n -> allowed CPU% mapping for the current per-core state."""
    ctl = PistonController()
    state = ctl.tick()
    if args.json:
        print(json.dumps({
            "package_s_n": round(state.package_s_n, 4),
            "cpu_budget_pct": state.package_budget_pct,
            "budget_by_core": state.budget_by_core,
        }, indent=2))
        return 0
    print(f"[GOVERNOR] package S_n={state.package_s_n:.3f} -> CPU budget {state.package_budget_pct:.0f}%")
    for c in sorted(state.cores, key=lambda x: x.core):
        raw = sn_to_budget(c.s_n) * 100.0
        print(
            f"  core {c.core}: T={c.temp_c:.1f}C S_n={c.s_n:.3f} "
            f"-> allowed {state.budget_by_core.get(str(c.core), raw):.0f}% (raw {raw:.0f}%)"
        )
    return 0


def cmd_govern(args: argparse.Namespace) -> int:
    """Actively govern managed CPU load: each core's duty = its S_n budget.

    Fail-safe: on any tick error the fleet is throttled to the floor (less heat).
    With --self-tune, periodically analyzes history and adjusts governor params.
    """
    ctl = PistonController()
    cores = list(range(ctl.n_cores)) if args.all_cores else [c for pair in ctl.pairs for c in pair]
    fleet = GovernedFleet(cores)
    fleet.start(initial_duty=0.0)
    duration = float(args.seconds)
    forever = duration <= 0
    tune_every = int(args.tune_every) if args.self_tune else 0
    beats_since_tune = 0
    hist_len_at_tune = 0
    pending_eval = False
    print(
        f"S_n CPU governor on cores {cores} - duty = S_n budget. "
        f"{'run until Ctrl+C' if forever else f'{duration:.0f}s'}."
    )
    if args.self_tune:
        print(f"  self-tune every {tune_every} beats (rollback if stability worsens)")
    print(f"  fleet pids: {fleet.pids()}")
    t0 = time.time()
    beat_n = 0
    try:
        while forever or (time.time() - t0 < duration):
            try:
                state = ctl.tick()
            except Exception as exc:
                fleet.set_all(0.0)
                print(f"  FAULT {exc!r} -> fleet throttled to floor")
                time.sleep(args.interval)
                continue
            for c in state.cores:
                if c.core in cores:
                    fleet.set_duty(c.core, ctl.core_budget(c.core))
            write_piston_state(state)
            if not args.no_journal:
                journal_piston_event(state)
            print(format_status_line(state))
            if args.verbose:
                for c in sorted(state.cores, key=lambda x: x.core):
                    if c.core in cores:
                        print(
                            f"    core {c.core}: T={c.temp_c:.1f}C S_n={c.s_n:.3f} "
                            f"load={c.load_pct:.0f}% -> budget "
                            f"{state.budget_by_core.get(str(c.core), 0):.0f}%"
                        )
            beat_n += 1
            if args.self_tune and tune_every > 0:
                if pending_eval and beat_n >= tune_every // 2:
                    hist = read_history(500)
                    before = hist[hist_len_at_tune : hist_len_at_tune + tune_every // 2]
                    after = hist[-(tune_every // 2) :]
                    ev = evaluate_tune_window(before, after)
                    if ev.get("rollback"):
                        ok, prev = rollback_params()
                        if ok:
                            ctl.reload_params()
                            print(f"  ROLLBACK params v{prev.version} ({ev['verdict']})")
                    pending_eval = False
                beats_since_tune += 1
                if beats_since_tune >= tune_every:
                    hist_len_at_tune = len(read_history(500))
                    report = tune_once(dry_run=False)
                    ctl.reload_params()
                    beats_since_tune = 0
                    pending_eval = report.get("verdict") == "APPLIED"
                    ch = report.get("proposal", {}).get("changes", [])
                    if ch:
                        print(f"  SELF-TUNE v{report['params_after']['version']}: {ch}")
                    elif report.get("verdict") == "NO_CHANGE":
                        print(f"  SELF-TUNE: {report.get('proposal', {}).get('reason', 'no change')}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        fleet.stop()
    print("governor stopped (fleet throttled to 0).")
    return 0


def cmd_tune(args: argparse.Namespace) -> int:
    report = tune_once(dry_run=args.dry_run)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"[SELF-TUNE] verdict={report['verdict']}")
    prop = report.get("proposal", {})
    if prop.get("changes"):
        for ch in prop["changes"]:
            print(f"  {ch['field']}: {ch['from']} -> {ch['to']} ({ch['why']})")
    else:
        print(f"  reason: {prop.get('reason', 'n/a')}")
    m = report.get("metrics", {})
    if m.get("verdict") == "OK":
        print(
            f"  n={m['n']} dormancy={m['dormancy_rate']:.2%} "
            f"budget_std={m['budget_std']:.1f} max_T={m['max_temp_c']:.1f}C"
        )
    return 0


def cmd_rollback(_: argparse.Namespace) -> int:
    ok, params = rollback_params()
    if ok:
        print(f"Rolled back governor params to version {params.version}")
        print(json.dumps(params.to_dict(), indent=2))
        return 0
    print("No backup to roll back to.")
    return 2


def cmd_params(args: argparse.Namespace) -> int:
    p = load_params()
    if args.json:
        print(json.dumps(p.to_dict(), indent=2))
    else:
        print(f"governor params v{p.version} source={p.source}")
        print(json.dumps(p.to_dict(), indent=2))
    return 0


def cmd_hardware(args: argparse.Namespace) -> int:
    """Prove hardware-agnostic scaling: show what this machine exposes."""
    cap = detect_hardware()
    ctl = PistonController()
    info = {
        "capabilities": cap,
        "governed_cores": ctl.n_cores,
        "pairs": [list(p) for p in ctl.pairs],
        "thermal_mode": ctl.thermal_mode,
        "halted": is_halted(),
    }
    if args.json:
        print(json.dumps(info, indent=2))
        return 0
    print(f"[HARDWARE] logical={cap['logical_cores']} physical={cap['physical_cores']} "
          f"per_core_temp={cap['per_core_temp']} package_temp={cap['package_temp']}")
    print(f"  governing {ctl.n_cores} cores as {len(ctl.pairs)} pairs, thermal_mode={ctl.thermal_mode}")
    if ctl.thermal_mode != "real":
        print("  NOTE: no thermal sensor detected -> degraded load-only headroom (surfaced, not silent).")
    if is_halted():
        print("  CONTAINMENT ACTIVE: layer is HALTED. Run: piston_core.py resume")
    return 0


def cmd_halt(args: argparse.Namespace) -> int:
    """Containment: force the whole layer to safe state (budgets -> floor)."""
    path = halt(reason=args.reason)
    print(f"HALTED ({args.reason}). Flag: {path}")
    print("All CPU budgets forced to floor until resumed.")
    return 0


def cmd_resume(_: argparse.Namespace) -> int:
    if resume():
        print("Containment lifted. Governor will resume S_n-based budgets.")
        return 0
    print("Not halted (no flag present).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="piston_core",
        description="RID piston-core per-core thermal control (Viv CPU layer).",
    )
    p.add_argument("--version", action="version", version=f"piston_core {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show last piston_state.json").set_defaults(func=cmd_status)

    o = sub.add_parser("once", help="One 1 Hz piston tick")
    o.add_argument("--json", action="store_true")
    o.add_argument("--no-journal", action="store_true")
    o.set_defaults(func=cmd_once)

    lp = sub.add_parser("loop", help="1 Hz piston control loop")
    lp.add_argument("--interval", type=float, default=1.0)
    lp.add_argument("--no-journal", action="store_true")
    lp.set_defaults(func=cmd_loop)

    sd = sub.add_parser("stress-demo", help="Single-core stress with auto pair swap")
    sd.add_argument("--seconds", type=float, default=30.0)
    sd.add_argument("--interval", type=float, default=1.0)
    sd.add_argument("--no-journal", action="store_true")
    sd.set_defaults(func=cmd_stress_demo)

    bg = sub.add_parser("budget", help="Show S_n -> allowed CPU%% mapping (one tick)")
    bg.add_argument("--json", action="store_true")
    bg.set_defaults(func=cmd_budget)

    gv = sub.add_parser("govern", help="Actively govern managed CPU: duty = S_n budget")
    gv.add_argument("--seconds", type=float, default=0.0, help="0 = run until Ctrl+C")
    gv.add_argument("--interval", type=float, default=1.0)
    gv.add_argument("--all-cores", action="store_true", help="Govern all cores, not just pairs")
    gv.add_argument("--verbose", action="store_true", help="Per-core budget lines")
    gv.add_argument("--no-journal", action="store_true")
    gv.add_argument("--self-tune", action="store_true", help="Self-modify governor params from history")
    gv.add_argument("--tune-every", type=int, default=30, help="Beats between self-tune cycles")
    gv.set_defaults(func=cmd_govern)

    tn = sub.add_parser("tune", help="Run one self-modify governor cycle from history")
    tn.add_argument("--dry-run", action="store_true")
    tn.add_argument("--json", action="store_true")
    tn.set_defaults(func=cmd_tune)

    sub.add_parser("rollback", help="Rollback governor params to last backup").set_defaults(func=cmd_rollback)

    pr = sub.add_parser("params", help="Show active governor parameters")
    pr.add_argument("--json", action="store_true")
    pr.set_defaults(func=cmd_params)

    hw = sub.add_parser("hardware", help="Show detected hardware + agnostic scaling")
    hw.add_argument("--json", action="store_true")
    hw.set_defaults(func=cmd_hardware)

    ht = sub.add_parser("halt", help="Containment: force layer to safe state")
    ht.add_argument("--reason", default="operator")
    ht.set_defaults(func=cmd_halt)

    sub.add_parser("resume", help="Lift containment halt").set_defaults(func=cmd_resume)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
