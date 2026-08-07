#!/usr/bin/env python3
"""Local overnight AIOS health loop (measurement-only; no start/stop/train/stress).

Runs until wall clock ~10 hours (or --hours). Each cycle runs safe smoke/plan/status
jobs, appends HEARTBEAT.jsonl, updates LATEST.json, and writes SUMMARY.json on exit.

Never: AIOS start/stop, GPU_LONG train, 120s plant stress, soft-0.99, mic,
network installs, git push.

Example:
  L:/Continue/.venv/Scripts/python.exe -B foundation/scripts/run_aios_overnight_local_v1.py --hours 10
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
FOUNDATION = SCRIPTS_DIR.parent
VIV_ROOT = FOUNDATION.parent
PYTHON = Path(r"L:\Continue\.venv\Scripts\python.exe")
ARTIFACT_ROOT = FOUNDATION / "artifacts" / "auto" / "overnight_local"

# Soft timeouts per step (seconds) — keep cycles bounded.
STEP_TIMEOUT_S = {
    "system_smoke": 180,
    "skeleton_plan": 120,
    "uml_status": 120,
    "speak_dry_run": 180,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def run_step(
    name: str,
    script: Path,
    args: list[str],
    cwd: Path,
    timeout_s: int,
) -> dict[str, Any]:
    if not script.is_file():
        return {
            "name": name,
            "status": "skipped",
            "reason": "missing",
            "script": str(script),
            "duration_s": 0.0,
            "returncode": None,
        }
    cmd = [str(PYTHON), "-B", str(script), *args]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        duration = round(time.monotonic() - t0, 3)
        ok = proc.returncode == 0
        return {
            "name": name,
            "status": "pass" if ok else "fail",
            "script": str(script),
            "args": args,
            "duration_s": duration,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-800:],
            "stderr_tail": (proc.stderr or "")[-800:],
        }
    except subprocess.TimeoutExpired as exc:
        duration = round(time.monotonic() - t0, 3)
        return {
            "name": name,
            "status": "fail",
            "reason": "timeout",
            "script": str(script),
            "args": args,
            "duration_s": duration,
            "returncode": None,
            "timeout_s": timeout_s,
            "stdout_tail": ((exc.stdout or "") if isinstance(exc.stdout, str) else "")[-800:],
            "stderr_tail": ((exc.stderr or "") if isinstance(exc.stderr, str) else "")[-800:],
        }
    except Exception as exc:  # noqa: BLE001 — overnight must not die
        duration = round(time.monotonic() - t0, 3)
        return {
            "name": name,
            "status": "fail",
            "reason": "exception",
            "script": str(script),
            "args": args,
            "duration_s": duration,
            "returncode": None,
            "error": repr(exc),
        }


def cycle_steps() -> list[tuple[str, Path, list[str], int]]:
    return [
        ("system_smoke", SCRIPTS_DIR / "run_aios_system_smoke_v1.py", [], STEP_TIMEOUT_S["system_smoke"]),
        (
            "skeleton_plan",
            SCRIPTS_DIR / "run_aios_skeleton_v1.py",
            ["--plan-only"],
            STEP_TIMEOUT_S["skeleton_plan"],
        ),
        (
            "uml_status",
            SCRIPTS_DIR / "run_training_automation_v1.py",
            ["--profile", "uml_status"],
            STEP_TIMEOUT_S["uml_status"],
        ),
        (
            "speak_dry_run",
            SCRIPTS_DIR / "run_viv_speak_session_v1.py",
            ["--dry-run"],
            STEP_TIMEOUT_S["speak_dry_run"],
        ),
    ]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hours", type=float, default=10.0, help="Wall-clock run duration (default 10)")
    p.add_argument(
        "--cycle-min",
        type=float,
        default=25.0,
        help="Minutes between cycle starts (default 25; target 20-30)",
    )
    p.add_argument(
        "--run-stamp",
        type=str,
        default="",
        help="Optional artifact stamp folder name",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    run_id = args.run_stamp.strip() or stamp()
    run_dir = ARTIFACT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    heartbeat = run_dir / "HEARTBEAT.jsonl"
    latest = run_dir / "LATEST.json"
    summary_path = run_dir / "SUMMARY.json"

    pid = os.getpid()
    started = utc_now()
    deadline = started.timestamp() + max(0.1, float(args.hours)) * 3600.0
    cycle_interval_s = max(60.0, float(args.cycle_min) * 60.0)

    print(f"OVERNIGHT_LOCAL pid={pid}", flush=True)
    print(f"OVERNIGHT_LOCAL run_dir={run_dir}", flush=True)
    print(f"OVERNIGHT_LOCAL heartbeat={heartbeat}", flush=True)
    print(f"OVERNIGHT_LOCAL hours={args.hours} cycle_min={args.cycle_min}", flush=True)
    print(f"OVERNIGHT_LOCAL python={PYTHON}", flush=True)

    write_json(
        latest,
        {
            "pid": pid,
            "status": "starting",
            "run_dir": str(run_dir),
            "started_utc": started.isoformat(),
            "hours": args.hours,
            "cycle_min": args.cycle_min,
        },
    )

    cycles = 0
    fails = 0
    passes = 0
    skips = 0
    stop_reason = "completed"

    try:
        while True:
            now_ts = time.time()
            if now_ts >= deadline:
                stop_reason = "time_budget"
                break

            cycles += 1
            cycle_t0 = time.monotonic()
            cycle_started = utc_now()
            step_results: list[dict[str, Any]] = []
            cycle_fail = 0
            cycle_pass = 0
            cycle_skip = 0

            for name, script, step_args, timeout_s in cycle_steps():
                result = run_step(name, script, step_args, VIV_ROOT, timeout_s)
                step_results.append(result)
                st = result.get("status")
                if st == "pass":
                    cycle_pass += 1
                    passes += 1
                elif st == "fail":
                    cycle_fail += 1
                    fails += 1
                else:
                    cycle_skip += 1
                    skips += 1
                print(
                    f"cycle={cycles} step={name} status={st} "
                    f"rc={result.get('returncode')} dur={result.get('duration_s')}s",
                    flush=True,
                )

            cycle_row = {
                "ts_utc": cycle_started.isoformat(),
                "cycle": cycles,
                "pid": pid,
                "seconds_remaining": max(0.0, round(deadline - time.time(), 1)),
                "pass": cycle_pass,
                "fail": cycle_fail,
                "skip": cycle_skip,
                "duration_s": round(time.monotonic() - cycle_t0, 3),
                "steps": step_results,
            }
            append_jsonl(heartbeat, cycle_row)
            write_json(
                latest,
                {
                    "pid": pid,
                    "status": "running",
                    "run_dir": str(run_dir),
                    "started_utc": started.isoformat(),
                    "updated_utc": utc_now().isoformat(),
                    "cycles": cycles,
                    "fails": fails,
                    "passes": passes,
                    "skips": skips,
                    "last_cycle": {
                        "cycle": cycles,
                        "pass": cycle_pass,
                        "fail": cycle_fail,
                        "skip": cycle_skip,
                        "ts_utc": cycle_started.isoformat(),
                    },
                    "heartbeat": str(heartbeat),
                },
            )

            # Sleep until next cycle, but never past deadline.
            remaining = deadline - time.time()
            if remaining <= 0:
                stop_reason = "time_budget"
                break
            sleep_s = min(cycle_interval_s, remaining)
            # Subtract time already spent in this cycle so interval is ~wall between starts.
            spent = time.monotonic() - cycle_t0
            sleep_s = max(0.0, min(sleep_s, cycle_interval_s - spent))
            if sleep_s > 0:
                time.sleep(sleep_s)

    except KeyboardInterrupt:
        stop_reason = "keyboard_interrupt"
        print("OVERNIGHT_LOCAL interrupted", flush=True)

    ended = utc_now()
    summary = {
        "pid": pid,
        "status": "stopped",
        "stop_reason": stop_reason,
        "run_dir": str(run_dir),
        "started_utc": started.isoformat(),
        "ended_utc": ended.isoformat(),
        "hours_requested": args.hours,
        "cycle_min": args.cycle_min,
        "cycles": cycles,
        "passes": passes,
        "fails": fails,
        "skips": skips,
        "heartbeat": str(heartbeat),
        "latest": str(latest),
    }
    write_json(summary_path, summary)
    write_json(latest, {**summary, "updated_utc": ended.isoformat()})
    print(f"OVERNIGHT_LOCAL summary={summary_path}", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
