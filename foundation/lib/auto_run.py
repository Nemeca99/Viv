"""Unified CPU automaton run loop."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from lib.auto_gate import evaluate_run_gate, write_operator_present
from lib.auto_narrator import narrate_latest
from lib.auto_rid_journal import journal_pulse
from lib.cpu_status import format_pulse_line, pulse_payload
from lib.paths import AUTO_ARTIFACTS
from lib.rid_feed import LIVE_SAMPLE_PATH, pulse_once


def run_beat(
    *,
    pulse_path: Path,
    journal: bool = True,
    narrate: bool = True,
    runtime_tick: bool = False,
    max_tasks: int = 1,
    piston: bool = False,
) -> dict[str, Any]:
    sample = pulse_once()
    payload = pulse_payload(sample)
    report: dict[str, Any] = {"sample": sample.to_dict(), "steps": []}

    if journal:
        j = journal_pulse(sample)
        payload["journal"] = j["heartbeat"]
        report["steps"].append("journal")
        report["supervisor_control"] = j["supervisor"]["system_rid"]["control"]
    else:
        write_operator_present(active=sample.s_n >= 0.45)

    if piston:
        from lib.piston_engine import piston_pulse

        p = piston_pulse(journal=journal)
        payload["piston"] = p
        report["piston"] = p
        report["steps"].append("piston")

    _write(pulse_path, payload)
    report["steps"].append("pulse")

    if narrate:
        n = narrate_latest(print_line=False)
        if n.get("line"):
            report["narrator_line"] = n["line"]
        report["steps"].append("narrator")

    gate = evaluate_run_gate(action_risk="low", irreversible=False)
    report["gate"] = gate
    report["steps"].append("gate")

    if runtime_tick and gate.get("allow"):
        rc = _runtime_tick(max_tasks)
        report["runtime_tick"] = rc
        report["steps"].append("runtime_tick")
    elif runtime_tick:
        report["runtime_tick"] = {"skipped": True, "reason": "gate_denied"}

    report["allow"] = gate.get("allow")
    report["line"] = format_pulse_line(sample)
    return report


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def runtime_tick(max_tasks: int) -> dict[str, Any]:
    return _runtime_tick(max_tasks)


def _runtime_tick(max_tasks: int) -> dict[str, Any]:
    """Prefer Viv-owned agentic queue (Rust-gated). Legacy FSAA is fallback only."""
    try:
        from lib.agentic_runtime import run_once

        report = run_once(max(1, max_tasks))
        return {
            "ok": bool(report.get("ok")) and int(report.get("exit_code", 0) or 0) == 0,
            "exit_code": int(report.get("exit_code", 0) or 0),
            "owner": "viv",
            "report": report,
        }
    except Exception as exc:  # noqa: BLE001 — fall back with evidence
        return {"ok": False, "owner": "viv", "reason": f"viv_tick_error:{exc}"}



def run_loop(
    *,
    interval: float = 1.0,
    pulse_path: Path | None = None,
    journal: bool = True,
    narrate: bool = True,
    runtime_tick: bool = False,
    max_tasks: int = 1,
    piston: bool = False,
) -> int:
    out = pulse_path or (AUTO_ARTIFACTS / "pulse.json")
    print(f"Viv CPU automaton @ {interval}s")
    print(f"  live_sample: {LIVE_SAMPLE_PATH}")
    print(f"  pulse:       {out}")
    print("  No LLM. Ctrl+C to stop.")
    try:
        while True:
            beat = run_beat(
                pulse_path=out,
                journal=journal,
                narrate=narrate,
                runtime_tick=runtime_tick,
                max_tasks=max_tasks,
                piston=piston,
            )
            line = beat["line"]
            ctl = beat.get("supervisor_control") or beat.get("gate", {}).get("supervisor_control")
            gate_ok = beat.get("allow")
            suffix = f" | ctl={ctl} | gate={'ALLOW' if gate_ok else 'DENY'}"
            if beat.get("narrator_line"):
                print(beat["narrator_line"])
            else:
                print(line + suffix)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nstopped.")
        return 0
