#!/usr/bin/env python3
"""Short CPU press — watch autonomous / RID react in another terminal."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.rid_stressor import start_stressor, stop_stressor, stress_alive


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="CPU press for a few seconds (RID / auto_main watch)")
    p.add_argument("--seconds", "-s", type=float, default=10.0, help="How long to burn (default: 10)")
    p.add_argument("--cores", "-c", type=int, default=0, help="Worker count (0 = all logical CPUs)")
    p.add_argument("--ramp", type=float, default=0.5, help="Seconds before full burn (default: 0.5)")
    args = p.parse_args(argv)

    cores = args.cores if args.cores > 0 else None
    duration = max(0.5, float(args.seconds))
    ramp = max(0.0, float(args.ramp))

    n_workers = cores or (__import__("os").cpu_count() or 8)
    print(f"[CPU PRESS] starting {n_workers} workers for {duration:.1f}s")
    print("  Watch auto_main / Master_S_n in the other terminal.")
    if ramp > 0:
        print(f"  Ramping {ramp:.1f}s...")
        time.sleep(ramp)

    procs = start_stressor(cores)
    alive = stress_alive(procs)
    print(f"[CPU PRESS] burn ON — {alive}/{n_workers} workers alive")

    t0 = time.monotonic()
    try:
        while True:
            elapsed = time.monotonic() - t0
            if elapsed >= duration:
                break
            left = duration - elapsed
            alive = stress_alive(procs)
            print(f"  ... {elapsed:.1f}s elapsed, {left:.1f}s left, workers={alive}", end="\r", flush=True)
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\n[CPU PRESS] interrupted — stopping workers")
    else:
        print(f"\n[CPU PRESS] done ({duration:.1f}s) — stopping workers")

    stop_stressor(procs)
    print("[CPU PRESS] off")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
