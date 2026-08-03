#!/usr/bin/env python3
"""
Viv foundation — RID main (Vidi).

Consolidates phone/PC RID work: live telemetry, CSV logging, stress tests,
and the v1.2 stability-coupled efficiency benchmark.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.paths import RID_ARTIFACTS
from lib.rid_benchmark import cli as benchmark_cli
from lib.rid_cross_compare import PHONE_BASELINE, compare, latest_pc_run, write_report
from lib.rid_stressor import start_stressor, stop_stressor
from lib.rid_feed import LIVE_SAMPLE_PATH, pulse_once, write_live
from lib.rid_telemetry import (
    DORMANCY_THRESHOLD,
    format_line,
    sample_once,
    write_json_sample,
)
from lib.triad_kernel import TRIAD_CONTRACT_VERSION

VERSION = "2.0.0-pc"

CSV_HEADER = [
    "timestamp", "t_s", "a_c", "b_c", "a_label", "b_label",
    "ltp", "rsr", "rle", "rle_rate", "runtime_rsr", "runtime_ltp", "runtime_rle",
    "s_n", "cpu_load_pct", "ram_pct", "status",
]

CANONICAL_CAPTURES = {
    "coolant": {
        "csv": RID_ARTIFACTS / "stability_pc_120s_v5.csv",
        "summary": RID_ARTIFACTS / "stability_pc_120s_v5.summary.json",
        "pair": "cpu_coolant",
    },
    "coupled": {
        "csv": RID_ARTIFACTS / "coupled_master_120s_v2.csv",
        "summary": RID_ARTIFACTS / "coupled_master_120s_v2.summary.json",
        "pair": "cpu_gpu",
    },
    "core_spread": {
        "csv": RID_ARTIFACTS / "core_spread_master_120s_v1.csv",
        "summary": RID_ARTIFACTS / "core_spread_master_120s_v1.summary.json",
        "pair": "core_spread",
    },
}


def triad_descriptor() -> dict:
    """Stable import-time contract consumed by the AIOS Triad kernel."""
    return {
        "pillar": "rid",
        "name": "Vidi",
        "version": VERSION,
        "triad_contract_version": TRIAD_CONTRACT_VERSION,
        "capabilities": ["observe", "stability", "resource_state"],
        "authority": "measurement_not_security",
    }


def triad_observe(envelope: dict) -> dict:
    """Return the latest bounded RID state without forcing a new sensor capture."""
    from lib.master_rid import load_master_rid

    requested_s_n = float(envelope.get("s_n", 0.0))
    master = load_master_rid()
    if master is None:
        return {
            "allowed": True,
            "source": "envelope_s_n",
            "s_n": requested_s_n,
            "status": "NO_LIVE_MASTER_RID",
            "fresh_measurement": False,
        }
    return {
        "allowed": True,
        "source": "master_rid",
        "s_n": float(master.master_s_n),
        "requested_s_n": requested_s_n,
        "status": str(master.status),
        "timestamp": str(master.timestamp),
        "n_subsystems": int(master.n_subsystems),
        "fresh_measurement": False,
    }


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _capture_status(kind: str, spec: dict) -> dict:
    summary_path = Path(spec["summary"])
    summary = _load_json(summary_path)
    verdict = summary.get("capture_verdict")
    return {
        "kind": kind,
        "pair": spec.get("pair"),
        "csv": str(spec["csv"]),
        "summary": str(summary_path),
        "exists": summary_path.is_file(),
        "verdict": verdict,
        "polls": summary.get("polls"),
        "expected_polls": summary.get("expected_polls"),
        "actual_hz": summary.get("actual_hz"),
        "cpu_load_max_pct": summary.get("cpu_load_max_pct"),
        "gpu_util_max_pct": summary.get("gpu_util_max_pct"),
        "master_s_n_mean": summary.get("master_s_n_mean", summary.get("s_n_mean")),
        "master_s_n_min": summary.get("master_s_n_min", summary.get("s_n_min")),
    }


def cmd_watch(args: argparse.Namespace) -> int:
    print(f"RID watch PC (Ctrl+C). Dormancy S_n < {DORMANCY_THRESHOLD}. Sensors: cpu_pkg + gpu")
    try:
        while True:
            s = sample_once()
            print(format_line(s))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped.")
        return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    """Architect plant monitor — per-core load/temp + Corsair + NVML + Master RID."""
    from lib.architect_monitor import run_monitor
    from lib.paths import RID_ARTIFACTS

    jsonl = Path(args.jsonl) if args.jsonl else RID_ARTIFACTS / "architect_monitor.jsonl"
    report = run_monitor(
        interval=float(args.interval),
        seconds=float(args.seconds) if args.seconds else None,
        n_cores=args.cores,
        jsonl=jsonl,
        clear=not bool(args.no_clear),
        publish=not bool(args.no_publish),
    )
    print(json.dumps(report, indent=2))
    return 0

def cmd_log(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv) if args.csv else RID_ARTIFACTS / "telemetry.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not csv_path.is_file()
    print(f"Logging to {csv_path} every {args.interval}s (Ctrl+C to stop)")
    try:
        with open(csv_path, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new_file:
                w.writerow(CSV_HEADER)
            while True:
                s = sample_once()
                w.writerow([
                    s.timestamp, s.t_s, s.a_c, s.b_c, s.a_label, s.b_label,
                    s.ltp, s.rsr, s.rle, s.rle_rate, s.runtime_rsr, s.runtime_ltp, s.runtime_rle,
                    s.s_n, s.cpu_load_pct, s.ram_pct, s.status,
                ])
                fh.flush()
                print(format_line(s))
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped.")
        return 0


def cmd_stress(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv) if args.csv else RID_ARTIFACTS / "stress_test.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not csv_path.is_file()
    print("=== RID stress test ===")
    print(f"Logging to {csv_path}")
    procs = start_stressor(args.cores)
    time.sleep(0.5)
    try:
        with open(csv_path, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new_file:
                w.writerow(CSV_HEADER)
            while True:
                s = sample_once()
                w.writerow([
                    s.timestamp, s.t_s, s.a_c, s.b_c, s.a_label, s.b_label,
                    s.ltp, s.rsr, s.rle, s.rle_rate, s.runtime_rsr, s.runtime_ltp, s.runtime_rle,
                    s.s_n, s.cpu_load_pct, s.ram_pct, s.status,
                ])
                fh.flush()
                print(format_line(s))
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopping stressor…")
        stop_stressor(procs)
        return 0


def cmd_feed(args: argparse.Namespace) -> int:
    out = Path(args.json) if args.json else LIVE_SAMPLE_PATH
    print(f"RID feed -> {out} every {args.interval}s (Ctrl+C to stop)")
    try:
        while True:
            s = sample_once()
            write_live(s, out)
            print(format_line(s))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped.")
        return 0


def cmd_sample(args: argparse.Namespace) -> int:
    s = sample_once()
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_json_sample(out, s)
        print(out)
    else:
        print(json.dumps(s.to_dict()))
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    argv = ["rid_benchmark"]
    if args.seconds is not None:
        argv.extend(["--seconds", str(args.seconds)])
    if args.rounds is not None:
        argv.extend(["--rounds", str(args.rounds)])
    if args.settle is not None:
        argv.extend(["--settle", str(args.settle)])
    if args.saboteur_mem is not None:
        argv.extend(["--saboteur-mem", str(args.saboteur_mem)])
    if args.smoke:
        argv.append("--smoke")
    if args.interactive:
        argv.append("--interactive")
    return benchmark_cli(argv[1:])


def cmd_compare(args: argparse.Namespace) -> int:
    phone = Path(args.phone) if args.phone else PHONE_BASELINE
    pc = Path(args.pc) if args.pc else latest_pc_run()
    if pc is None:
        print("No PC benchmark found. Run: rid_main benchmark --seconds 10 --rounds 8", file=sys.stderr)
        return 2
    report = compare(phone_path=phone, pc_path=pc)
    out_json = Path(args.json) if args.json else RID_ARTIFACTS / "pc_vs_phone_report.json"
    out_md = Path(args.md) if args.md else RID_ARTIFACTS / "pc_vs_phone_report.md"
    write_report(report, out_json, out_md)
    if args.quiet:
        print(out_json)
    else:
        print(report["summary"])
        print(f"wrote {out_json}")
        print(f"wrote {out_md}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Read-only RID pillar status: captures, Master S_n, piston, GPU, plant verdict."""
    from lib.master_rid import MASTER_RID_PATH
    from lib.piston_background import read_piston_snapshot
    from lib.plant_piston_bridge import LAST_CAPTURE_PATH

    captures = {
        kind: _capture_status(kind, spec)
        for kind, spec in CANONICAL_CAPTURES.items()
    }
    payload = {
        "rid_main": str(_ROOT / "rid_main.py"),
        "canonical_alpha_root": str(_ROOT.parent),
        "canonical_captures": captures,
        "master_rid_path": str(MASTER_RID_PATH),
        "master_rid": _load_json(MASTER_RID_PATH),
        "plant_last_capture_path": str(LAST_CAPTURE_PATH),
        "plant_last_capture": _load_json(LAST_CAPTURE_PATH),
        "piston": read_piston_snapshot(),
        "gpu": None,
    }
    try:
        from lib.gpu_plant import read_gpu

        payload["gpu"] = read_gpu(0).to_dict()
    except Exception as exc:
        payload["gpu"] = {"available": False, "error": str(exc)}

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print("=== RID pillar status ===")
    master = payload.get("master_rid") or {}
    if master:
        print(
            f"Master_S_n={master.get('master_s_n')} "
            f"status={master.get('status')} subsystems={master.get('n_subsystems')}"
        )
    else:
        print("Master_S_n: missing")
    print("\nCanonical captures:")
    for kind, item in captures.items():
        exists = "yes" if item["exists"] else "no"
        print(
            f"  {kind:11s} exists={exists} verdict={item.get('verdict')} "
            f"polls={item.get('polls')}/{item.get('expected_polls') or '-'} "
            f"hz={item.get('actual_hz') or '-'}"
        )
    plant = payload.get("plant_last_capture") or {}
    verdict = (plant.get("verdict") or {}).get("verdict")
    print(f"\nPlant bridge: {verdict or 'missing'} -> {LAST_CAPTURE_PATH}")
    piston = payload.get("piston") or {}
    print(
        f"Piston: available={piston.get('available')} "
        f"pkg_S_n={piston.get('package_s_n')} background={piston.get('background')}"
    )
    gpu = payload.get("gpu") or {}
    print(
        f"GPU: available={gpu.get('available', True)} "
        f"name={gpu.get('name')} temp={gpu.get('temp_c')}C util={gpu.get('util_pct')}%"
    )
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    from lib.foundation_health import run_checks

    report = run_checks(include_stress=args.stress)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1
    for check in report["checks"]:
        mark = "OK" if check["ok"] else "FAIL"
        print(f"  [{mark}] {check['name']}: {check['detail']}")
    print(f"\nFoundation health: {'PASS' if report['ok'] else 'FAIL'}")
    return 0 if report["ok"] else 1


