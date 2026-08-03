#!/usr/bin/env python3
"""Summarize session and daily energy ledgers.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_energy_ledger_summarize.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_energy_ledger import (  # noqa: E402
    LEDGER_DIR,
    load_actions,
    summarize_daily,
    summarize_registry_accounting,
    summarize_sessions,
)
from lib.rid_electrical_policy import policy_stamp  # noqa: E402


def main() -> int:
    rows = load_actions()
    session = summarize_sessions(rows)
    daily = summarize_daily(rows)
    registry = summarize_registry_accounting(rows)
    session["policy"] = policy_stamp()
    daily["policy"] = policy_stamp()
    registry["policy"] = policy_stamp()

    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    s_json = LEDGER_DIR / "energy_ledger_session_latest.json"
    d_json = LEDGER_DIR / "energy_ledger_daily_latest.json"
    r_json = LEDGER_DIR / "registry_accounting_report_latest.json"
    s_md = LEDGER_DIR / "energy_ledger_session_latest.md"
    d_md = LEDGER_DIR / "energy_ledger_daily_latest.md"
    r_md = LEDGER_DIR / "registry_accounting_report_latest.md"
    s_json.write_text(json.dumps(session, indent=2), encoding="utf-8")
    d_json.write_text(json.dumps(daily, indent=2), encoding="utf-8")
    r_json.write_text(json.dumps(registry, indent=2), encoding="utf-8")

    s_lines = [
        "# Energy ledger — sessions",
        "",
        f"- sessions: {session.get('n_sessions')}",
        f"- actions: {session.get('n_actions')}",
        "",
    ]
    for s in session.get("sessions") or []:
        s_lines.append(
            f"- `{s.get('session_id')}`: n={s.get('n_actions')} "
            f"E={s.get('E_session_j')} J ({s.get('E_session_kWh')} kWh)"
        )
    s_md.write_text("\n".join(s_lines) + "\n", encoding="utf-8")

    d_lines = [
        "# Energy ledger — daily",
        "",
        f"- days: {daily.get('n_days')}",
        f"- actions: {daily.get('n_actions')}",
        "",
    ]
    for day in daily.get("days") or []:
        d_lines.append(
            f"- `{day.get('date')}`: n={day.get('n_actions')} "
            f"E={day.get('E_daily_j')} J ({day.get('E_daily_kWh')} kWh)"
        )
    d_md.write_text("\n".join(d_lines) + "\n", encoding="utf-8")

    r_lines = [
        "# Registry accounting report",
        "",
        f"- actions: {registry.get('n_actions')}",
        f"- E_j: {registry.get('E_j')}",
        f"- null_stats: `{registry.get('null_stats')}`",
        f"- receipt_completeness: `{registry.get('receipt_completeness')}`",
        f"- by_registry_selected_predictor: `{registry.get('by_registry_selected_predictor')}`",
        "",
    ]
    r_md.write_text("\n".join(r_lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "n_actions": len(rows),
                "n_sessions": session.get("n_sessions"),
                "n_days": daily.get("n_days"),
                "session_artifact": str(s_json).replace("\\", "/"),
                "daily_artifact": str(d_json).replace("\\", "/"),
                "registry_artifact": str(r_json).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
