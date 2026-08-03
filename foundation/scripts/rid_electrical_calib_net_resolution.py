#!/usr/bin/env python3
"""Warm-repeat duration calibration: find net-energy resolution boundary.

Varies only num_predict under locked protocol (settle + warm residency).
Does not resume the token matrix. Learning remains withheld.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_calib_net_resolution.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_ledger_controls import (  # noqa: E402
    ControlCell,
    evaluate_control_repeats,
    run_controlled_v2,
)
from lib.rid_electrical_policy import LEARNING_ADMISSION_WITHHELD, policy_stamp  # noqa: E402

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
DEFAULT_LEVELS = (64, 128, 256, 512, 768)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--levels",
        default=",".join(str(x) for x in DEFAULT_LEVELS),
        help="Comma-separated num_predict values",
    )
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--gap-s", type=float, default=12.0)
    args = p.parse_args()
    levels = [int(x.strip()) for x in str(args.levels).split(",") if x.strip()]
    OUT.mkdir(parents=True, exist_ok=True)

    level_results: list[dict] = []
    boundary = None

    print(
        f"[calib] net-resolution sweep levels={levels} repeats={args.repeats}",
        flush=True,
    )
    for np_ in levels:
        cell = ControlCell(
            cell_id=f"calib_np{np_}__warm_repeat",
            residency="warm_repeat",
            num_predict=np_,
            token_bucket=f"calib_{np_}",
        )
        rows = []
        print(f"[calib] === num_predict={np_} ===", flush=True)
        for i in range(1, max(1, int(args.repeats)) + 1):
            print(f"[calib] np={np_} repeat {i}/{args.repeats}", flush=True)
            row = run_controlled_v2(cell, repeat_i=i)
            rows.append(row)
            print(
                f"[calib] done E_gen={row.get('E_generate_j')} "
                f"E_net_raw={row.get('E_net_raw_j')} "
                f"net={row.get('net_attribution')} "
                f"dt={row.get('delta_t_generate_s')} "
                f"n_samp={row.get('n_generate_locked_samples')} "
                f"peak_conf={row.get('P_peak_confidence')}",
                flush=True,
            )
            time.sleep(max(0.0, float(args.gap_s)))

        ev = evaluate_control_repeats(rows)
        entry = {
            "num_predict": np_,
            "cell_id": cell.cell_id,
            "n_repeats": len(rows),
            "evaluation": ev,
            "actions": [
                {
                    "repeat_i": r.get("repeat_i"),
                    "token_count": r.get("token_count"),
                    "E_generate_j": r.get("E_generate_j"),
                    "E_net_raw_j": r.get("E_net_raw_j"),
                    "E_net_j": r.get("E_net_j"),
                    "E_tail_j": r.get("E_tail_j"),
                    "delta_t_generate_s": r.get("delta_t_generate_s"),
                    "n_generate_locked_samples": r.get("n_generate_locked_samples"),
                    "P_peak_generate_w": r.get("P_peak_generate_w"),
                    "P_peak_confidence": r.get("P_peak_confidence"),
                    "P_mean_from_E_w": r.get("P_mean_from_E_w"),
                    "net_attribution": r.get("net_attribution"),
                    "control_gates": {
                        "integration_wall_ratio": (r.get("control_gates") or {}).get(
                            "integration_wall_ratio"
                        ),
                        "CV_P_idle": (r.get("control_gates") or {}).get("CV_P_idle"),
                        "settle_ok": (r.get("control_gates") or {}).get("settle_ok"),
                    },
                    "session_id": r.get("session_id"),
                }
                for r in rows
            ],
        }
        level_results.append(entry)
        print(
            f"[calib] np={np_} outcome={ev.get('outcome')} "
            f"SNR={ev.get('SNR_net')} CV_E={ev.get('CV_E')} "
            f"CV_P={ev.get('CV_P')}({ev.get('CV_P_metric')}) "
            f"CV_Egen={ev.get('CV_E_generate')}",
            flush=True,
        )
        if boundary is None and ev.get("outcome") == "net_signature_repeatable":
            boundary = {
                "num_predict_min": np_,
                "mu_delta_t_s": (
                    sum(
                        float(a["delta_t_generate_s"] or 0)
                        for a in entry["actions"]
                    )
                    / max(1, len(entry["actions"]))
                ),
                "evaluation": ev,
            }
            print(f"[calib] RESOLUTION BOUNDARY FOUND at num_predict={np_}", flush=True)

    report = {
        "ok": True,
        "at": _utc(),
        "protocol": "rid_electrical_ledger_controls_v2",
        "experiment": "net_resolution_calibration_warm_repeat",
        "levels": levels,
        "repeats_per_level": int(args.repeats),
        "resolution_boundary": boundary,
        "level_results": level_results,
        "learning_admission_withheld": LEARNING_ADMISSION_WITHHELD,
        "token_matrix": (
            "resume_only_above_boundary"
            if boundary
            else "blocked_boundary_not_found"
        ),
        "policy": policy_stamp(),
        "accounting_rule": {
            "short_below_boundary": "E_generate_gross authoritative; E_net=null/below_resolution",
            "at_or_above_boundary": "E_net may be authoritative when net_signature_repeatable",
            "tail": "separate E_post_action; never folded into E_net",
        },
    }
    jpath = OUT / "net_resolution_calibration_latest.json"
    mpath = OUT / "net_resolution_calibration_latest.md"
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# Net-energy resolution calibration (warm_repeat)",
        "",
        f"- **Boundary:** "
        + (
            f"`num_predict>={boundary['num_predict_min']}` "
            f"(~{boundary['mu_delta_t_s']:.2f}s)"
            if boundary
            else "`not found in sweep`"
        ),
        f"- **Token matrix:** `{report['token_matrix']}`",
        "- **Learning admission:** withheld",
        "",
        "## Levels",
        "",
    ]
    for lr in level_results:
        ev = lr["evaluation"]
        lines.append(
            f"- np={lr['num_predict']}: outcome=`{ev.get('outcome')}` "
            f"net=`{ev.get('net_attribution')}` "
            f"SNR={ev.get('SNR_net')} "
            f"CV_E={ev.get('CV_E')} CV_P={ev.get('CV_P')} "
            f"CV_Egen={ev.get('CV_E_generate')} "
            f"μE_net_raw={ev.get('mu_E_net_raw_j')} "
            f"μE_gen={ev.get('mu_E_generate_j')}"
        )
    lines.append("")
    mpath.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "boundary": boundary,
                "artifact": str(jpath).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0 if boundary else 2


if __name__ == "__main__":
    raise SystemExit(main())
