#!/usr/bin/env python3
"""Prospective validation: eval_duration_s -> E_net under fixed controls.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_eval_duration_validation.py

Five duration targets × 5 rotated sessions. Session-level holdout for fit eval.
Learning admission withheld. No Master routing.
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
from lib.rid_electrical_eval_duration_validation import (  # noqa: E402
    DURATION_TARGETS_S,
    build_session_orders,
    enrich_action_row,
    evaluate_validation_campaign,
    make_duration_cells,
    rotation_coverage,
)
from lib.rid_electrical_ledger_controls import run_controlled_v2  # noqa: E402
from lib.rid_electrical_policy import LEARNING_ADMISSION_WITHHELD, policy_stamp  # noqa: E402

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append_progress(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sessions", type=int, default=5)
    p.add_argument("--gap-s", type=float, default=12.0)
    p.add_argument(
        "--holdout-sessions",
        type=str,
        default="",
        help="Comma-separated session indices to hold out (default: last 40%)",
    )
    p.add_argument(
        "--dry-eval-from",
        type=str,
        default="",
        help="Skip plant run; evaluate from an existing campaign JSON path",
    )
    args = p.parse_args()

    cells = make_duration_cells(DURATION_TARGETS_S)
    n_sessions = max(1, int(args.sessions))
    orders = build_session_orders(cells, n_sessions=n_sessions)
    cov = rotation_coverage(orders)
    if not cov.get("ok"):
        print(json.dumps({"error": "rotation_coverage_failed", "coverage": cov}, indent=2))
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    progress_path = OUT / "eval_duration_validation_progress.jsonl"

    holdout_sessions = None
    if args.holdout_sessions.strip():
        holdout_sessions = [int(x) for x in args.holdout_sessions.split(",") if x.strip()]

    if args.dry_eval_from:
        prior = json.loads(Path(args.dry_eval_from).read_text(encoding="utf-8"))
        action_rows = [enrich_action_row(a) for a in (prior.get("actions") or [])]
    else:
        progress_path.write_text("", encoding="utf-8")
        print(
            f"[eval-dur-val] targets={list(DURATION_TARGETS_S)}s "
            f"np={[c.num_predict for c in cells]} sessions={n_sessions} "
            f"learning_withheld={LEARNING_ADMISSION_WITHHELD}",
            flush=True,
        )
        action_rows = []
        for session_i, order in enumerate(orders, start=1):
            print(
                f"[eval-dur-val] === session {session_i}/{n_sessions} "
                f"order={[c.cell_id for c in order]} ===",
                flush=True,
            )
            for order_i, dcell in enumerate(order, start=1):
                print(
                    f"[eval-dur-val] S{session_i} order{order_i}: "
                    f"target={dcell.target_eval_s}s np={dcell.num_predict}",
                    flush=True,
                )
                row = run_controlled_v2(
                    dcell.to_control_cell(),
                    repeat_i=session_i,
                    prep_residency=(order_i == 1),
                )
                row = enrich_action_row(row, target_eval_s=dcell.target_eval_s)
                row["session_i"] = session_i
                row["order_i"] = order_i
                row["num_predict"] = dcell.num_predict
                row["target_eval_s"] = dcell.target_eval_s
                row["cell_id"] = dcell.cell_id
                action_rows.append(row)
                _append_progress(
                    progress_path,
                    {
                        "at": _utc(),
                        "session_i": session_i,
                        "order_i": order_i,
                        "target_eval_s": dcell.target_eval_s,
                        "num_predict": dcell.num_predict,
                        "cell_id": dcell.cell_id,
                        "eval_duration_s": row.get("eval_duration_s"),
                        "E_net_raw_j": row.get("E_net_raw_j"),
                        "session_id": row.get("session_id"),
                    },
                )
                print(
                    f"[eval-dur-val] done eval_dur={row.get('eval_duration_s')} "
                    f"E_net={row.get('E_net_raw_j')} net={row.get('net_attribution')}",
                    flush=True,
                )
                time.sleep(max(0.0, float(args.gap_s)))

    evaluation = evaluate_validation_campaign(
        action_rows, holdout_sessions=holdout_sessions
    )
    decision = (evaluation.get("decision") or {}).get("decision")

    report = {
        "ok": True,
        "at": _utc(),
        "protocol": "rid_electrical_eval_duration_validation_v1",
        "hypothesis": "E_net ~= alpha + beta * eval_duration_s",
        "duration_targets_s": list(DURATION_TARGETS_S),
        "cells": [
            {
                "cell_id": c.cell_id,
                "target_eval_s": c.target_eval_s,
                "num_predict": c.num_predict,
            }
            for c in cells
        ],
        "session_orders": [[c.cell_id for c in o] for o in orders],
        "gap_s": float(args.gap_s) if not args.dry_eval_from else None,
        "evaluation": evaluation,
        "actions": [
            {
                "session_i": r.get("session_i"),
                "order_i": r.get("order_i"),
                "cell_id": r.get("cell_id"),
                "target_eval_s": r.get("target_eval_s"),
                "num_predict": r.get("num_predict"),
                "eval_duration_s": r.get("eval_duration_s"),
                "actual_eval_tokens": r.get("actual_eval_tokens")
                or (r.get("infer") or {}).get("eval_count"),
                "E_generate_j": r.get("E_generate_j"),
                "E_net_raw_j": r.get("E_net_raw_j"),
                "E_net_j": r.get("E_net_j"),
                "P_mean_from_E_w": r.get("P_mean_from_E_w"),
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
            }
            for r in action_rows
        ],
        "learning_admission_withheld": True,
        "auto_admit": False,
        "predictor_authorized": False,
        "master_routing_authorized": False,
        "policy": policy_stamp(),
    }

    jpath = OUT / "eval_duration_validation_latest.json"
    mpath = OUT / "eval_duration_validation_latest.md"
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")

    fit = evaluation.get("fit_train") or {}
    held = evaluation.get("heldout_metrics") or {}
    stab = evaluation.get("stability") or {}
    dec = evaluation.get("decision") or {}
    lines = [
        "# Eval duration -> E_net validation",
        "",
        f"- **Decision:** `{dec.get('decision')}`",
        f"- **Train fit:** alpha={fit.get('alpha')} beta={fit.get('beta')} r2={fit.get('r2')} n={fit.get('n')}",
        f"- **Held-out MAE (J):** {held.get('mae_j')}",
        f"- **Held-out mean abs rel err:** {held.get('mean_abs_rel_error')}",
        f"- **Error grows with duration:** {held.get('error_grows_with_duration')}",
        f"- **Beta stability CV:** {stab.get('beta_cv')}",
        f"- **Alpha stability CV:** {stab.get('alpha_cv')}",
        f"- **Alpha diagnostic:** {(evaluation.get('alpha_diagnostic') or {}).get('note')}",
        "- **Learning admission:** withheld (`auto_admit=false`)",
        "- **Master routing:** not authorized",
        "",
        "## Cell gates",
        "",
    ]
    for cid, rep in sorted((evaluation.get("cell_reports") or {}).items()):
        lines.append(
            f"- `{cid}`: outcome=`{rep.get('outcome')}` "
            f"mu_teval={rep.get('mu_eval_duration_s')} "
            f"SNR={rep.get('SNR_net')} CV_E={rep.get('CV_E')} "
            f"CV_P={rep.get('CV_P')} mu_E={rep.get('mu_E_net_raw_j')}"
        )
    lines.append("")
    lines.append("## Decision note")
    lines.append("")
    lines.append(str(dec.get("note") or ""))
    lines.append("")
    mpath.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "decision": decision,
                "train_r2": fit.get("r2"),
                "heldout_mae_j": held.get("mae_j"),
                "heldout_rel": held.get("mean_abs_rel_error"),
                "beta": fit.get("beta"),
                "alpha": fit.get("alpha"),
                "artifact": str(jpath).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