def cmd_piston(args: argparse.Namespace) -> int:
    from lib.governor_params import load_params, rollback_params
    from lib.governor_self_tune import evaluate_tune_window, read_history, tune_once
    from lib.cpu_governor import GovernedFleet
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

    action = args.piston_command
    if action == "status":
        if not PISTON_STATE_PATH.is_file():
            print("No piston state yet. Run: rid_main.py piston once")
            return 2
        if args.json:
            print(PISTON_STATE_PATH.read_text(encoding="utf-8"))
        else:
            data = _load_json(PISTON_STATE_PATH)
            print(
                f"[PISTON] beat={data.get('beat')} pkg_S_n={data.get('package_s_n')} "
                f"budget={data.get('package_budget_pct')}% halted={data.get('halted')}"
            )
            print(f"state: {PISTON_STATE_PATH}")
        return 0

    if action == "once":
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

    if action == "budget":
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

    if action == "govern":
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
                for core in state.cores:
                    if core.core in cores:
                        fleet.set_duty(core.core, ctl.core_budget(core.core))
                write_piston_state(state)
                if not args.no_journal:
                    journal_piston_event(state)
                print(format_status_line(state))
                if args.verbose:
                    for core in sorted(state.cores, key=lambda x: x.core):
                        if core.core in cores:
                            print(
                                f"    core {core.core}: T={core.temp_c:.1f}C S_n={core.s_n:.3f} "
                                f"load={core.load_pct:.0f}% -> budget "
                                f"{state.budget_by_core.get(str(core.core), 0):.0f}%"
                            )
                beat_n += 1
                if args.self_tune and tune_every > 0:
                    if pending_eval and beat_n >= tune_every // 2:
                        hist = read_history(500)
                        before = hist[hist_len_at_tune : hist_len_at_tune + tune_every // 2]
                        after = hist[-(tune_every // 2) :]
                        ev = evaluate_tune_window(before, after)
                        if ev.get("rollback"):
                            ok, previous = rollback_params()
                            if ok:
                                ctl.reload_params()
                                print(f"  ROLLBACK params v{previous.version} ({ev['verdict']})")
                        pending_eval = False
                    beats_since_tune += 1
                    if beats_since_tune >= tune_every:
                        hist_len_at_tune = len(read_history(500))
                        report = tune_once(dry_run=False)
                        ctl.reload_params()
                        beats_since_tune = 0
                        pending_eval = report.get("verdict") == "APPLIED"
                        changes = report.get("proposal", {}).get("changes", [])
                        if changes:
                            print(f"  SELF-TUNE v{report['params_after']['version']}: {changes}")
                        elif report.get("verdict") == "NO_CHANGE":
                            print(f"  SELF-TUNE: {report.get('proposal', {}).get('reason', 'no change')}")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            pass
        finally:
            fleet.stop()
        print("governor stopped (fleet throttled to 0).")
        return 0

    if action == "params":
        params = load_params()
        if args.json:
            print(json.dumps(params.to_dict(), indent=2))
        else:
            print(f"governor params v{params.version} source={params.source}")
            print(json.dumps(params.to_dict(), indent=2))
        return 0

    if action == "tune":
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
        metrics = report.get("metrics", {})
        if metrics.get("verdict") == "OK":
            print(
                f"  n={metrics['n']} dormancy={metrics['dormancy_rate']:.2%} "
                f"budget_std={metrics['budget_std']:.1f} max_T={metrics['max_temp_c']:.1f}C"
            )
        return 0

    if action == "rollback":
        ok, params = rollback_params()
        if ok:
            print(f"Rolled back governor params to version {params.version}")
            print(json.dumps(params.to_dict(), indent=2))
            return 0
        print("No backup to roll back to.")
        return 2

    if action == "hardware":
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
        print(
            f"[HARDWARE] logical={cap['logical_cores']} physical={cap['physical_cores']} "
            f"per_core_temp={cap['per_core_temp']} package_temp={cap['package_temp']}"
        )
        print(f"  governing {ctl.n_cores} cores as {len(ctl.pairs)} pairs, thermal_mode={ctl.thermal_mode}")
        if ctl.thermal_mode != "real":
            print("  NOTE: no thermal sensor detected -> degraded load-only headroom.")
        if is_halted():
            print("  CONTAINMENT ACTIVE: layer is HALTED. Run: rid_main.py piston resume")
        return 0

    if action == "halt":
        path = halt(reason=args.reason)
        print(f"HALTED ({args.reason}). Flag: {path}")
        print("All CPU budgets forced to floor until resumed.")
        return 0

    if action == "resume":
        if resume():
            print("Containment lifted. Governor will resume S_n-based budgets.")
        else:
            print("Not halted (no flag present).")
        return 0

    print(f"unknown piston command: {action}", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rid_main",
        description="Viv RID foundation — telemetry, stress, benchmark (Vidi).",
    )
    p.add_argument("--version", action="version", version=f"rid_main {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    rs = sub.add_parser("status", help="Read-only RID pillar status and canonical captures")
    rs.add_argument("--json", action="store_true")
    rs.set_defaults(func=cmd_status)

    hl = sub.add_parser("health", help="Foundation bedrock health (venv, plant, piston)")
    hl.add_argument("--json", action="store_true")
    hl.add_argument("--stress", action="store_true", help="Include quick 4-core stress probe")
    hl.set_defaults(func=cmd_health)

    ps = sub.add_parser("piston", help="RID piston-core controls")
    ps_sub = ps.add_subparsers(dest="piston_command", required=True)

    pst = ps_sub.add_parser("status", help="Show last piston_state.json")
    pst.add_argument("--json", action="store_true")
    pst.set_defaults(func=cmd_piston)

    po = ps_sub.add_parser("once", help="One piston tick")
    po.add_argument("--json", action="store_true")
    po.add_argument("--no-journal", action="store_true")
    po.set_defaults(func=cmd_piston)

    pb = ps_sub.add_parser("budget", help="Show S_n -> allowed CPU percent mapping")
    pb.add_argument("--json", action="store_true")
    pb.set_defaults(func=cmd_piston)

    pg = ps_sub.add_parser("govern", help="Actively govern managed CPU: duty = S_n budget")
    pg.add_argument("--seconds", type=float, default=0.0, help="0 = run until Ctrl+C")
    pg.add_argument("--interval", type=float, default=1.0)
    pg.add_argument("--all-cores", action="store_true", help="Govern all cores, not just pairs")
    pg.add_argument("--verbose", action="store_true", help="Per-core budget lines")
    pg.add_argument("--no-journal", action="store_true")
    pg.add_argument("--self-tune", action="store_true", help="Self-modify governor params from history")
    pg.add_argument("--tune-every", type=int, default=30, help="Beats between self-tune cycles")
    pg.set_defaults(func=cmd_piston)

    pp = ps_sub.add_parser("params", help="Show active governor parameters")
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(func=cmd_piston)

    pt = ps_sub.add_parser("tune", help="Run one governor self-tune cycle from history")
    pt.add_argument("--dry-run", action="store_true")
    pt.add_argument("--json", action="store_true")
    pt.set_defaults(func=cmd_piston)

    ps_sub.add_parser("rollback", help="Rollback governor params to last backup").set_defaults(func=cmd_piston)

    phw = ps_sub.add_parser("hardware", help="Show detected hardware and pairing")
    phw.add_argument("--json", action="store_true")
    phw.set_defaults(func=cmd_piston)

    pht = ps_sub.add_parser("halt", help="Containment: force piston layer safe")
    pht.add_argument("--reason", default="operator")
    pht.set_defaults(func=cmd_piston)

    ps_sub.add_parser("resume", help="Lift piston containment halt").set_defaults(func=cmd_piston)

    w = sub.add_parser("watch", help="Live 1 Hz S_n console monitor")
    w.add_argument("--interval", type=float, default=1.0)
    w.set_defaults(func=cmd_watch)

    mon = sub.add_parser(
        "monitor",
        help="Architect plant monitor: per-core load/temp + Corsair + NVML + Master RID (JSONL)",
    )
    mon.add_argument("--interval", type=float, default=1.0)
    mon.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Finite run (default: until Ctrl+C)",
    )
    mon.add_argument("--cores", type=int, default=None, help="Logical cores to show (default: all)")
    mon.add_argument(
        "--jsonl",
        nargs="?",
        const="",
        default="",
        help="JSONL path (omit value or flag alone → artifacts/rid/architect_monitor.jsonl)",
    )
    mon.add_argument("--no-clear", action="store_true", help="Do not ANSI-clear between frames")
    mon.add_argument("--no-publish", action="store_true", help="Do not write master_rid.json")
    mon.set_defaults(func=cmd_monitor)

    lg = sub.add_parser("log", help="CSV telemetry without CPU stress")
    lg.add_argument("--interval", type=float, default=1.0)
    lg.add_argument("--csv", default="", help="Output CSV (default: artifacts/rid/telemetry.csv)")
    lg.set_defaults(func=cmd_log)

    st = sub.add_parser("stress", help="Full-core stress + CSV telemetry")
    st.add_argument("--interval", type=float, default=1.0)
    st.add_argument("--csv", default="", help="Output CSV (default: artifacts/rid/stress_test.csv)")
    st.add_argument("--cores", type=int, default=None)
    st.set_defaults(func=cmd_stress)

    sm = sub.add_parser("sample", help="Single S_n sample (JSON for heart/automation hooks)")
    sm.add_argument("--json", default="", help="Write sample JSON to path")
    sm.set_defaults(func=cmd_sample)

    fd = sub.add_parser("feed", help="1 Hz live_sample.json for automation / heart")
    fd.add_argument("--interval", type=float, default=1.0)
    fd.add_argument("--json", default="", help="Output JSON path (default: artifacts/rid/live_sample.json)")
    fd.set_defaults(func=cmd_feed)

    bm = sub.add_parser("benchmark", help="RID v1.2 stability-coupled efficiency test")
    bm.add_argument("--seconds", type=float, default=None)
    bm.add_argument("--rounds", type=int, default=None)
    bm.add_argument("--settle", type=float, default=None)
    bm.add_argument("--saboteur-mem", type=int, default=None, help="Chaos memory MB (PC default 2048)")
    bm.add_argument("--smoke", action="store_true", help="Quick desktop tuning benchmark")
    bm.add_argument("--interactive", action="store_true")
    bm.set_defaults(func=cmd_benchmark)

    cp = sub.add_parser("compare", help="Compare latest PC benchmark vs phone S24 baseline")
    cp.add_argument("--phone", default="", help="Phone baseline JSON")
    cp.add_argument("--pc", default="", help="PC run JSON (default: latest artifact)")
    cp.add_argument("--json", default="", help="Output report JSON")
    cp.add_argument("--md", default="", help="Output report markdown")
    cp.add_argument("--quiet", action="store_true")
    cp.set_defaults(func=cmd_compare)

    stb = sub.add_parser("stability", help="PC port of Phone/ridv14.py — dual-sensor stability test")
    stb.add_argument("--seconds", type=float, default=120.0)
    stb.add_argument("--sample-interval", type=float, default=1.0)
    stb.add_argument("--interval", type=float, default=2.0)
    stb.add_argument("--stress", action="store_true")
    stb.add_argument("--stress-mode", default="blast", choices=["blast", "piston"])
    stb.add_argument("--cores", type=int, default=None)
    stb.add_argument("--pair", default="cpu_coolant", choices=["cpu_gpu", "cpu_coolant", "core_spread"])
    stb.add_argument("--csv", default="")
    stb.add_argument("--log-all", action="store_true")
    stb.set_defaults(func=cmd_stability)

    pl = sub.add_parser("plot", help="PC port of Phone/ridplot.py — 4-panel triad chart")
    pl.add_argument("--csv", default="", help="Plot existing CSV")
    pl.add_argument("--seconds", type=float, default=120.0)
    pl.add_argument("--interval", type=float, default=1.0)
    pl.add_argument("--stress", action="store_true")
    pl.add_argument("--pair", default="cpu_coolant", choices=["cpu_gpu", "cpu_coolant", "core_spread"])
    pl.add_argument("--out", default="")
    pl.add_argument("--log-all", action="store_true")
    pl.add_argument("--master", action="store_true", help="Plot Master S_n CSV (coupled/core_spread capture schema)")
    pl.add_argument("--master-kind", default="coupled", choices=["coupled", "core_spread"])
    pl.set_defaults(func=cmd_plot)

    cb = sub.add_parser("cube", help="PC port of Phone/ridtessv1.py — 3D S_n cube")
    cb.add_argument("--seconds", type=float, default=120.0)
    cb.set_defaults(func=cmd_cube)

    tr = sub.add_parser("trajectory", help="3D LTP×RLE×time from collapse log")
    tr.add_argument("--log", default="")
    tr.add_argument("--out", default="")
    tr.set_defaults(func=cmd_trajectory)

    bh = sub.add_parser("black-hole", help="RID black-hole plant science commands")
    bh_sub = bh.add_subparsers(dest="black_hole_command", required=True)

    bho = bh_sub.add_parser("once", help="Single CPU black-hole sample")
    bho.add_argument("--json", action="store_true")
    bho.add_argument("--phone-compat", action="store_true")
    bho.set_defaults(func=cmd_black_hole)

    bhw = bh_sub.add_parser("watch", help="Watch CPU black-hole telemetry without stress")
    bhw.add_argument("--interval", type=float, default=1.0)
    bhw.add_argument("--log", action="store_true")
    bhw.add_argument("--phone-compat", action="store_true")
    bhw.add_argument("--extreme", action="store_true")
    bhw.add_argument("--mass", type=float, default=None)
    bhw.add_argument("--density", type=float, default=None)
    bhw.add_argument("--energy", type=float, default=None)
    bhw.set_defaults(func=cmd_black_hole)

    bhc = bh_sub.add_parser("collapse", help="CPU stress + black-hole event monitor")
    bhc.add_argument("--interval", type=float, default=1.0)
    bhc.add_argument("--seconds", type=float, default=0.0)
    bhc.add_argument("--warmup", type=float, default=3.0)
    bhc.add_argument("--cores", type=int, default=0)
    bhc.add_argument("--extreme", action="store_true")
    bhc.add_argument("--stop-on-latch", action="store_true")
    bhc.add_argument("--phone-compat", action="store_true")
    bhc.add_argument("--mass", type=float, default=None)
    bhc.add_argument("--density", type=float, default=None)
    bhc.add_argument("--energy", type=float, default=None)
    bhc.set_defaults(func=cmd_black_hole)

    bhgo = bh_sub.add_parser("gpu-once", help="Single GPU black-hole sample")
    bhgo.add_argument("--gpu", type=int, default=0)
    bhgo.add_argument("--json", action="store_true")
    bhgo.set_defaults(func=cmd_black_hole)

    bhgw = bh_sub.add_parser("gpu-watch", help="Watch GPU black-hole telemetry without stress")
    bhgw.add_argument("--gpu", type=int, default=0)
    bhgw.add_argument("--interval", type=float, default=1.0)
    bhgw.add_argument("--log", action="store_true")
    bhgw.add_argument("--extreme", action="store_true")
    bhgw.add_argument("--mass", type=float, default=None)
    bhgw.add_argument("--density", type=float, default=None)
    bhgw.add_argument("--energy", type=float, default=None)
    bhgw.set_defaults(func=cmd_black_hole)

    bhgc = bh_sub.add_parser("gpu-collapse", help="GPU stress + black-hole event monitor")
    bhgc.add_argument("--gpu", type=int, default=0)
    bhgc.add_argument("--interval", type=float, default=1.0)
    bhgc.add_argument("--seconds", type=float, default=0.0)
    bhgc.add_argument("--warmup", type=float, default=3.0)
    bhgc.add_argument("--extreme", action="store_true")
    bhgc.add_argument("--stop-on-latch", action="store_true")
    bhgc.add_argument("--mass", type=float, default=None)
    bhgc.add_argument("--density", type=float, default=None)
    bhgc.add_argument("--energy", type=float, default=None)
    bhgc.add_argument("--gpu-stress", default="extreme", choices=["normal", "extreme", "rtx"])
    bhgc.set_defaults(func=cmd_black_hole)

    bhcp = bh_sub.add_parser("coupled-collapse", help="CPU+GPU coupled plant stress")
    bhcp.add_argument("--gpu", type=int, default=0)
    bhcp.add_argument("--interval", type=float, default=1.0)
    bhcp.add_argument("--seconds", type=float, default=0.0)
    bhcp.add_argument("--warmup", type=float, default=4.0)
    bhcp.add_argument("--cores", type=int, default=0)
    bhcp.add_argument("--extreme", action="store_true")
    bhcp.add_argument("--gpu-stress", default="rtx", choices=["normal", "extreme", "rtx"])
    bhcp.add_argument("--stop-on-dual", action="store_true")
    bhcp.add_argument("--stop-on-any", action="store_true")
    bhcp.add_argument("--phone-compat", action="store_true")
    bhcp.set_defaults(func=cmd_black_hole)

    bhcr = bh_sub.add_parser("coupled-run", help="Coupled RTX stress + trajectory + cpu_gpu triad reports")
    bhcr.add_argument("--seconds", type=float, default=120.0)
    bhcr.add_argument("--interval", type=float, default=1.0)
    bhcr.add_argument("--gpu-stress", default="rtx", choices=["normal", "extreme", "rtx"])
    bhcr.add_argument("--cores", type=int, default=0)
    bhcr.add_argument("--warmup", type=float, default=4.0)
    bhcr.set_defaults(func=cmd_black_hole)

    bhco = bh_sub.add_parser("coupled-once", help="Single coupled CPU+GPU sample")
    bhco.add_argument("--gpu", type=int, default=0)
    bhco.add_argument("--json", action="store_true")
    bhco.add_argument("--extreme", action="store_true")
    bhco.add_argument("--phone-compat", action="store_true")
    bhco.set_defaults(func=cmd_black_hole)

    gt = bh_sub.add_parser("gpu-triad", help="GPU temp/power/VRAM triad plot")
    gt.add_argument("--seconds", type=float, default=120.0)
    gt.add_argument("--pair", default="temp_power", choices=["temp_power", "temp_vram", "temp_clock"])
    gt.add_argument("--gpu-stress", default="rtx", choices=["normal", "extreme", "rtx"])
    gt.set_defaults(func=cmd_black_hole)

    vis = bh_sub.add_parser("visual", help="Black-hole 3D visual")
    vis.add_argument("--seconds", type=float, default=180.0)
    vis.add_argument("--gpu-stress", default="rtx", choices=["normal", "extreme", "rtx"])
    vis.add_argument("--windowed", action="store_true")
    vis.set_defaults(func=cmd_black_hole)

    cap = sub.add_parser("capture", help="Unified RID plant proof capture")
    cap.add_argument("--kind", required=True, choices=["coolant", "coupled", "core_spread"])
    cap.add_argument("--seconds", type=float, default=120.0)
    cap.add_argument("--sample-interval", type=float, default=1.0)
    cap.add_argument("--interval", type=float, default=2.0, help="Console print interval for coolant captures")
    cap.add_argument("--cores", type=int, default=None)
    cap.add_argument("--gpu-stress", default="rtx", choices=["normal", "extreme", "rtx"])
    cap.add_argument("--csv", default="")
    cap.add_argument("--warmup", type=float, default=4.0)
    cap.add_argument("--no-piston-bg", action="store_true")
    cap.add_argument("--piston-interval", type=float, default=1.0)
    cap.add_argument("--log-all", action="store_true", help="Coolant captures: log every poll")
    cap.add_argument("--no-publish", action="store_true", help="Do not update plant authority bridge")
    cap.set_defaults(func=cmd_capture)

    cc = sub.add_parser(
        "coupled-capture",
        help="120s CPU+GPU stress with per-subsystem Master S_n logging",
    )
    cc.add_argument("--seconds", type=float, default=120.0)
    cc.add_argument("--sample-interval", type=float, default=1.0)
    cc.add_argument("--cores", type=int, default=None)
    cc.add_argument("--gpu-stress", default="rtx", choices=["normal", "extreme", "rtx"])
    cc.add_argument("--csv", default="")
    cc.add_argument("--warmup", type=float, default=4.0)
    cc.add_argument("--no-piston-bg", action="store_true", help="Disable background piston thread")
    cc.add_argument("--piston-interval", type=float, default=1.0, help="Background piston Hz period")
    cc.set_defaults(func=cmd_coupled_capture)

    cs = sub.add_parser(
        "core-spread-capture",
        help="120s core_spread sensor + Master S_n (CPU stress, background piston)",
    )
    cs.add_argument("--seconds", type=float, default=120.0)
    cs.add_argument("--sample-interval", type=float, default=1.0)
    cs.add_argument("--cores", type=int, default=None)
    cs.add_argument("--csv", default="")
    cs.add_argument("--warmup", type=float, default=4.0)
    cs.add_argument("--no-piston-bg", action="store_true")
    cs.add_argument("--piston-interval", type=float, default=1.0)
    cs.set_defaults(func=cmd_core_spread_capture)

    return p


def cmd_capture(args: argparse.Namespace) -> int:
    """Unified Canonical Alpha RID capture entry."""
    if args.kind == "coolant":
        import rid_stability_main as m

        csv = Path(args.csv) if args.csv else RID_ARTIFACTS / f"stability_pc_{int(args.seconds)}s_alpha.csv"
        argv = [
            "--seconds", str(args.seconds),
            "--sample-interval", str(args.sample_interval),
            "--interval", str(args.interval),
            "--stress",
            "--stress-mode", "blast",
            "--pair", "cpu_coolant",
            "--csv", str(csv),
        ]
        if args.cores:
            argv.extend(["--cores", str(args.cores)])
        if args.log_all:
            argv.append("--log-all")
        if args.no_publish:
            argv.append("--no-publish")
        return m.main(argv)

    if args.kind == "coupled":
        from lib.plant_master_capture import run_coupled_rid_capture

        csv = Path(args.csv) if args.csv else RID_ARTIFACTS / f"coupled_master_{int(args.seconds)}s_alpha.csv"
        run_coupled_rid_capture(
            duration=args.seconds,
            sample_interval=args.sample_interval,
            cores=args.cores,
            gpu_stress=args.gpu_stress,
            csv_path=csv,
            warmup=args.warmup,
            piston_background=not args.no_piston_bg,
            piston_interval=args.piston_interval,
            publish=not args.no_publish,
        )
        return 0

    if args.kind == "core_spread":
        from lib.plant_master_capture import run_core_spread_capture

        csv = Path(args.csv) if args.csv else RID_ARTIFACTS / f"core_spread_master_{int(args.seconds)}s_alpha.csv"
        run_core_spread_capture(
            duration=args.seconds,
            sample_interval=args.sample_interval,
            cores=args.cores,
            csv_path=csv,
            warmup=args.warmup,
            piston_background=not args.no_piston_bg,
            piston_interval=args.piston_interval,
            publish=not args.no_publish,
        )
        return 0

    print(f"unknown capture kind: {args.kind}", file=sys.stderr)
    return 2


def _plot_master_csv(csv_path: Path, out_png: Path) -> bool:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — pip install matplotlib", file=sys.stderr)
        return False

    rows: list[dict[str, str]] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print(f"no rows in {csv_path}", file=sys.stderr)
        return False
    required = {
        "t_s",
        "master_s_n",
        "cpu_automaton_s_n",
        "piston_s_n",
        "gpu_s_n",
        "coolant_loop_s_n",
    }
    missing = sorted(required - set(rows[0]))
    if missing:
        print(f"not a Master S_n CSV; missing {missing}", file=sys.stderr)
        return False

    t = [float(r["t_s"]) for r in rows]
    series = {
        "Master S_n": [float(r["master_s_n"]) for r in rows],
        "cpu_automaton": [float(r["cpu_automaton_s_n"]) for r in rows],
        "piston": [float(r["piston_s_n"]) for r in rows],
        "gpu": [float(r["gpu_s_n"]) for r in rows],
        "coolant_loop": [float(r["coolant_loop_s_n"]) for r in rows],
    }
    cpu_load = [float(r.get("cpu_load_pct") or 0) for r in rows]
    gpu_util = [float(r.get("gpu_util_pct") or 0) for r in rows]

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    step = dict(drawstyle="steps-post")
    for label, vals in series.items():
        width = 2.0 if label == "Master S_n" else 1.0
        axes[0].plot(t, vals, label=label, linewidth=width, **step)
    axes[0].axhline(DORMANCY_THRESHOLD, color="gray", linewidth=0.8, linestyle="--", label="dormancy 0.45")
    axes[0].set_ylabel("S_n (0-1)")
    axes[0].set_ylim(-0.02, 1.02)
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc="upper right")

    axes[1].plot(t, cpu_load, label="CPU load %", **step)
    if any(gpu_util):
        axes[1].plot(t, gpu_util, label="GPU util %", **step)
    axes[1].set_ylabel("Load / util %")
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylim(-2, 102)
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc="upper right")

    fig.suptitle(f"RID Master S_n — {csv_path.name}")
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"wrote {out_png}")
    return True


