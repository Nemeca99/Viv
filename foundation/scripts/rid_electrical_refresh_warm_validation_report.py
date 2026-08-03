#!/usr/bin/env python3
"""Refresh warm-repeat validation report diagnostics from existing session artifacts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_ledger_controls import evaluate_control_repeats  # noqa: E402

OUT = FOUNDATION / "artifacts" / "auto" / "rid_electrical" / "ledger_campaign"
SESSIONS = FOUNDATION / "artifacts" / "auto" / "rid_electrical" / "sessions"


def main() -> int:
    p = OUT / "control_validation_warm_repeat_latest.json"
    rep = json.loads(p.read_text(encoding="utf-8"))
    rows = []
    for a in rep["actions"]:
        sid = a["session_id"]
        full = json.loads(
            (SESSIONS / sid / "controlled_action_v2.json").read_text(encoding="utf-8")
        )
        # Backfill raw net if older schema
        if full.get("E_net_raw_j") is None and full.get("E_net_j") is not None:
            full["E_net_raw_j"] = full["E_net_j"]
        if full.get("P_mean_from_E_w") is None:
            eg = full.get("E_generate_j")
            dt = full.get("delta_t_generate_s")
            if eg is not None and dt:
                full["P_mean_from_E_w"] = float(eg) / float(dt)
        rows.append(full)
    ev = evaluate_control_repeats(rows)
    rep["evaluation"] = ev
    rep["diagnosis"] = {
        "windowing_fixed": (
            ev.get("mean_integration_wall_ratio") is not None
            and 0.85 <= float(ev["mean_integration_wall_ratio"]) <= 1.25
        ),
        "outcome": ev.get("outcome"),
        "net_attribution": ev.get("net_attribution"),
        "gross_authority": ev.get("gross_authority"),
        "SNR_net": ev.get("SNR_net"),
        "note": (
            "Measurement resolution, not workload instability. "
            "Gross E_generate repeatable; net below SNR/resolution floor."
        ),
    }
    p.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    lines = [
        "# Control validation: tokens_short__warm_repeat",
        "",
        f"- **Outcome:** `{ev.get('outcome')}`",
        f"- **Net attribution:** `{ev.get('net_attribution')}`",
        f"- **Gross authority:** `{ev.get('gross_authority')}`",
        f"- **SNR_net:** {ev.get('SNR_net')} (ok={ev.get('SNR_net_ok')})",
        f"- **CV_E (net):** {ev.get('CV_E')} (null when below resolution — correct)",
        f"- **CV_E_generate:** {ev.get('CV_E_generate')} (μ={ev.get('mu_E_generate_j')})",
        f"- **CV_P ({ev.get('CV_P_metric')}):** {ev.get('CV_P')}",
        f"- **mean integration/wall ratio:** {ev.get('mean_integration_wall_ratio')}",
        "- **Learning admission:** withheld",
        "- **Token matrix:** blocked until net resolution boundary found",
        "",
    ]
    (OUT / "control_validation_warm_repeat_latest.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(json.dumps({"evaluation": ev, "artifact": str(p).replace("\\", "/")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
