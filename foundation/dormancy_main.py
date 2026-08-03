#!/usr/bin/env python3
"""Benchmark + calibrate Master S_n dormancy threshold (Law 5 / ACTIVE gate).

Default is propose-only. --apply writes shared JSON that Rust Law 5 reads.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.dormancy_config import (  # noqa: E402
    BENCHMARK_LATEST,
    THRESHOLD_PATH,
    live_benchmark,
    load_threshold,
    write_threshold,
)


def cmd_status(_: argparse.Namespace) -> int:
    thr = load_threshold()
    out = {
        "ok": True,
        "dormancy_threshold": thr,
        "threshold_path": str(THRESHOLD_PATH).replace("\\", "/"),
        "file_exists": THRESHOLD_PATH.is_file(),
    }
    try:
        from lib.security_membrane import dormancy_threshold as rust_thr

        out["rust_dormancy_threshold"] = float(rust_thr())
        out["rust_matches_file"] = abs(float(rust_thr()) - thr) < 1e-6
    except Exception as exc:  # noqa: BLE001
        out["rust_error"] = str(exc)
    print(json.dumps(out, indent=2))
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    report = live_benchmark(seconds=args.seconds, interval=args.interval)
    print(json.dumps(report, indent=2))
    print(f"wrote: {BENCHMARK_LATEST}", file=sys.stderr)
    if args.apply:
        return cmd_apply_from_report(report, dry_run=False)
    return 0


def cmd_apply_from_report(report: dict, *, dry_run: bool) -> int:
    proposed = float(report["proposed_threshold"])
    if dry_run:
        print(json.dumps({"dry_run": True, "would_write": proposed}, indent=2))
        return 0
    payload = write_threshold(
        proposed,
        source="dormancy_benchmark",
        evidence={
            "live": report.get("live"),
            "history": report.get("history"),
            "rationale": report.get("rationale"),
        },
    )
    print(json.dumps(payload, indent=2))
    print(
        "NOTE: Restart Python processes / ensure security_core.pyd 0.2.4+ so Law 5 re-reads the file.",
        file=sys.stderr,
    )
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    if args.from_benchmark:
        if not BENCHMARK_LATEST.is_file():
            print("no benchmark file — run: dormancy_main.py benchmark", file=sys.stderr)
            return 2
        report = json.loads(BENCHMARK_LATEST.read_text(encoding="utf-8"))
        return cmd_apply_from_report(report, dry_run=args.dry_run)
    if args.value is None:
        print("need --value or --from-benchmark", file=sys.stderr)
        return 2
    if args.dry_run:
        print(json.dumps({"dry_run": True, "would_write": args.value}, indent=2))
        return 0
    payload = write_threshold(float(args.value), source="operator_set", evidence={})
    print(json.dumps(payload, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Calibrate Master S_n dormancy threshold")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status")
    s.set_defaults(func=cmd_status)

    b = sub.add_parser("benchmark", help="Idle plant samples + history → proposal")
    b.add_argument("--seconds", type=float, default=20.0)
    b.add_argument("--interval", type=float, default=1.0)
    b.add_argument("--apply", action="store_true", help="Write proposed threshold after bench")
    b.set_defaults(func=cmd_benchmark)

    a = sub.add_parser("apply", help="Write threshold JSON (Law 5 + cpu_config)")
    a.add_argument("--from-benchmark", action="store_true")
    a.add_argument("--value", type=float, default=None)
    a.add_argument("--dry-run", action="store_true")
    a.set_defaults(func=cmd_apply)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
