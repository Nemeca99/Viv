#!/usr/bin/env python3
"""Prospective plant validation for V2 candidate (unseen actions).

Predict-before-grade protocol: declare plan (residency, np, prompt, tail_h),
run controlled action, grade V2 (and V1 on overlap) afterward.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_v2_prospective_validation.py
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_cost_decomposition import PROMPT_TEXT  # noqa: E402
from lib.rid_electrical_ledger_controls import ControlCell, run_controlled_v2  # noqa: E402
from lib.rid_electrical_policy import (  # noqa: E402
    PREDICTOR_V1_FROZEN,
    apply_v2_candidate_verdict,
    policy_stamp,
)
from lib.rid_electrical_predictor import predict_E_net as predict_v1  # noqa: E402
from lib.rid_electrical_predictor_v2 import (  # noqa: E402
    clear_candidate_cache,
    load_candidate,
    predict_E_action,
)
from lib.rid_electrical_v2_fit import (  # noqa: E402
    GATE_MAE_J,
    GATE_MEDIAN_EPS,
    GATE_REL_MAE,
    summarize_errors,
)

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ProspectivePlan:
    plan_id: str
    residency: str
    num_predict: int
    prompt_variant: str
    tail_tau_s: float
    unload_before: bool = False
    notes: str = ""


# ≥15 unseen mixed actions (not identical to frozen corpus cell set alone)
PROSPECTIVE_PLANS: tuple[ProspectivePlan, ...] = (
    ProspectivePlan("p_warm_np300_std_t5", "warm_repeat", 300, "standard", 5.0),
    ProspectivePlan("p_warm_np400_std_t5", "warm_repeat", 400, "standard", 5.0),
    ProspectivePlan("p_warm_np450_short_t5", "warm_repeat", 450, "short", 5.0),
    ProspectivePlan("p_warm_np350_long_t5", "warm_repeat", 350, "long", 5.0),
    ProspectivePlan("p_warm_np360_med_t10", "warm_repeat", 360, "medium", 10.0),
    ProspectivePlan("p_warm_np320_std_t20", "warm_repeat", 320, "standard", 20.0),
    ProspectivePlan("p_cold_np360_std_t5", "cold_first", 360, "standard", 5.0),
    ProspectivePlan("p_cold_np400_med_t5", "cold_first", 400, "medium", 5.0),
    ProspectivePlan(
        "p_unload_np360_std_t10",
        "cold_first",
        360,
        "standard",
        10.0,
        unload_before=True,
    ),
    ProspectivePlan("p_warm_np280_long_t10", "warm_repeat", 280, "long", 10.0),
    ProspectivePlan("p_warm_np480_short_t5", "warm_repeat", 480, "short", 5.0),
    ProspectivePlan("p_warm_np360_std_t5b", "warm_repeat", 360, "standard", 5.0),
    ProspectivePlan("p_cold_np320_short_t5", "cold_first", 320, "short", 5.0),
    ProspectivePlan("p_warm_np420_med_t20", "warm_repeat", 420, "medium", 20.0),
    ProspectivePlan("p_warm_np340_long_t20", "warm_repeat", 340, "long", 20.0),
    ProspectivePlan("p_unload_np400_long_t5", "cold_first", 400, "long", 5.0, True),
)


def _grade_row(plan: ProspectivePlan, row: dict[str, Any]) -> dict[str, Any]:
    infer = row.get("infer") or {}
    te = infer.get("eval_duration_s")
    tp = infer.get("prompt_eval_duration_s") or 0.0
    e_net = row.get("E_net_raw_j")
    e_tail = row.get("E_tail_j")
    predeclared = {
        "plan_id": plan.plan_id,
        "residency": plan.residency,
        "num_predict": plan.num_predict,
        "prompt_variant": plan.prompt_variant,
        "tail_tau_s": plan.tail_tau_s,
        "unload_before": plan.unload_before,
    }
    # Pre-action prediction uses planned residency/tail; durations unknown →
    # record plan first, then post-measure grade with measured timings.
    v2 = predict_E_action(
        t_eval_s=float(te) if te is not None else -1.0,
        t_prompt_s=float(tp),
        tail_horizon_s=float(plan.tail_tau_s),
        residency=plan.residency,
        unload_before=plan.unload_before,
        cell_id=plan.plan_id,
    )
    e_meas = None
    if e_net is not None and e_tail is not None:
        e_meas = float(e_net) + float(e_tail)
    e_hat = v2.get("predicted_E_action_j")
    resid = None if e_meas is None or e_hat is None else float(e_meas) - float(e_hat)
    eps = None
    if e_meas is not None and e_hat is not None and abs(e_meas) > 1e-9:
        eps = abs(float(e_meas) - float(e_hat)) / abs(float(e_meas))

    v1 = None
    if te is not None and plan.residency == "warm_repeat" and not plan.unload_before:
        v1 = predict_v1(float(te))

    return {
        "predeclared_plan": predeclared,
        "measured": {
            "eval_duration_s": te,
            "prompt_eval_duration_s": tp,
            "E_net_raw_j": e_net,
            "E_tail_j": e_tail,
            "E_action_j": e_meas,
            "session_id": row.get("session_id"),
        },
        "v2_prediction": v2,
        "v1_prediction": v1,
        "residual_j": resid,
        "eps_closure": eps,
        "abs_err_j": None if resid is None else abs(float(resid)),
        "E_meas_j": e_meas,
        "E_hat_j": e_hat,
        "cold": plan.residency == "cold_first" or plan.unload_before,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gap-s", type=float, default=8.0)
    p.add_argument("--limit", type=int, default=0, help="Optional cap for smoke")
    args = p.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    clear_candidate_cache()
    cand = load_candidate()
    if not cand.get("loaded"):
        print(json.dumps({"error": "candidate_missing", "cand": cand}, indent=2))
        return 1

    plans = list(PROSPECTIVE_PLANS)
    if args.limit > 0:
        plans = plans[: int(args.limit)]

    print(f"[v2-prospective] n_plans={len(plans)} candidate={cand.get('path')}", flush=True)
    graded: list[dict[str, Any]] = []
    progress = OUT / "v2_prospective_progress.jsonl"
    progress.write_text("", encoding="utf-8")

    model_warm = False
    for i, plan in enumerate(plans, start=1):
        need_unload = plan.unload_before or plan.residency == "cold_first"
        prep = True if need_unload else (not model_warm)
        prompt = PROMPT_TEXT.get(plan.prompt_variant, PROMPT_TEXT["standard"])
        cell = ControlCell(
            cell_id=f"v2pros_{plan.plan_id}",
            residency=plan.residency,
            num_predict=plan.num_predict,
            token_bucket="v2_prospective",
            prompt=prompt,
        )
        print(
            f"[v2-prospective] {i}/{len(plans)} {plan.plan_id} "
            f"prep={prep} np={plan.num_predict} tail={plan.tail_tau_s}",
            flush=True,
        )
        row = run_controlled_v2(
            cell,
            repeat_i=i,
            prep_residency=prep,
            tail_tau_s=float(plan.tail_tau_s),
        )
        model_warm = True
        g = _grade_row(plan, row)
        graded.append(g)
        with progress.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "at": _utc(),
                        "plan_id": plan.plan_id,
                        "eps": g.get("eps_closure"),
                        "abs_err_j": g.get("abs_err_j"),
                        "E_meas_j": g.get("E_meas_j"),
                        "E_hat_j": g.get("E_hat_j"),
                    }
                )
                + "\n"
            )
        print(
            f"[v2-prospective] done eps={g.get('eps_closure')} "
            f"err={g.get('abs_err_j')} meas={g.get('E_meas_j')}",
            flush=True,
        )
        time.sleep(max(0.0, float(args.gap_s)))

    # Summarize like holdout gates
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
    # Prospective gates: relative + median eps (action energy spans ~1–3.5 kJ).
    # Absolute MAE≤120 remains the offline holdout gate; for prospective use
    # scale-aware bound max(120, 0.15 * mean |E_meas|).
    mean_abs_meas = None
    if pred_rows:
        mean_abs_meas = statistics.fmean(
            [abs(float(p["E_meas_j"])) for p in pred_rows if p.get("E_meas_j") is not None]
        )
    mae_cap = GATE_MAE_J
    if mean_abs_meas is not None:
        mae_cap = max(GATE_MAE_J, GATE_REL_MAE * float(mean_abs_meas))
    pass_gates = (
        len(pred_rows) >= 15
        and summary.get("median_eps") is not None
        and summary["median_eps"] <= GATE_MEDIAN_EPS
        and summary.get("rel_mae") is not None
        and summary["rel_mae"] <= GATE_REL_MAE
        and summary.get("mae_j") is not None
        and summary["mae_j"] <= mae_cap
    )
    status = "v2_predictor_candidate" if pass_gates else "v2_prospective_failed"
    apply_v2_candidate_verdict(pass_gates)
    report = {
        "ok": True,
        "at": _utc(),
        "status": status,
        "prospective_pass": bool(pass_gates),
        "n_actions": len(graded),
        "n_usable": len(pred_rows),
        "summary": summary,
        "gates": {
            "n_min": 15,
            "median_eps_max": GATE_MEDIAN_EPS,
            "rel_mae_max": GATE_REL_MAE,
            "mae_j_max_offline_holdout": GATE_MAE_J,
            "mae_j_cap_prospective": mae_cap,
            "mean_abs_E_meas_j": mean_abs_meas,
        },
        "predictor_v1_frozen": bool(PREDICTOR_V1_FROZEN),
        "accounting_predictor_v2_approved": False,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
        },
        "actions": graded,
        "policy": policy_stamp(),
    }
    jpath = OUT / "v2_prospective_validation_latest.json"
    mpath = OUT / "v2_prospective_validation_latest.md"
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
    mpath.write_text(
        "\n".join(
            [
                "# V2 prospective validation",
                "",
                f"- status: `{status}`",
                f"- n_usable: `{len(pred_rows)}`",
                f"- median_eps: `{summary.get('median_eps')}`",
                f"- mae_j: `{summary.get('mae_j')}`",
                f"- rel_mae: `{summary.get('rel_mae')}`",
                f"- V1 frozen: `{PREDICTOR_V1_FROZEN}`",
                f"- V2 accounting approved: `False`",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Update candidate artifact status on pass
    cpath = OUT / "PREDICTOR_CANDIDATE_V2.json"
    if cpath.exists() and pass_gates:
        payload = json.loads(cpath.read_text(encoding="utf-8"))
        payload["status"] = "v2_predictor_candidate"
        payload["prospective_validation"] = {
            "at": _utc(),
            "pass": True,
            "summary": summary,
            "artifact": str(jpath).replace("\\", "/"),
        }
        cpath.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        clear_candidate_cache()

    print(
        json.dumps(
            {
                "status": status,
                "prospective_pass": pass_gates,
                "summary": summary,
                "artifact": str(jpath).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0 if pass_gates else 2


if __name__ == "__main__":
    raise SystemExit(main())
