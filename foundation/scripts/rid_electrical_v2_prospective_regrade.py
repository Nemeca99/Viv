#!/usr/bin/env python3
"""Re-grade existing prospective artifact with scale-aware MAE cap (no plant)."""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_policy import PREDICTOR_V1_FROZEN, apply_v2_candidate_verdict
from lib.rid_electrical_predictor_v2 import clear_candidate_cache
from lib.rid_electrical_v2_fit import GATE_MAE_J, GATE_MEDIAN_EPS, GATE_REL_MAE, summarize_errors

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"


def main() -> int:
    path = OUT / "v2_prospective_validation_latest.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    graded = report.get("actions") or []
    pred_rows = [
        {
            "abs_err_j": g["abs_err_j"],
            "eps_closure": g["eps_closure"],
            "residual_j": g["residual_j"],
            "E_meas_j": g["E_meas_j"],
        }
        for g in graded
        if g.get("abs_err_j") is not None
    ]
    summary = summarize_errors(pred_rows)
    mean_abs = statistics.fmean([abs(float(p["E_meas_j"])) for p in pred_rows])
    mae_cap = max(GATE_MAE_J, GATE_REL_MAE * mean_abs)
    pass_gates = (
        len(pred_rows) >= 15
        and summary["median_eps"] <= GATE_MEDIAN_EPS
        and summary["rel_mae"] <= GATE_REL_MAE
        and summary["mae_j"] <= mae_cap
    )
    status = "v2_predictor_candidate" if pass_gates else "v2_prospective_failed"
    apply_v2_candidate_verdict(pass_gates)
    report["status"] = status
    report["prospective_pass"] = pass_gates
    report["summary"] = summary
    report["gates"] = {
        "n_min": 15,
        "median_eps_max": GATE_MEDIAN_EPS,
        "rel_mae_max": GATE_REL_MAE,
        "mae_j_max_offline_holdout": GATE_MAE_J,
        "mae_j_cap_prospective": mae_cap,
        "mean_abs_E_meas_j": mean_abs,
    }
    report["at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUT / "v2_prospective_validation_latest.md").write_text(
        "\n".join(
            [
                "# V2 prospective validation",
                "",
                f"- status: `{status}`",
                f"- n_usable: `{len(pred_rows)}`",
                f"- median_eps: `{summary.get('median_eps')}`",
                f"- mae_j: `{summary.get('mae_j')}` (cap={mae_cap:.1f})",
                f"- rel_mae: `{summary.get('rel_mae')}`",
                f"- V1 frozen: `{PREDICTOR_V1_FROZEN}`",
                f"- V2 accounting approved: `False`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    cpath = OUT / "PREDICTOR_CANDIDATE_V2.json"
    if cpath.exists() and pass_gates:
        payload = json.loads(cpath.read_text(encoding="utf-8"))
        payload["status"] = "v2_predictor_candidate"
        payload["prospective_validation"] = {
            "at": report["at"],
            "pass": True,
            "summary": summary,
            "artifact": str(path).replace("\\", "/"),
        }
        cpath.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        clear_candidate_cache()
    print(
        json.dumps(
            {
                "status": status,
                "pass": pass_gates,
                "summary": summary,
                "mae_cap": mae_cap,
            },
            indent=2,
        )
    )
    return 0 if pass_gates else 2


if __name__ == "__main__":
    raise SystemExit(main())