def cmd_black_hole(args: argparse.Namespace) -> int:
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
        sample_once as bh_sample_once,
        stop_stressors,
        write_state,
    )
    from lib.coupled_black_hole import (
        COUPLED_ARTIFACTS,
        CoupledEngine,
        append_coupled_log,
        print_coupled_line,
        write_coupled_state,
    )
    from lib.coupled_report import generate_coupled_reports
    from lib.gpu_black_hole_engine import (
        GPU_BH_ARTIFACTS,
        GpuChannelEngine,
        append_gpu_log,
        print_gpu_line,
        sample_gpu_once,
        write_gpu_state,
    )
    from lib.gpu_stress import launch_gpu_stress, stop_gpu_stress

    cpu_extreme = {"mass": 0.65, "density": 0.40, "energy": 0.75}
    gpu_extreme = {"mass": 0.60, "density": 0.45, "energy": 0.82}

    def cpu_thresholds() -> dict[str, float]:
        if getattr(args, "extreme", False):
            return dict(cpu_extreme)
        return {
            "mass": args.mass if getattr(args, "mass", None) is not None else MASS_CRITICAL,
            "density": args.density if getattr(args, "density", None) is not None else DENSITY_CRITICAL,
            "energy": args.energy if getattr(args, "energy", None) is not None else ENERGY_CRITICAL,
        }

    def gpu_thresholds() -> dict[str, float]:
        if getattr(args, "extreme", False):
            return dict(gpu_extreme)
        from lib.gpu_black_hole_engine import DENSITY_CRITICAL as GDENSITY
        from lib.gpu_black_hole_engine import ENERGY_CRITICAL as GENERGY
        from lib.gpu_black_hole_engine import MASS_CRITICAL as GMASS

        return {
            "mass": args.mass if getattr(args, "mass", None) is not None else GMASS,
            "density": args.density if getattr(args, "density", None) is not None else GDENSITY,
            "energy": args.energy if getattr(args, "energy", None) is not None else GENERGY,
        }

    def cpu_check(engine: ChannelEngine, sample, thresholds: dict[str, float]) -> None:
        if engine.collapsed(
            sample.mass,
            sample.density,
            sample.energy,
            phone_compat=getattr(args, "phone_compat", False),
            mass_thr=thresholds["mass"],
            density_thr=thresholds["density"],
            energy_thr=thresholds["energy"],
        ):
            sample.collapsed = True
            sample.latched = engine.latched

    def gpu_check(engine: GpuChannelEngine, sample, thresholds: dict[str, float]) -> None:
        if engine.collapsed(
            sample.mass,
            sample.density,
            sample.energy,
            mass_thr=thresholds["mass"],
            density_thr=thresholds["density"],
            energy_thr=thresholds["energy"],
        ):
            sample.collapsed = True
            sample.latched = engine.latched

    command = args.black_hole_command

    if command == "once":
        engine = ChannelEngine()
        sample = bh_sample_once(engine, phone_compat=args.phone_compat)
        write_state(sample)
        print(json.dumps(sample.to_dict(), indent=2) if args.json else format_line(sample), flush=True)
        return 0

    if command == "watch":
        engine = ChannelEngine()
        thresholds = cpu_thresholds()
        print(
            f"Black hole watch @ {args.interval}s | "
            f"Mass>{thresholds['mass']} Dens>{thresholds['density']} En<{thresholds['energy']}"
        )
        try:
            while True:
                sample = bh_sample_once(engine, phone_compat=args.phone_compat)
                cpu_check(engine, sample, thresholds)
                write_state(sample)
                if args.log:
                    append_log(sample)
                print(format_line(sample), flush=True)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nstopped.")
            return 0

    if command == "collapse":
        thresholds = cpu_thresholds()
        procs = launch_stressors(args.cores if args.cores > 0 else None)
        print("=== BLACK HOLE COLLAPSE SIMULATOR (PC) ===")
        print(f"Mass > {thresholds['mass']}  |  Density > {thresholds['density']}  |  Energy < {thresholds['energy']}")
        print(f"Pi storm on {len(procs)} cores + memory apocalypse. Ctrl+C to stop.\n")
        time.sleep(args.warmup)
        engine = ChannelEngine()
        t0 = time.time()
        duration = float(args.seconds)
        try:
            while duration <= 0 or (time.time() - t0 < duration):
                sample = bh_sample_once(engine, phone_compat=args.phone_compat)
                cpu_check(engine, sample, thresholds)
                write_state(sample)
                append_log(sample)
                print_line(sample)
                if sample.latched and args.stop_on_latch:
                    print("Event horizon latched. Stressors stopping.", flush=True)
                    break
                time.sleep(args.interval)
        except KeyboardInterrupt:
            pass
        finally:
            stop_stressors(procs)
        print(f"state: {BH_ARTIFACTS / 'collapse_state.json'}")
        return 0

    if command == "gpu-once":
        engine = GpuChannelEngine()
        sample = sample_gpu_once(engine, index=args.gpu)
        write_gpu_state(sample)
        if args.json:
            print(json.dumps(sample.to_dict(), indent=2))
        else:
            print_gpu_line(sample)
        return 0

    if command == "gpu-watch":
        engine = GpuChannelEngine()
        thresholds = gpu_thresholds()
        print(
            f"GPU black hole watch @ {args.interval}s | "
            f"Mass>{thresholds['mass']} Dens>{thresholds['density']} En<{thresholds['energy']} (air-cooled plant)"
        )
        try:
            while True:
                sample = sample_gpu_once(engine, index=args.gpu)
                gpu_check(engine, sample, thresholds)
                write_gpu_state(sample)
                if args.log:
                    append_gpu_log(sample)
                print_gpu_line(sample)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nstopped.")
            return 0

    if command == "gpu-collapse":
        thresholds = gpu_thresholds()
        mode = getattr(args, "gpu_stress", "extreme") or "extreme"
        procs = launch_gpu_stress(mode)
        print(f"=== GPU BLACK HOLE COLLAPSE ({mode.upper()} OpenCL on RTX) ===")
        print(f"Mass > {thresholds['mass']}  |  Density > {thresholds['density']}  |  Energy < {thresholds['energy']}")
        print("OpenCL matmul burn + VRAM apocalypse on NVIDIA GPU.\n")
        time.sleep(args.warmup)
        engine = GpuChannelEngine()
        t0 = time.time()
        duration = float(args.seconds)
        try:
            while duration <= 0 or (time.time() - t0 < duration):
                sample = sample_gpu_once(engine, index=args.gpu)
                gpu_check(engine, sample, thresholds)
                write_gpu_state(sample)
                append_gpu_log(sample)
                print_gpu_line(sample)
                if sample.latched and args.stop_on_latch:
                    print("GPU event horizon latched. Stressors stopping.", flush=True)
                    break
                time.sleep(args.interval)
        except KeyboardInterrupt:
            pass
        finally:
            stop_gpu_stress(procs)
        print(f"state: {GPU_BH_ARTIFACTS / 'collapse_state.json'}")
        return 0

    if command == "coupled-once":
        engine = CoupledEngine()
        sample = engine.tick(
            cpu_thr=cpu_thresholds(),
            gpu_thr=gpu_thresholds(),
            phone_compat=args.phone_compat,
            gpu_index=args.gpu,
        )
        write_coupled_state(sample)
        if args.json:
            print(json.dumps(sample.to_dict(), indent=2))
        else:
            print_coupled_line(sample)
        return 0

    if command == "coupled-collapse":
        cpu_thr = cpu_thresholds()
        gpu_thr = gpu_thresholds()
        mode = getattr(args, "gpu_stress", "rtx") or "rtx"
        cpu_procs = launch_stressors(args.cores if args.cores > 0 else None)
        gpu_procs = launch_gpu_stress(mode)
        print(f"=== COUPLED BLACK HOLE (CPU liquid + GPU {mode.upper()}) ===")
        print(f"CPU: Mass>{cpu_thr['mass']} Dens>{cpu_thr['density']} En<{cpu_thr['energy']}")
        print(f"GPU: Mass>{gpu_thr['mass']} Dens>{gpu_thr['density']} En<{gpu_thr['energy']}")
        print("Pi storm + RAM apocalypse + OpenCL GPU burn. Ctrl+C to stop.\n")
        time.sleep(args.warmup)
        engine = CoupledEngine()
        t0 = time.time()
        duration = float(args.seconds)
        last_regime = ""
        last_sample = None
        try:
            while duration <= 0 or (time.time() - t0 < duration):
                sample = engine.tick(
                    cpu_thr=cpu_thr,
                    gpu_thr=gpu_thr,
                    phone_compat=args.phone_compat,
                    gpu_index=args.gpu,
                )
                last_sample = sample
                write_coupled_state(sample)
                append_coupled_log(sample)
                print_coupled_line(sample)
                if sample.regime != last_regime:
                    print(f"  >> regime: {sample.regime}", flush=True)
                    last_regime = sample.regime
                if args.stop_on_dual and sample.dual_horizon:
                    print("DUAL EVENT HORIZON latched. Stressors stopping.", flush=True)
                    break
                if args.stop_on_any and (sample.cpu_horizon or sample.gpu_horizon):
                    print(f"Horizon crossed ({sample.regime}). Stressors stopping.", flush=True)
                    break
                time.sleep(args.interval)
        except KeyboardInterrupt:
            pass
        finally:
            stop_stressors(cpu_procs)
            stop_gpu_stress(gpu_procs)
        print(f"state: {COUPLED_ARTIFACTS / 'collapse_state.json'}")
        if last_sample and (engine.cpu_eng.latched or engine.gpu_eng.latched):
            print(
                f"horizons: cpu={'yes' if engine.cpu_eng.latched else 'no'} "
                f"gpu={'yes' if engine.gpu_eng.latched else 'no'} "
                f"first={last_sample.first_plant} lag={last_sample.horizon_lag_s}s"
            )
        return 0

    if command == "coupled-run":
        args.extreme = True
        args.stop_on_dual = getattr(args, "stop_on_dual", False)
        args.stop_on_any = getattr(args, "stop_on_any", False)
        args.phone_compat = getattr(args, "phone_compat", False)
        args.gpu = getattr(args, "gpu", 0)
        args.seconds = float(args.seconds) if args.seconds else 120.0
        print(f"=== COUPLED RUN {args.seconds:.0f}s - stress, log, plot ===\n")
        rc = cmd_black_hole(argparse.Namespace(**{**vars(args), "black_hole_command": "coupled-collapse"}))
        if rc != 0:
            return rc
        report = generate_coupled_reports()
        print("\n--- Coupled report ---")
        print(json.dumps(report, indent=2))
        return 0

    if command == "gpu-triad":
        import gpu_triad_main as gpu_triad

        argv = ["--seconds", str(args.seconds), "--pair", args.pair, "--stress", args.gpu_stress]
        return int(gpu_triad.main(argv))

    if command == "visual":
        import black_hole_visual_main as visual

        argv = ["--seconds", str(args.seconds), "--gpu-stress", args.gpu_stress]
        if args.windowed:
            argv.append("--windowed")
        return int(visual.main(argv))

    print(f"unknown black-hole command: {command}", file=sys.stderr)
    return 2


