#!/usr/bin/env python3
"""Run token-energy matrix v2 (rotated warm-repeat sessions).

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_token_matrix_v2.py
  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_token_matrix_v2.py --with-forensic-768

Learning remains withheld. 768 is forensic-only when enabled.
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
from lib.rid_electrical_ledger_controls import run_controlled_v2  # noqa: E402
from lib.rid_electrical_policy import LEARNING_ADMISSION_WITHHELD, policy_stamp  # noqa: E402
from lib.rid_electrical_token_matrix import (  # noqa: E402
    ADMISSION_NUM_PREDICT,
    FORENSIC_NUM_PREDICT,
    SESSION_ORDERS,
    evaluate_token_matrix,
    make_cell,
    rotation_coverage,
    write_token_cost_curve_review,
)

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append_progress(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--sessions",
        type=int,
        default=len(SESSION_ORDERS),
        help="Number of rotated sessions (default 5)",
    )
    p.add_argument("--gap-s", type=float, default=12.0)
    p.add_argument(
        "--with-forensic-768",
        action="store_true",
        help="After admission matrix, run 768 forensic cell × sessions (excluded from admission)",
    )
    p.add_argument(
        "--forensic-repeats",
        type=int,
        default=3,
        help="Repeats for forensic 768 cell when enabled",
    )
    args = p.parse_args()

    cov = rotation_coverage()
    if not cov.get("ok"):
        print(json.dumps({"error": "rotation_coverage_failed", "coverage": cov}, indent=2))
        return 1

    n_sessions = max(1, min(int(args.sessions), len(SESSION_ORDERS)))
    orders = SESSION_ORDERS[:n_sessions]
    OUT.mkdir(parents=True, exist_ok=True)
    progress_path = OUT / "token_matrix_v2_progress.jsonl"
    # truncate progress for this run
    progress_path.write_text("", encoding="utf-8")

    print(
        f"[token-matrix-v2] sessions={n_sessions} cells={list(ADMISSION_NUM_PREDICT)} "
        f"cv_p=mean_from_E learning_withheld={LEARNING_ADMISSION_WITHHELD}",
        flush=True,
    )
    print(
        "[token-matrix-v2] note: np=256 is min validated pass point — not np>=256 blanket",
        flush=True,
    )

    admission_rows: list[dict] = []
    for session_i, order in enumerate(orders, start=1):
        print(f"[token-matrix-v2] === session {session_i}/{n_sessions} order={order} ===", flush=True)
        for order_i, np_ in enumerate(order, start=1):
            cell = make_cell(np_)
            # repeat_i == session_i so each cell gets one action per session
            print(
                f"[token-matrix-v2] S{session_i} order{order_i}: np={np_} cell={cell.cell_id}",
                flush=True,
            )
            # Warm once per session (first cell only); later cells stay warm-resident.
            row = run_controlled_v2(
                cell,
                repeat_i=session_i,
                prep_residency=(order_i == 1),
            )
            row["session_i"] = session_i
            row["order_i"] = order_i
            row["num_predict"] = np_
            row["matrix_role"] = "admission"
            admission_rows.append(row)
            _append_progress(
                progress_path,
                {
                    "at": _utc(),
                    "session_i": session_i,
                    "order_i": order_i,
                    "num_predict": np_,
                    "cell_id": cell.cell_id,
                    "E_net_raw_j": row.get("E_net_raw_j"),
                    "E_generate_j": row.get("E_generate_j"),
                    "delta_t_generate_s": row.get("delta_t_generate_s"),
                    "net_attribution": row.get("net_attribution"),
                    "session_id": row.get("session_id"),
                },
            )
            print(
                f"[token-matrix-v2] done E_gen={row.get('E_generate_j')} "
                f"E_net_raw={row.get('E_net_raw_j')} dt={row.get('delta_t_generate_s')} "
                f"net={row.get('net_attribution')}",
                flush=True,
            )
            time.sleep(max(0.0, float(args.gap_s)))

    forensic_rows: list[dict] = []
    if args.with_forensic_768:
        cell = make_cell(FORENSIC_NUM_PREDICT, forensic=True)
        n_f = max(1, int(args.forensic_repeats))
        print(
            f"[token-matrix-v2] === forensic np=768 ×{n_f} (excluded from admission) ===",
            flush=True,
        )
        for i in range(1, n_f + 1):
            row = run_controlled_v2(cell, repeat_i=i)
            row["session_i"] = None
            row["order_i"] = None
            row["num_predict"] = FORENSIC_NUM_PREDICT
            row["matrix_role"] = "forensic"
            forensic_rows.append(row)
            _append_progress(
                progress_path,
                {
                    "at": _utc(),
                    "role": "forensic",
                    "num_predict": FORENSIC_NUM_PREDICT,
                    "repeat_i": i,
                    "E_net_raw_j": row.get("E_net_raw_j"),
                    "session_id": row.get("session_id"),
                },
            )
            time.sleep(max(0.0, float(args.gap_s)))

    summary = evaluate_token_matrix(admission_rows, forensic_rows=forensic_rows or None)
    curve = write_token_cost_curve_review(summary, OUT)
    report = {
        "ok": True,
        "at": _utc(),
        "protocol": "rid_electrical_token_matrix_v2",
        "constraint": (
            "256 is minimum validated passing point — not proof every np≥256 passes"
        ),
        "session_orders": [list(o) for o in orders],
        "gap_s": float(args.gap_s),
        "evaluation": summary,
        "token_cost_curve_review": curve,
        "actions": [
            {
                "session_i": r.get("session_i"),
                "order_i": r.get("order_i"),
                "num_predict": r.get("num_predict"),
                "cell_id": (r.get("cell") or {}).get("cell_id"),
                "token_count": r.get("token_count"),
                "E_generate_j": r.get("E_generate_j"),
                "E_net_raw_j": r.get("E_net_raw_j"),
                "E_net_j": r.get("E_net_j"),
                "E_tail_j": r.get("E_tail_j"),
                "P_mean_from_E_w": r.get("P_mean_from_E_w"),
                "P_peak_generate_w": r.get("P_peak_generate_w"),
                "delta_t_generate_s": r.get("delta_t_generate_s"),
                "net_attribution": r.get("net_attribution"),
                "control_gates": {
                    "settle_ok": (r.get("control_gates") or {}).get("settle_ok"),
                    "integration_wall_ratio": (r.get("control_gates") or {}).get(
                        "integration_wall_ratio"
                    ),
                    "CV_P_idle": (r.get("control_gates") or {}).get("CV_P_idle"),
                },
                "session_id": r.get("session_id"),
                "matrix_role": r.get("matrix_role"),
            }
            for r in admission_rows + forensic_rows
        ],
        "learning_admission_withheld": True,
        "auto_admit": False,
        "predictor_authorized": False,
        "policy": policy_stamp(),
    }

    jpath = OUT / "token_matrix_v2_latest.json"
    mpath = OUT / "token_matrix_v2_latest.md"
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")

    ms = (summary.get("milestone") or {})
    cells = summary.get("cells") or {}
    lines = [
        "# Token matrix v2",
        "",
        f"- **Campaign decision:** `{ms.get('campaign_decision')}`",
        f"- **Repeatable cells:** {ms.get('repeatable_cell_ids')}",
        f"- **Unstable cells:** {ms.get('unstable_cell_ids')}",
        f"- **All pairs separable:** {ms.get('all_pairs_separable')}",
        f"- **Energy rises with np:** {(ms.get('energy_trend') or {}).get('energy_rises_with_np')}",
        "- **Learning admission:** withheld (`auto_admit=false`)",
        "- **Constraint:** 256 = min validated pass point, not ≥256 blanket",
        "",
        "## Cells",
        "",
    ]
    for cid, rep in sorted(cells.items()):
        lines.append(
            f"- `{cid}`: outcome=`{rep.get('outcome')}` "
            f"SNR={rep.get('SNR_net')} CV_E={rep.get('CV_E')} "
            f"CV_P={rep.get('CV_P')}({rep.get('CV_P_metric')}) "
            f"μE_net={rep.get('mu_E_net_raw_j')} forensic={rep.get('forensic')}"
        )
    lines.append("")
    lines.append("## Separability")
    lines.append("")
    for pair in (summary.get("separability") or {}).get("pairs") or []:
        lines.append(
            f"- {pair.get('a')} vs {pair.get('b')}: "
            f"Δμ={pair.get('abs_delta_mu_E')} pooled={pair.get('pooled_within_sigma_E')} "
            f"separable={pair.get('separable')}"
        )
    lines.append("")
    lines.append(str(ms.get("campaign_decision_note") or ""))
    lines.append("")
    mpath.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "campaign_decision": ms.get("campaign_decision"),
                "repeatable": ms.get("repeatable_cell_ids"),
                "artifact": str(jpath).replace("\\", "/"),
                "curve": (curve or {}).get("artifact_json") if curve else None,
            },
            indent=2,
        )
    )
    # Exit 0 for completed experiment regardless of milestone (evidence is valid).
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
