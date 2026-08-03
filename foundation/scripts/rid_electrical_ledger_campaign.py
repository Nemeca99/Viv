#!/usr/bin/env python3
"""Run controlled one-factor ledger campaign; learning stays withheld.

  # Smoke (subset, 1 repeat) — validates plumbing
  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_ledger_campaign.py --smoke --repeats 1

  # Full cell matrix, 3 independent repeats each
  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_ledger_campaign.py --repeats 3

  # Evaluate existing campaign actions only
  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_ledger_campaign.py --evaluate-only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_ledger_campaign import (  # noqa: E402
    CAMPAIGN_DIR,
    SESSIONS,
    campaign_matrix,
    run_controlled_action,
    summarize_campaign,
)
from lib.rid_electrical_policy import (  # noqa: E402
    LIFECYCLE,
    LEARNING_ADMISSION_WITHHELD,
    policy_stamp,
)

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
LATEST = OUT_DIR / "ledger_campaign_latest.json"
LATEST_MD = OUT_DIR / "ledger_campaign_latest.md"


def _load_existing_actions() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not SESSIONS.is_dir():
        return rows
    for d in sorted(SESSIONS.iterdir()):
        if not d.is_dir():
            continue
        p = d / "controlled_action.json"
        if not p.is_file():
            continue
        try:
            rows.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return rows


def _write_report(summary: dict[str, Any], *, ran: list[dict[str, Any]]) -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        **summary,
        "lifecycle_master_electrical": LIFECYCLE,
        "learning_admission_withheld_policy": LEARNING_ADMISSION_WITHHELD,
        "policy": policy_stamp(),
        "actions_ran_n": len(ran),
        "current_state": {
            "accounting_implemented": True,
            "measurements_valid": True,
            "cost_signatures_not_repeatable": summary.get("learning_admission", {})
            .get("n_repeatable_cells", 0)
            == 0,
            "learning_admission_withheld": True,
        },
    }
    LATEST.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    adm = payload.get("learning_admission") or {}
    lines = [
        "# Controlled ledger campaign",
        "",
        f"- **Experiment:** {payload.get('experiment_id')}",
        f"- **Actions:** {payload.get('n_actions')}",
        f"- **Cells:** {payload.get('n_cells')}",
        f"- **Campaign decision:** `{adm.get('campaign_decision')}`",
        f"- **Repeatable cells:** {adm.get('n_repeatable_cells')}",
        f"- **Cell outcomes:** {adm.get('cell_outcome_counts')}",
        f"- **Separable factors:** {adm.get('separable_factors')}",
        f"- **Learning admission:** withheld (auto_admit=false)",
        f"- **Predictor blocked:** true",
        "",
        "## State",
        "",
        "```",
        "accounting implemented + measurements valid",
        "+ cost signatures under CV test",
        "+ learning admission withheld",
        "```",
        "",
        "## Per-cell outcomes",
        "",
    ]
    for cid, rep in sorted((payload.get("cells") or {}).items()):
        lines.append(
            f"- **{cid}:** outcome=`{rep.get('outcome')}` n={rep.get('n_valid')} "
            f"CV_E={rep.get('CV_E')} CV_P={rep.get('CV_P')} "
            f"reasons={rep.get('outcome_reasons')}"
        )
    lines.append("")
    LATEST_MD.write_text("\n".join(lines), encoding="utf-8")
    payload["artifact_json"] = str(LATEST).replace("\\", "/")
    payload["artifact_md"] = str(LATEST_MD).replace("\\", "/")
    return payload


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--smoke", action="store_true", help="Short subset for plumbing validation")
    p.add_argument("--repeats", type=int, default=3, help="Independent repeats per cell")
    p.add_argument("--cadence", type=float, default=1.0)
    p.add_argument("--factor", type=str, default=None, help="Run only this factor")
    p.add_argument("--evaluate-only", action="store_true")
    p.add_argument(
        "--gap-s",
        type=float,
        default=20.0,
        help="Independence gap between actions (seconds)",
    )
    args = p.parse_args()

    ran: list[dict[str, Any]] = []
    if not args.evaluate_only:
        cells = campaign_matrix(smoke=bool(args.smoke))
        if args.factor:
            cells = [c for c in cells if c.factor == args.factor]
        repeats = 1 if args.smoke and int(args.repeats) < 1 else max(1, int(args.repeats))
        if args.smoke:
            repeats = min(repeats, 1)
        print(
            f"[ledger-campaign] cells={len(cells)} repeats={repeats} smoke={args.smoke}",
            flush=True,
        )
        for cell in cells:
            for r in range(1, repeats + 1):
                print(
                    f"[ledger-campaign] cell={cell.cell_id} repeat={r}/{repeats}",
                    flush=True,
                )
                row = run_controlled_action(
                    cell, repeat_i=r, cadence_s=float(args.cadence)
                )
                ran.append(row)
                print(
                    f"[ledger-campaign] done E_net={row.get('E_net_j')} "
                    f"tokens={row.get('token_count')} conf={row.get('confidence')}",
                    flush=True,
                )
                time.sleep(max(0.0, float(args.gap_s if not args.smoke else min(5.0, args.gap_s))))

    all_rows = _load_existing_actions()
    summary = summarize_campaign(all_rows)
    payload = _write_report(summary, ran=ran)
    slim = {
        k: payload[k]
        for k in (
            "ok",
            "at",
            "experiment_id",
            "n_actions",
            "n_cells",
            "learning_admission",
            "current_state",
            "predictor_blocked",
            "artifact_json",
            "artifact_md",
        )
        if k in payload
    }
    print(json.dumps(slim, indent=2), flush=True)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
