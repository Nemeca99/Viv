#!/usr/bin/env python3
"""Validate tokens_short__warm_repeat under control protocol v2 (default 5 repeats).

Does not resume the legacy matrix. Learning remains withheld.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_validate_warm_repeat.py --repeats 5
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


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--gap-s", type=float, default=15.0)
    p.add_argument(
        "--residency",
        choices=("warm_repeat", "cold_first"),
        default="warm_repeat",
    )
    args = p.parse_args()
    cell = ControlCell(
        cell_id=f"tokens_short__{args.residency}",
        residency=args.residency,
    )
    rows = []
    print(
        f"[ctrl-v2] validate cell={cell.cell_id} repeats={args.repeats}",
        flush=True,
    )
    for i in range(1, max(1, int(args.repeats)) + 1):
        print(f"[ctrl-v2] repeat {i}/{args.repeats}", flush=True)
        row = run_controlled_v2(cell, repeat_i=i)
        rows.append(row)
        g = row.get("control_gates") or {}
        print(
            f"[ctrl-v2] done E_net={row.get('E_net_j')} tokens={row.get('token_count')} "
            f"ratio={g.get('integration_wall_ratio')} settle={g.get('settle_ok')} "
            f"idle_cv={g.get('CV_P_idle')}",
            flush=True,
        )
        time.sleep(max(0.0, float(args.gap_s)))

    ev = evaluate_control_repeats(rows)
    report = {
        "ok": True,
        "at": _utc(),
        "protocol": "rid_electrical_ledger_controls_v2",
        "cell": cell.to_dict(),
        "n_repeats": len(rows),
        "evaluation": ev,
        "actions": [
            {
                "repeat_i": r.get("repeat_i"),
                "token_count": r.get("token_count"),
                "E_generate_j": r.get("E_generate_j"),
                "E_tail_j": r.get("E_tail_j"),
                "E_net_j": r.get("E_net_j"),
                "P_idle_stable_w": r.get("P_idle_stable_w"),
                "P_peak_generate_w": r.get("P_peak_generate_w"),
                "delta_t_generate_s": r.get("delta_t_generate_s"),
                "delta_t_ollama_s": r.get("delta_t_ollama_s"),
                "control_gates": r.get("control_gates"),
                "infer_timing": {
                    "ttft_s": (r.get("infer") or {}).get("ttft_s"),
                    "wall_s": (r.get("infer") or {}).get("wall_s"),
                    "load_duration_s": (r.get("infer") or {}).get("load_duration_s"),
                    "prompt_eval_duration_s": (r.get("infer") or {}).get(
                        "prompt_eval_duration_s"
                    ),
                    "eval_duration_s": (r.get("infer") or {}).get("eval_duration_s"),
                    "total_duration_s": (r.get("infer") or {}).get("total_duration_s"),
                },
                "session_id": r.get("session_id"),
            }
            for r in rows
        ],
        "learning_admission_withheld": LEARNING_ADMISSION_WITHHELD,
        "legacy_sequential_campaign": "forensic_only_halted",
        "policy": policy_stamp(),
        "next": (
            "If outcome=repeatable_signature, resume token-length cells under the "
            "same residency/thermal controls. Else tighten settle/window further."
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    jpath = OUT / "control_validation_warm_repeat_latest.json"
    mpath = OUT / "control_validation_warm_repeat_latest.md"
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Control validation: tokens_short__warm_repeat",
        "",
        f"- **Outcome:** `{ev.get('outcome')}`",
        f"- **n_usable:** {ev.get('n_usable')}",
        f"- **CV_E:** {ev.get('CV_E')}",
        f"- **CV_P:** {ev.get('CV_P')}",
        f"- **mean integration/wall ratio:** {ev.get('mean_integration_wall_ratio')}",
        f"- **Learning admission:** withheld",
        "",
        "## Repeats",
        "",
    ]
    for a in report["actions"]:
        lines.append(
            f"- r{a['repeat_i']}: tokens={a['token_count']} "
            f"E_net={a['E_net_j']} E_gen={a['E_generate_j']} E_tail={a['E_tail_j']} "
            f"ratio={(a.get('control_gates') or {}).get('integration_wall_ratio')} "
            f"load={(a.get('infer_timing') or {}).get('load_duration_s')}"
        )
    lines.append("")
    mpath.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"evaluation": ev, "artifact": str(jpath).replace("\\", "/")}, indent=2))
    # Short-cell success: gross repeatable with net below resolution is expected.
    ok_outcomes = {"gross_signature_repeatable", "net_signature_repeatable"}
    return 0 if ev.get("outcome") in ok_outcomes else 2


if __name__ == "__main__":
    raise SystemExit(main())
