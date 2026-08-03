#!/usr/bin/env python3
"""Stratified V2 live-shadow plant campaign (n≥50, ≥10 per major stratum).

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_v2_live_shadow_campaign.py
"""
from __future__ import annotations

import argparse
import json
import random
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
from lib.rid_electrical_policy import PREDICTOR_V1_FROZEN, policy_stamp  # noqa: E402
from lib.rid_electrical_predictor import PLANT_CONFIG_ID  # noqa: E402
from lib.rid_electrical_predictor_registry import estimate_action  # noqa: E402
from lib.rid_electrical_v2_uncertainty import classify_strata  # noqa: E402

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ShadowPlan:
    plan_id: str
    residency: str
    num_predict: int
    prompt_variant: str
    tail_tau_s: float
    unload_before: bool = False
    request_prompt_decomposition: bool = False
    request_tail_accounting: bool = True


def build_plans() -> list[ShadowPlan]:
    """≥50 plans covering all strata with ≥10 membership each (overlapping)."""
    plans: list[ShadowPlan] = []
    # 12 cold across durations/prompts/tails
    cold_specs = [
        (280, "short", 5.0),
        (300, "standard", 5.0),
        (320, "medium", 5.0),
        (360, "long", 5.0),
        (400, "short", 10.0),
        (360, "standard", 10.0),
        (420, "medium", 10.0),
        (380, "long", 10.0),
        (300, "short", 20.0),
        (360, "standard", 20.0),
        (450, "medium", 20.0),
        (400, "long", 20.0),
    ]
    for i, (np_, pv, th) in enumerate(cold_specs, start=1):
        plans.append(
            ShadowPlan(
                f"cold_{i}",
                "cold_first",
                np_,
                pv,
                th,
                unload_before=(i % 3 == 0),
                request_prompt_decomposition=pv in {"short", "medium", "long"},
            )
        )
    # Warm short prompt (≥10) mix tails/durations
    for i, (np_, th) in enumerate(
        [
            (260, 5.0),
            (280, 5.0),
            (300, 5.0),
            (320, 10.0),
            (340, 10.0),
            (360, 10.0),
            (280, 20.0),
            (300, 20.0),
            (400, 5.0),
            (420, 5.0),
            (440, 10.0),
            (460, 20.0),
        ],
        start=1,
    ):
        plans.append(
            ShadowPlan(
                f"warm_short_{i}",
                "warm_repeat",
                np_,
                "short",
                th,
                request_prompt_decomposition=True,
            )
        )
    # Warm long prompt (≥10)
    for i, (np_, th) in enumerate(
        [
            (260, 5.0),
            (300, 5.0),
            (340, 5.0),
            (380, 10.0),
            (420, 10.0),
            (280, 10.0),
            (320, 20.0),
            (360, 20.0),
            (400, 20.0),
            (450, 5.0),
            (480, 10.0),
            (350, 5.0),
        ],
        start=1,
    ):
        plans.append(
            ShadowPlan(
                f"warm_long_{i}",
                "warm_repeat",
                np_,
                "long",
                th,
                request_prompt_decomposition=True,
            )
        )
    # Warm standard fill for eval/tail coverage
    for i, (np_, th) in enumerate(
        [
            (250, 5.0),
            (270, 5.0),
            (290, 5.0),
            (410, 5.0),
            (430, 5.0),
            (470, 5.0),
            (310, 10.0),
            (330, 10.0),
            (390, 10.0),
            (440, 10.0),
            (260, 20.0),
            (370, 20.0),
            (410, 20.0),
            (480, 20.0),
            (360, 5.0),
            (360, 10.0),
            (360, 20.0),
            (500, 5.0),
        ],
        start=1,
    ):
        plans.append(
            ShadowPlan(
                f"warm_std_{i}",
                "warm_repeat",
                np_,
                "standard",
                th,
                request_prompt_decomposition=False,
            )
        )
    # Warm eval-only (no tail accounting request) → V1 registry specialty (≥10)
    for i, np_ in enumerate(
        [260, 280, 300, 320, 340, 360, 380, 400, 420, 440, 360, 300],
        start=1,
    ):
        plans.append(
            ShadowPlan(
                f"warm_v1_{i}",
                "warm_repeat",
                np_,
                "standard",
                5.0,
                request_prompt_decomposition=False,
                request_tail_accounting=False,
            )
        )
    return plans


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gap-s", type=float, default=6.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    plans = build_plans()
    rng = random.Random(int(args.seed))
    order = list(range(len(plans)))
    rng.shuffle(order)
    plans = [plans[i] for i in order]
    if args.limit > 0:
        plans = plans[: int(args.limit)]

    OUT.mkdir(parents=True, exist_ok=True)
    progress = OUT / "v2_live_shadow_progress.jsonl"
    progress.write_text("", encoding="utf-8")
    print(f"[v2-live-shadow] n_plans={len(plans)}", flush=True)

    actions: list[dict[str, Any]] = []
    model_warm = False
    for i, plan in enumerate(plans, start=1):
        need_unload = plan.unload_before or plan.residency == "cold_first"
        prep = True if need_unload else (not model_warm)
        prompt = PROMPT_TEXT.get(plan.prompt_variant, PROMPT_TEXT["standard"])
        cell = ControlCell(
            cell_id=f"v2shadow_{plan.plan_id}",
            residency=plan.residency,
            num_predict=plan.num_predict,
            token_bucket="v2_live_shadow",
            prompt=prompt,
        )
        print(
            f"[v2-live-shadow] {i}/{len(plans)} {plan.plan_id} "
            f"np={plan.num_predict} tail={plan.tail_tau_s} prep={prep}",
            flush=True,
        )
        row = run_controlled_v2(
            cell,
            repeat_i=i,
            prep_residency=prep,
            tail_tau_s=float(plan.tail_tau_s),
        )
        model_warm = True
        infer = row.get("infer") or {}
        te = infer.get("eval_duration_s")
        tp = infer.get("prompt_eval_duration_s")
        e_net = row.get("E_net_raw_j")
        e_tail = row.get("E_tail_j")

        # Registry: expanded when cold/prompt-decomp/tail accounting
        est = estimate_action(
            t_eval_s=float(te) if te is not None else None,
            t_prompt_s=float(tp or 0.0),
            tail_horizon_s=float(plan.tail_tau_s),
            residency=plan.residency,
            unload_before=plan.unload_before,
            request_tail_accounting=plan.request_tail_accounting,
            request_prompt_decomposition=plan.request_prompt_decomposition,
            plant_config_id=PLANT_CONFIG_ID,
            measured_E_net_j=float(e_net) if e_net is not None else None,
            measured_E_tail_j=float(e_tail) if e_tail is not None else None,
        )

        cold = plan.residency == "cold_first" or plan.unload_before
        action = {
            "plan_id": plan.plan_id,
            "session_id": row.get("session_id"),
            "action_id": row.get("action_id"),
            "residency": plan.residency,
            "unload_before": plan.unload_before,
            "prompt_variant": plan.prompt_variant,
            "num_predict": plan.num_predict,
            "tail_tau_s": plan.tail_tau_s,
            "tail_horizon_s": plan.tail_tau_s,
            "cold": cold,
            "t_eval_s": te,
            "t_prompt_s": tp,
            "measured_E_net_j": e_net,
            "measured_E_tail_j": e_tail,
            "measured_energy": (
                float(e_net) + float(e_tail)
                if e_net is not None and e_tail is not None
                else None
            ),
            "registry_selected_predictor": est.get("registry_selected_predictor"),
            "selection_reason": est.get("selection_reason"),
            "v1_prediction": est.get("v1_prediction"),
            "v2_prediction": est.get("v2_prediction"),
            "registry_predicted_E_j": est.get("predicted_E_j"),
            "v1_residual": est.get("v1_residual"),
            "v2_residual": est.get("v2_residual"),
            "prediction_domain": est.get("prediction_domain"),
            "component_estimates": est.get("component_estimates"),
            "empirical_error_scale_j": est.get("empirical_error_scale_j"),
            "confidence": est.get("confidence"),
            "plant_fingerprint": {
                "plant_config_id": PLANT_CONFIG_ID,
                "residency": plan.residency,
                "gpu_temp_settle_c": (row.get("temps") or {}).get("gpu_temp_c_settle"),
                "gpu_temp_end_c": (row.get("temps") or {}).get("gpu_temp_c_end"),
                "eval_duration_s": te,
                "prompt_eval_duration_s": tp,
                "tail_tau_s": plan.tail_tau_s,
            },
        }
        action["strata"] = classify_strata(action)
        actions.append(action)
        with progress.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "at": _utc(),
                        "i": i,
                        "plan_id": plan.plan_id,
                        "selected": action["registry_selected_predictor"],
                        "v2_residual": action["v2_residual"],
                        "strata": action["strata"],
                    }
                )
                + "\n"
            )
        print(
            f"[v2-live-shadow] done sel={action['registry_selected_predictor']} "
            f"v2_resid={action['v2_residual']} strata={action['strata']}",
            flush=True,
        )
        time.sleep(max(0.0, float(args.gap_s)))

    # Stratum counts
    counts: dict[str, int] = {}
    for a in actions:
        for s in a.get("strata") or []:
            counts[s] = counts.get(s, 0) + 1

    report = {
        "ok": True,
        "at": _utc(),
        "status": "v2_live_shadow_evidence_ready",
        "n_actions": len(actions),
        "stratum_counts": counts,
        "predictor_v1_frozen": bool(PREDICTOR_V1_FROZEN),
        "actions": actions,
        "policy": policy_stamp(),
    }
    jpath = OUT / "v2_live_shadow_campaign_latest.json"
    mpath = OUT / "v2_live_shadow_campaign_latest.md"
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
    mpath.write_text(
        "\n".join(
            [
                "# V2 live-shadow campaign",
                "",
                f"- n_actions: `{len(actions)}`",
                f"- stratum_counts: `{counts}`",
                f"- status: `v2_live_shadow_evidence_ready`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "n_actions": len(actions),
                "stratum_counts": counts,
                "artifact": str(jpath).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
