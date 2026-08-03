#!/usr/bin/env python3
"""Run one labeled electrical workload session with enriched JSONL capture.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_workload_session.py --profile cpu_ramp --smoke
  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_workload_session.py --all --smoke

Never mutates Master RID. Each profile is a whole evaluation session.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.master_rid import MASTER_RID_PATH  # noqa: E402
from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_capture import SessionCapture  # noqa: E402
from lib.rid_electrical_workloads import (  # noqa: E402
    PROFILE_NAMES,
    WorkloadController,
    phases_for,
    run_profile_phases,
)

SESSIONS = AUTO_ARTIFACTS / "rid_electrical" / "sessions"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_session(
    profile: str,
    *,
    smoke: bool = False,
    cadence_s: float = 1.0,
) -> dict[str, Any]:
    session_id = f"{profile}_{_utc_stamp()}"
    session_dir = SESSIONS / session_id
    master_before = (
        MASTER_RID_PATH.read_text(encoding="utf-8") if MASTER_RID_PATH.is_file() else None
    )
    meta = {
        "session_id": session_id,
        "workload": profile,
        "smoke": smoke,
        "cadence_s": cadence_s,
        "started_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "goal": "prove_electrical_info_gain_not_master_admission",
        "phases": [p.name for p in phases_for(profile, smoke=smoke)],
    }
    cap = SessionCapture(session_dir, meta)
    cap.open()
    ctrl = WorkloadController()

    def on_tick(phase_name: str, phase: Any) -> None:
        cap.record(
            workload=profile,
            phase=phase_name,
            cadence_s=cadence_s,
            session_id=session_id,
        )

    try:
        result = run_profile_phases(
            profile,
            smoke=smoke,
            cadence_s=cadence_s,
            on_tick=on_tick,
            controller=ctrl,
        )
        master_after = (
            MASTER_RID_PATH.read_text(encoding="utf-8") if MASTER_RID_PATH.is_file() else None
        )
        cap.close(
            duration_s=result["duration_s"],
            events=result["events"],
            master_disk_mutated=master_before != master_after,
            samples_path=str(cap.jsonl_path).replace("\\", "/"),
        )
        out = {
            "ok": True,
            "session_id": session_id,
            "workload": profile,
            "session_dir": str(session_dir).replace("\\", "/"),
            "n_samples": cap.n_samples,
            "duration_s": result["duration_s"],
            "smoke": smoke,
            "master_disk_mutated": master_before != master_after,
            "lifecycle": "measured_in_shadow",
        }
    except Exception as exc:  # noqa: BLE001
        ctrl.stop_all()
        cap.close(incomplete=True, error=str(exc))
        raise
    (session_dir / "session_summary.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8"
    )
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", choices=PROFILE_NAMES, help="Single workload profile")
    p.add_argument("--all", action="store_true", help="Run all five profiles as separate sessions")
    p.add_argument("--smoke", action="store_true", help="Short durations for validation")
    p.add_argument("--cadence", type=float, default=1.0, help="Sample period seconds")
    args = p.parse_args()
    if not args.all and not args.profile:
        p.error("require --profile or --all")
    profiles = list(PROFILE_NAMES) if args.all else [args.profile]
    summaries = []
    for name in profiles:
        print(f"[electrical-session] starting {name} smoke={args.smoke}", flush=True)
        summaries.append(run_session(name, smoke=args.smoke, cadence_s=args.cadence))
        print(json.dumps(summaries[-1], indent=2), flush=True)
    index = {
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "sessions": summaries,
        "master_any_mutated": any(s.get("master_disk_mutated") for s in summaries),
    }
    SESSIONS.mkdir(parents=True, exist_ok=True)
    (SESSIONS / "index_latest.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    return 0 if all(s.get("ok") for s in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