def cmd_coupled_capture(args: argparse.Namespace) -> int:
    print(
        "[DEPRECATED] use: rid_main.py capture --kind coupled",
        file=sys.stderr,
    )
    return cmd_capture(
        argparse.Namespace(
            kind="coupled",
            seconds=args.seconds,
            sample_interval=args.sample_interval,
            interval=2.0,
            cores=args.cores,
            gpu_stress=args.gpu_stress,
            csv=args.csv,
            warmup=args.warmup,
            no_piston_bg=args.no_piston_bg,
            piston_interval=args.piston_interval,
            log_all=False,
            no_publish=False,
        )
    )


def cmd_core_spread_capture(args: argparse.Namespace) -> int:
    print(
        "[DEPRECATED] use: rid_main.py capture --kind core_spread",
        file=sys.stderr,
    )
    return cmd_capture(
        argparse.Namespace(
            kind="core_spread",
            seconds=args.seconds,
            sample_interval=args.sample_interval,
            interval=2.0,
            cores=args.cores,
            gpu_stress="rtx",
            csv=args.csv,
            warmup=args.warmup,
            no_piston_bg=args.no_piston_bg,
            piston_interval=args.piston_interval,
            log_all=False,
            no_publish=False,
        )
    )


def cmd_stability(args: argparse.Namespace) -> int:
    import rid_stability_main as m

    argv = ["stability"]
    if args.seconds:
        argv.extend(["--seconds", str(args.seconds)])
    if getattr(args, "sample_interval", None):
        argv.extend(["--sample-interval", str(args.sample_interval)])
    if args.interval:
        argv.extend(["--interval", str(args.interval)])
    if args.stress:
        argv.append("--stress")
    if getattr(args, "stress_mode", None):
        argv.extend(["--stress-mode", args.stress_mode])
    if args.cores:
        argv.extend(["--cores", str(args.cores)])
    if args.pair:
        argv.extend(["--pair", args.pair])
    if args.csv:
        argv.extend(["--csv", args.csv])
    if getattr(args, "log_all", False):
        argv.append("--log-all")
    return m.main(argv[1:])


