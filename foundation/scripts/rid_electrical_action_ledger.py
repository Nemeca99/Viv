#!/usr/bin/env python3
"""Build calibrated action-cost ledger + cost profiles from sessions.

Does not reopen Master prediction. Token counts remain null until capture
instruments them.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_action_ledger.py --corpus
  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_action_ledger.py --session <id>
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

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_capture import load_session_meta, load_session_samples  # noqa: E402
from lib.rid_electrical_outcomes import (  # noqa: E402
    cost_profiles_from_actions,
    ledger_from_session,
)
from lib.rid_electrical_policy import LIFECYCLE, RAIL_ROLE, policy_stamp  # noqa: E402
from lib.rid_electrical_session_eval import list_decisive_sessions  # noqa: E402

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
SESSIONS = OUT_DIR / "sessions"
LEDGER_JSON = OUT_DIR / "action_ledger_latest.json"
LEDGER_MD = OUT_DIR / "action_ledger_latest.md"
PROFILES_JSON = OUT_DIR / "cost_profiles_latest.json"
PROFILES_MD = OUT_DIR / "cost_profiles_latest.md"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_session_ledger(session_id: str) -> dict[str, Any]:
    d = SESSIONS / session_id
    samples = load_session_samples(d)
    meta = load_session_meta(d)
    return ledger_from_session(samples, meta)


def build_corpus_ledger() -> dict[str, Any]:
    session_ledgers = []
    all_actions: list[dict[str, Any]] = []
    for s in list_decisive_sessions():
        led = ledger_from_session(s.get("samples") or [], s.get("meta") or {})
        session_ledgers.append(
            {
                "session_id": led["session_id"],
                "workload": led["workload"],
                "session_total": {
                    "E_gross_j": (led.get("session_total") or {}).get("E_gross_j"),
                    "E_net_j": (led.get("session_total") or {}).get("E_net_j"),
                    "P_peak_w": (led.get("session_total") or {}).get("P_peak_w"),
                    "confidence": (led.get("session_total") or {}).get("confidence"),
                    "overload_level": ((led.get("session_total") or {}).get("overload") or {}).get(
                        "level"
                    ),
                },
                "n_actions": led.get("n_actions"),
                "actions": led.get("actions"),
            }
        )
        all_actions.extend(led.get("actions") or [])

    profiles = cost_profiles_from_actions(all_actions, action_type_filter="active_load")
    # Also phase-level profiles for sustained / ramp
    phase_profiles = cost_profiles_from_actions(
        [a for a in all_actions if str(a.get("action_type", "")).startswith("phase:")],
        action_type_filter=None,
    )

    conf = {"valid": 0, "degraded": 0, "invalid": 0}
    overload = {}
    for a in all_actions:
        if a.get("action_type") != "active_load":
            continue
        c = str(a.get("confidence") or "unknown")
        conf[c] = conf.get(c, 0) + 1
        ol = str(a.get("overload_level") or "unknown")
        overload[ol] = overload.get(ol, 0) + 1

    payload = {
        "ok": True,
        "at": _utc(),
        "experiment_id": "rid_electrical_action_ledger_v1",
        "milestone": "validated_integration→per_action_attribution→cost_profiles",
        "master_prediction_branch": "closed_negative_result",
        "lifecycle_master_electrical": LIFECYCLE,
        "rail_role": RAIL_ROLE,
        "policy": policy_stamp(),
        "n_sessions": len(session_ledgers),
        "n_actions": len(all_actions),
        "active_load_confidence": conf,
        "active_load_overload": overload,
        "sessions": session_ledgers,
        "cost_profiles_active_load": profiles,
        "note": (
            "Action-cost ledger from rail power. Token counts not yet instrumented. "
            "Overload uses min-duration hysteresis. Not Master/A(t)/routing."
        ),
        "next": (
            "Repeat dedicated ledger sessions with instrumented token counts; "
            "then evaluate whether signatures are stable enough to learn "
            "f→(Ê, P̂_peak, R̂_overload) on holdouts."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LEDGER_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Human ledger excerpt
    lines = [
        "# Electrical action-cost ledger",
        "",
        f"- **At:** {payload['at']}",
        f"- **Sessions:** {payload['n_sessions']}",
        f"- **Actions:** {payload['n_actions']}",
        f"- **Active-load confidence:** {conf}",
        f"- **Active-load overload (τ-gated):** {overload}",
        "",
        "## Example active_load rows",
        "",
    ]
    for led in session_ledgers:
        for a in led.get("actions") or []:
            if a.get("action_type") != "active_load":
                continue
            lines.append(f"- {a.get('human_summary')}")
    lines.extend(["", "## Cost profiles (active_load)", ""])
    for wl, p in (profiles.get("profiles") or {}).items():
        lines.append(
            f"- **{wl}:** n={p['n']} μE_net={_fmt_e(p.get('mu_E_net_j'))} "
            f"σE={_fmt_e(p.get('sigma_E_net_j'))} "
            f"μP_peak={_fmt_p(p.get('mu_P_peak_w'))} "
            f"repeatable={p.get('repeatable_signature')}"
        )
    lines.append("")
    LEDGER_MD.write_text("\n".join(lines), encoding="utf-8")

    PROFILES_JSON.write_text(
        json.dumps(
            {
                "ok": True,
                "at": _utc(),
                "active_load": profiles,
                "by_phase_action": phase_profiles,
                "authority": "action_cost_ledger_only",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    plines = [
        "# Electrical cost profiles",
        "",
        f"Repeatable signatures: {profiles.get('n_repeatable_signatures')}/{profiles.get('n_workloads')}",
        "",
    ]
    for wl, p in (profiles.get("profiles") or {}).items():
        plines.append(
            f"## {wl}\n"
            f"- n={p['n']}\n"
            f"- μE_net={p.get('mu_E_net_j')} σ={p.get('sigma_E_net_j')} cv={p.get('cv_E_net')}\n"
            f"- μP_peak={p.get('mu_P_peak_w')} σ={p.get('sigma_P_peak_w')}\n"
            f"- repeatable_signature={p.get('repeatable_signature')}\n"
        )
    PROFILES_MD.write_text("\n".join(plines), encoding="utf-8")

    payload["artifact_json"] = str(LEDGER_JSON).replace("\\", "/")
    payload["artifact_md"] = str(LEDGER_MD).replace("\\", "/")
    payload["profiles_json"] = str(PROFILES_JSON).replace("\\", "/")
    return payload


def _fmt_e(x: Any) -> str:
    if x is None:
        return "n/a"
    v = float(x)
    return f"{v/1000:.2f}kJ" if abs(v) >= 1000 else f"{v:.0f}J"


def _fmt_p(x: Any) -> str:
    if x is None:
        return "n/a"
    return f"{float(x):.0f}W"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--corpus", action="store_true", help="Ledger all decisive sessions")
    g.add_argument("--session", type=str, help="Single session_id")
    args = p.parse_args()
    if args.session:
        out = build_session_ledger(str(args.session))
        out["at"] = _utc()
        path = OUT_DIR / f"action_ledger_{args.session}.json"
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(json.dumps(out, indent=2), flush=True)
        return 0 if out.get("ok") else 1
    out = build_corpus_ledger()
    # Compact stdout
    slim = {
        k: out[k]
        for k in (
            "ok",
            "at",
            "experiment_id",
            "n_sessions",
            "n_actions",
            "active_load_confidence",
            "active_load_overload",
            "cost_profiles_active_load",
            "artifact_json",
            "artifact_md",
            "profiles_json",
            "next",
        )
        if k in out
    }
    print(json.dumps(slim, indent=2), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
