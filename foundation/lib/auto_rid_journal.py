"""Bridge Viv foundation pulses → Continue/automation RID event log."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS, AUTOMATION_ROOT
from lib.rid_telemetry import DORMANCY_THRESHOLD, RidSample

RID_BODY = AUTOMATION_ROOT / "3_body"
RID_LOGS = RID_BODY / "rid_logs"
EVENTS_PATH = RID_LOGS / "events.jsonl"
STATE_PATH = RID_LOGS / "supervisor_state.json"
BEAT_PATH = AUTO_ARTIFACTS / "beat.json"
HEARTBEAT_PATH = AUTO_ARTIFACTS / "automaton_heartbeat.json"


def _rid_body_on_path() -> None:
    body = str(RID_BODY)
    if body not in sys.path:
        sys.path.insert(0, body)


def next_beat() -> int:
    BEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    beat = 1
    if BEAT_PATH.is_file():
        try:
            beat = int(json.loads(BEAT_PATH.read_text(encoding="utf-8")).get("beat", 0)) + 1
        except (json.JSONDecodeError, TypeError, ValueError):
            beat = 1
    BEAT_PATH.write_text(json.dumps({"beat": beat}), encoding="utf-8")
    return beat


def _triple_for_sample(sample: RidSample, master=None):
    _rid_body_on_path()
    from rid_core import RIDTriple, recommended_control
    from lib.master_rid import MasterRid, compute_master_rid

    if master is None:
        master = compute_master_rid(sample)
    rsr, ltp, rle = master.master_rsr, master.master_ltp, master.master_rle
    s_n = master.master_s_n
    if s_n < DORMANCY_THRESHOLD:
        return RIDTriple(
            rsr=rsr,
            ltp=ltp,
            rle=rle,
            s_n=s_n,
            verdict="danger",
            control="pause",
        )
    triple = RIDTriple.from_channels(rsr, ltp, rle)
    if master.status.upper() == "DORMANT":
        return RIDTriple(
            rsr=triple.rsr,
            ltp=triple.ltp,
            rle=triple.rle,
            s_n=triple.s_n,
            verdict="danger",
            control=recommended_control("danger", risk="normal", reversible=True),
        )
    return triple


def journal_pulse(sample: RidSample, *, beat: int | None = None) -> dict[str, Any]:
    """Append one PC RID heartbeat to automation rid_logs and refresh supervisor."""
    _rid_body_on_path()
    from rid_event_schema import RIDEvent, append_event
    from rid_supervisor import write_state
    from lib.master_rid import compute_master_rid, publish_master_rid

    master = compute_master_rid(sample)
    publish_master_rid(master)
    beat_n = beat if beat is not None else next_beat()
    rid = _triple_for_sample(sample, master)
    event = RIDEvent(
        run_id="viv_automaton",
        subsystem="runtime",
        source="viv_auto_pulse",
        phase="heartbeat",
        risk="low",
        reversible=True,
        rid=rid,
        metrics={
            "beat": beat_n,
            "master_s_n": master.master_s_n,
            "n_subsystems": master.n_subsystems,
            "cpu_load": float(getattr(sample, "cpu_load_pct", getattr(sample, "cpu_load", 0))),
            "cpu_temp": float(getattr(sample, "a_c", getattr(sample, "cpu_temp", 0))),
            "ram_pct": sample.ram_pct,
        },
        evidence=[{"type": "pc_rid_sample", "timestamp": sample.timestamp}],
        notes=[f"Master_S_n={master.master_s_n:.4f} {master.status} subs={master.n_subsystems}"],
    )
    append_event(EVENTS_PATH, event)
    decision = write_state(EVENTS_PATH, STATE_PATH)

    heartbeat = {
        "timestamp": sample.timestamp,
        "beat": beat_n,
        "s_n": master.master_s_n,
        "master_s_n": master.master_s_n,
        "master_rsr": master.master_rsr,
        "master_ltp": master.master_ltp,
        "master_rle": master.master_rle,
        "subsystems": {
            k: {"s_n": v.s_n, "available": v.available}
            for k, v in master.subsystems.items()
        },
        "status": "verified" if master.master_s_n >= DORMANCY_THRESHOLD else "dormant",
        "valid": master.master_s_n >= DORMANCY_THRESHOLD,
        "dormant": master.master_s_n < DORMANCY_THRESHOLD,
        "allow_automation": rid.control in ("allow", "throttle"),
        "control": rid.control,
        "verdict": rid.verdict,
        "events_path": str(EVENTS_PATH),
        "state_path": str(STATE_PATH),
        "event_id": event.event_id,
    }
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_PATH.write_text(json.dumps(heartbeat, indent=2), encoding="utf-8")

    from lib.auto_gate import write_operator_present

    write_operator_present(active=heartbeat["valid"])

    return {
        "heartbeat": heartbeat,
        "supervisor": decision.to_dict(),
    }


def read_supervisor_state() -> dict[str, Any] | None:
    if not STATE_PATH.is_file():
        return None
    try:
        raw = STATE_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            return _rebuild_supervisor_state()
        return json.loads(raw)
    except json.JSONDecodeError:
        return _rebuild_supervisor_state()


def _rebuild_supervisor_state() -> dict[str, Any] | None:
    if not EVENTS_PATH.is_file():
        return None
    _rid_body_on_path()
    from rid_supervisor import write_state

    decision = write_state(EVENTS_PATH, STATE_PATH)
    return decision.to_dict()