def cmd_plot(args: argparse.Namespace) -> int:
    if getattr(args, "master", False):
        kind = getattr(args, "master_kind", "coupled")
        spec = CANONICAL_CAPTURES[kind]
        csv_path = Path(args.csv) if args.csv else Path(spec["csv"])
        out = Path(args.out) if args.out else RID_ARTIFACTS / f"{csv_path.stem}_master_plot.png"
        ok = _plot_master_csv(csv_path, out)
        return 0 if ok else 1

    import rid_plot_main as m

    argv = ["plot"]
    if args.csv:
        argv.extend(["--csv", args.csv])
    if args.seconds:
        argv.extend(["--seconds", str(args.seconds)])
    if getattr(args, "interval", None):
        argv.extend(["--interval", str(args.interval)])
    if args.stress:
        argv.append("--stress")
    if getattr(args, "pair", None):
        argv.extend(["--pair", args.pair])
    if args.out:
        argv.extend(["--out", args.out])
    if getattr(args, "log_all", False):
        argv.append("--log-all")
    return m.main(argv[1:])


def cmd_cube(args: argparse.Namespace) -> int:
    import rid_cube_main as m

    return m.main(["--seconds", str(args.seconds)])


def cmd_trajectory(args: argparse.Namespace) -> int:
    from lib.rid_trajectory_plot import main as traj_main
    from lib.paths import AUTO_ARTIFACTS, RID_ARTIFACTS
    import json

    log = Path(args.log) if args.log else AUTO_ARTIFACTS / "black_hole" / "coupled" / "collapse_log.jsonl"
    out = Path(args.out) if args.out else RID_ARTIFACTS / "trajectory"
    print(json.dumps(traj_main(log, out), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    import multiprocessing as mp

    mp.freeze_support()
    if mp.current_process().name == "MainProcess":
        raise SystemExit(main())
