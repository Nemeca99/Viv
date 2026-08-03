#!/usr/bin/env python3
"""Observe/accounting for direct electrical outcomes (E=∫P dt, peak, overload).

Separate experiment from closed Master S_n prediction. Never writes Master,
never enters A(t), never enables routing.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_outcomes_observe.py --live 30
  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_outcomes_observe.py --session cpu_ramp_20260727T024438Z
  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_outcomes_observe.py --corpus-summary
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_capture import SessionCapture, load_session_samples  # noqa: E402
from lib.rid_electrical_outcomes import outcomes_from_samples  # noqa: E402
from lib.rid_electrical_policy import (  # noqa: E402
    LIFECYCLE,
    RAIL_ROLE,
    policy_stamp,
)
from lib.rid_electrical_session_eval import list_decisive_sessions  # noqa: E402

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
SESSIONS = OUT_DIR / "sessions"
LATEST = OUT_DIR / "outcomes_observe_latest.json"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _wrap(payload: dict[str, Any]) -> dict[str, Any]:
    out = {
        "ok": True,
        "at": _utc(),
        "experiment_id": "rid_electrical_outcomes_v1",
        "hypothesis": (
            "Rail power predicts/accounts for direct electrical quantities "
            "(action energy, peak board power, overload risk) — not Master S_n."
        ),
        "master_prediction_branch": "closed_negative_result",
        "lifecycle_master_electrical": LIFECYCLE,
        "rail_role": RAIL_ROLE,
        "policy": policy_stamp(),
        **payload,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(out, indent=2), encoding="utf-8")
    out["artifact"] = str(LATEST).replace("\\", "/")
    return out


def run_live(seconds: float, *, cadence_s: float = 1.0) -> dict[str, Any]:
    sid = f"outcomes_live_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    session_dir = SESSIONS / sid
    cap = SessionCapture(
        session_dir,
        {
            "session_id": sid,
            "workload": "outcomes_live",
            "smoke": True,
            "experiment": "rid_electrical_outcomes_v1",
            "not_master_prediction": True,
        },
    )
    cap.open()
    t_end = time.perf_counter() + max(1.0, float(seconds))
    while time.perf_counter() < t_end:
        cap.record(
            workload="outcomes_live",
            phase="observe",
            cadence_s=cadence_s,
            session_id=sid,
        )
        time.sleep(cadence_s)
    cap.close(duration_s=float(seconds), experiment="rid_electrical_outcomes_v1")
    samples = load_session_samples(session_dir)
    oc = outcomes_from_samples(samples)
    return _wrap(
        {
            "mode": "live",
            "session_id": sid,
            "outcomes": oc,
            "note": "Live accounting window. Diagnostic only; not Master prediction.",
        }
    )


def run_session(session_id: str) -> dict[str, Any]:
    d = SESSIONS / session_id
    if not d.is_dir():
        return _wrap({"ok": False, "error": f"missing_session:{session_id}", "mode": "session"})
    samples = load_session_samples(d)
    oc = outcomes_from_samples(samples)
    return _wrap(
        {
            "mode": "session",
            "session_id": session_id,
            "outcomes": oc,
            "note": "Replay accounting on existing capture. Not a Master reopen.",
        }
    )


def run_corpus_summary() -> dict[str, Any]:
    rows = []
    for s in list_decisive_sessions():
        oc = outcomes_from_samples(s.get("samples") or [])
        rows.append(
            {
                "session_id": s.get("session_id"),
                "workload": s.get("workload"),
                "E_action_j": oc.get("E_action_j"),
                "P_peak_w": oc.get("P_peak_w"),
                "P_mean_w": oc.get("P_mean_w"),
                "overload_level": (oc.get("overload_risk") or {}).get("level"),
                "duration_s": oc.get("duration_s"),
                "ok": oc.get("ok"),
            }
        )
    ok_rows = [r for r in rows if r.get("ok") and r.get("E_action_j") is not None]
    total_e = sum(float(r["E_action_j"]) for r in ok_rows) if ok_rows else None
    return _wrap(
        {
            "mode": "corpus_summary",
            "n_sessions": len(rows),
            "n_ok": len(ok_rows),
            "E_action_j_sum": total_e,
            "sessions": rows,
            "note": (
                "Frozen decisive corpus replayed for electrical accounting only. "
                "Does not reopen Master prediction."
            ),
        }
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--live", type=float, metavar="SECONDS", help="Live observe window")
    g.add_argument("--session", type=str, help="Replay one session_id")
    g.add_argument("--corpus-summary", action="store_true", help="Summarize frozen decisive corpus")
    p.add_argument("--cadence", type=float, default=1.0)
    args = p.parse_args()
    if args.live is not None:
        out = run_live(float(args.live), cadence_s=float(args.cadence))
    elif args.session:
        out = run_session(str(args.session))
    else:
        out = run_corpus_summary()
    print(json.dumps(out, indent=2), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
