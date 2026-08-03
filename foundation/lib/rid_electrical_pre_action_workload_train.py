#!/usr/bin/env python3
"""Workload-first training: fit g then h for Action Contract campaign.

Never trains E directly from prompt metadata as the primary path.
Never uses measured duration/tokens/done_reason as deployable features.
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from lib.rid_electrical_pre_action_action_contract import (
    CONTRACT_SCHEMA,
    demand_features_from_contract_and_snapshot,
    split_action_contract_rows,
)
from lib.rid_electrical_pre_action_baseline import paired_metrics
from lib.rid_electrical_pre_action_campaign_status import (
    ACTION_CONTRACT_CAMPAIGN_ID,
    assert_campaign_fittable,
)
from lib.rid_electrical_pre_action_oracle_audit import _ols_fit, _ols_predict
from lib.rid_electrical_pre_action_paths import EVIDENCE_PLANT, plant_dir
from lib.rid_electrical_pre_action_snapshot import (
    FORBIDDEN_FEATURE_KEYS,
    PROFILE_MEASURABLE,
    PROFILE_SHORT,
    PROFILE_UNKNOWN,
)

G_JSON = "pre_action_workload_demand_train_latest.json"
G_MD = "pre_action_workload_demand_train_latest.md"
H_JSON = "pre_action_energy_map_train_latest.json"
H_MD = "pre_action_energy_map_train_latest.md"
COMBINED_JSON = "pre_action_action_contract_train_latest.json"
COMBINED_MD = "pre_action_action_contract_train_latest.md"

FEATURE_ORDER = [
    "planned_eval_token_target",
    "reasoning_depth",
    "prompt_utf8_bytes",
    "prompt_word_count",
    "gpu_temp_start_c",
    "settled_idle_power_w",
    "trailing_throughput_tps",
    "throughput_history_count",
    "task_explanation",
    "task_summary",
    # task_enumeration implied by intercept (avoid perfect multicollinearity)
]


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _contract_of(row: Mapping[str, Any]) -> dict[str, Any]:
    snap = row.get("snapshot") if isinstance(row.get("snapshot"), Mapping) else {}
    c = row.get("action_contract") or snap.get("action_contract")
    if isinstance(c, Mapping):
        return dict(c)
    raise ValueError("missing_action_contract")


def _eligible_workload(row: Mapping[str, Any]) -> bool:
    lab = row.get("label") or {}
    try:
        toks = float(lab.get("actual_eval_tokens"))
        dur = float(lab.get("eval_duration_s"))
    except (TypeError, ValueError):
        return False
    return math.isfinite(toks) and math.isfinite(dur) and toks > 0 and dur > 0


def _eligible_energy(row: Mapping[str, Any], head: str) -> bool:
    if head == "gross":
        return bool(row.get("eligible_gross"))
    return bool(row.get("eligible_net"))


def _xy_demand(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[list[float]], list[float], list[float]]:
    xs: list[list[float]] = []
    y_tok: list[float] = []
    y_dur: list[float] = []
    for r in rows:
        if not _eligible_workload(r):
            continue
        contract = _contract_of(r)
        snap = r.get("snapshot") or {}
        feats = demand_features_from_contract_and_snapshot(contract, snap)
        for fk in FORBIDDEN_FEATURE_KEYS:
            if fk in feats:
                raise RuntimeError(f"leakage_in_g_features:{fk}")
        xs.append([float(feats.get(k, 0.0)) for k in FEATURE_ORDER])
        lab = r["label"]
        y_tok.append(float(lab["actual_eval_tokens"]))
        y_dur.append(float(lab["eval_duration_s"]))
    return xs, y_tok, y_dur


def _admission_workload(holdout: Mapping[str, Any], *, target: str) -> dict[str, Any]:
    rel = holdout.get("rel_mae")
    slope = holdout.get("calibration_slope")
    bor = holdout.get("bias_over_rmse")
    n = int(holdout.get("n") or 0)
    gates = {
        "n_holdout_ge_8": n >= 8,
        "rel_mae_le_0_25": rel is not None and float(rel) <= 0.25,
        "slope_in_0_7_1_3": slope is not None and 0.7 <= float(slope) <= 1.3,
        "bias_rmse_le_0_35": bor is not None and float(bor) <= 0.35,
    }
    return {
        "passed": all(gates.values()),
        "gates": gates,
        "target": target,
        "status": "admitted_candidate" if all(gates.values()) else "training_not_justified",
    }


def fit_workload_demand_g(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    splits = split_action_contract_rows(rows)
    train, select, holdout = splits["train"], splits["select"], splits["holdout"]
    xs_tr, yt_tr, yd_tr = _xy_demand(train)
    if len(yt_tr) < len(FEATURE_ORDER) + 2:
        return {
            "ok": True,
            "status": "training_not_justified",
            "reason": "insufficient_train_rows",
            "n_train": len(yt_tr),
            "deployable": False,
        }
    coefs_tok = _ols_fit(xs_tr, yt_tr)
    coefs_dur = _ols_fit(xs_tr, yd_tr)
    # Residual std on train for t90
    pred_dur_tr = [_ols_predict(coefs_dur, x) for x in xs_tr]
    resid = [float(a) - float(b) for a, b in zip(yd_tr, pred_dur_tr)]
    resid_std = statistics.pstdev(resid) if len(resid) > 1 else 0.0

    def _eval(xs, yt, yd):
        if not xs:
            return {
                "tokens": paired_metrics([], []),
                "duration": paired_metrics([], []),
            }
        pt = [_ols_predict(coefs_tok, x) for x in xs]
        pd = [_ols_predict(coefs_dur, x) for x in xs]
        return {
            "tokens": paired_metrics(yt, pt),
            "duration": paired_metrics(yd, pd),
        }

    xs_se, yt_se, yd_se = _xy_demand(select)
    xs_ho, yt_ho, yd_ho = _xy_demand(holdout)
    metrics = {
        "train": _eval(xs_tr, yt_tr, yd_tr),
        "select": _eval(xs_se, yt_se, yd_se),
        "holdout": _eval(xs_ho, yt_ho, yd_ho),
    }
    adm_tok = _admission_workload(metrics["holdout"]["tokens"], target="tokens")
    adm_dur = _admission_workload(metrics["holdout"]["duration"], target="duration")
    admitted = bool(adm_tok["passed"] and adm_dur["passed"])
    model = {
        "schema_version": CONTRACT_SCHEMA,
        "stage": "workload_demand_g",
        "feature_order": list(FEATURE_ORDER),
        "coefs_tokens": coefs_tok,
        "coefs_duration": coefs_dur,
        "duration_resid_std": resid_std,
        "memory_demand_proxy_default": None,
        "memory_note": "No stable per-action memory demand metric in plant corpus yet.",
        "deployable": False,
        "admitted": admitted,
    }
    status = "admitted_candidate" if admitted else "training_not_justified"
    return {
        "ok": True,
        "at": _utc(),
        "status": status,
        "deployable": False,
        "model": model,
        "admission_tokens": adm_tok,
        "admission_duration": adm_dur,
        "metrics": metrics,
        "n_train": len(yt_tr),
        "n_select": len(yt_se),
        "n_holdout": len(yt_ho),
        "authority": {
            "learning_admission_withheld": True,
            "auto_admit": False,
            "auto_refit": False,
        },
    }


def fit_energy_map_h(
    rows: Sequence[Mapping[str, Any]],
    demand_model: Mapping[str, Any],
    *,
    head: str = "gross",
) -> dict[str, Any]:
    """Fit h: E ~ predicted t_eval from g (+ intercept). Uses g predictions, not measured t."""
    from lib.rid_electrical_pre_action_action_contract import predict_workload_demand

    splits = split_action_contract_rows(rows)
    train = [r for r in splits["train"] if _eligible_energy(r, head)]
    holdout = [r for r in splits["holdout"] if _eligible_energy(r, head)]
    select = [r for r in splits["select"] if _eligible_energy(r, head)]

    def pack(rs: Sequence[Mapping[str, Any]]):
        ts: list[float] = []
        ys: list[float] = []
        for r in rs:
            contract = _contract_of(r)
            snap = r.get("snapshot") or {}
            profile = str(snap.get("planned_response_profile") or "")
            if head == "net" and profile in {PROFILE_SHORT, PROFILE_UNKNOWN}:
                continue
            demand = predict_workload_demand(contract, snap, model=demand_model)
            t_hat = demand.get("t_eval_hat_s")
            lab = r.get("label") or {}
            ykey = "E_generate_j" if head == "gross" else "E_net_raw_j"
            try:
                y = float(lab.get(ykey))
                t = float(t_hat)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(y) or not math.isfinite(t):
                continue
            ts.append(t)
            ys.append(y)
        return ts, ys

    t_tr, y_tr = pack(train)
    if len(y_tr) < 6:
        return {
            "ok": True,
            "head": head,
            "status": "training_not_justified",
            "reason": "insufficient_train_rows",
            "n_train": len(y_tr),
            "deployable": False,
        }
    coefs = _ols_fit([[t] for t in t_tr], y_tr)
    alpha, beta = float(coefs[0]), float(coefs[1])
    pred_tr = [alpha + beta * t for t in t_tr]
    resid = [y - p for y, p in zip(y_tr, pred_tr)]
    resid_std = statistics.pstdev(resid) if len(resid) > 1 else 0.0

    def metrics_for(rs):
        t, y = pack(rs)
        if not y:
            return paired_metrics([], [])
        pred = [alpha + beta * tt for tt in t]
        return paired_metrics(y, pred)

    hold_m = metrics_for(holdout)
    sel_m = metrics_for(select)
    tr_m = metrics_for(train)
    rel = hold_m.get("rel_mae")
    slope = hold_m.get("calibration_slope")
    bor = hold_m.get("bias_over_rmse")
    n = int(hold_m.get("n") or 0)
    gates = {
        "n_holdout_ge_8": n >= 8,
        "rel_mae_le_0_20": rel is not None and float(rel) <= 0.20,
        "slope_in_0_8_1_2": slope is not None and 0.8 <= float(slope) <= 1.2,
        "bias_rmse_le_0_30": bor is not None and float(bor) <= 0.30,
    }
    passed = all(gates.values())
    model = {
        "schema_version": CONTRACT_SCHEMA,
        "stage": "energy_h",
        "head": head,
        "alpha": alpha,
        "beta": beta,
        "energy_resid_std": resid_std,
        "deployable": False,
        "admitted": passed,
        "note": "Primary path is h(t_hat from g); not E~prompt metadata.",
    }
    return {
        "ok": True,
        "at": _utc(),
        "head": head,
        "status": "admitted_candidate" if passed else "training_not_justified",
        "deployable": False,
        "model": model,
        "admission": {"passed": passed, "gates": gates},
        "metrics": {"train": tr_m, "select": sel_m, "holdout": hold_m},
        "n_train": len(y_tr),
        "n_select": int(sel_m.get("n") or 0),
        "n_holdout": n,
    }


def run_action_contract_train(
    *,
    campaign_id: str = ACTION_CONTRACT_CAMPAIGN_ID,
) -> dict[str, Any]:
    assert_campaign_fittable(campaign_id)
    root = plant_dir(campaign_id)
    freeze_path = root / "pre_action_corpus_freeze_latest.json"
    if not freeze_path.exists():
        raise FileNotFoundError(f"missing_freeze:{freeze_path}")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    rows = list(freeze.get("rows") or [])
    # Hard refuse dual/V1 merge
    for r in rows:
        cid = str(r.get("campaign_id") or (r.get("snapshot") or {}).get("campaign_id") or "")
        if cid and cid != campaign_id:
            raise RuntimeError(f"foreign_campaign_row_refused:{cid}")

    g_result = fit_workload_demand_g(rows)
    (root / G_JSON).write_text(json.dumps(g_result, indent=2), encoding="utf-8")
    (root / G_MD).write_text(_g_md(g_result), encoding="utf-8")

    h_gross = None
    h_net = None
    if g_result.get("status") == "admitted_candidate" or g_result.get("model"):
        # Fit h even when g is not fully admitted, using best available g model,
        # but mark overall accordingly. Prefer admitted; else still attempt map.
        demand_model = g_result.get("model") or {}
        if demand_model.get("coefs_tokens"):
            h_gross = fit_energy_map_h(rows, demand_model, head="gross")
            h_net = fit_energy_map_h(rows, demand_model, head="net")
            (root / H_JSON).write_text(
                json.dumps({"gross": h_gross, "net": h_net}, indent=2),
                encoding="utf-8",
            )
            (root / H_MD).write_text(_h_md(h_gross, h_net), encoding="utf-8")

    any_candidate = bool(
        (g_result.get("status") == "admitted_candidate")
        and h_gross
        and h_gross.get("status") == "admitted_candidate"
    )
    overall = {
        "ok": True,
        "at": _utc(),
        "campaign_id": campaign_id,
        "evidence_source": EVIDENCE_PLANT,
        "deployable": False,
        "status": (
            "admitted_candidate"
            if any_candidate
            else "training_not_justified"
        ),
        "workload_g": {
            "status": g_result.get("status"),
            "artifact": str(root / G_JSON).replace("\\", "/"),
        },
        "energy_h_gross": {
            "status": (h_gross or {}).get("status"),
            "artifact": str(root / H_JSON).replace("\\", "/") if h_gross else None,
        },
        "energy_h_net": {"status": (h_net or {}).get("status")},
        "shadow_authorized": False,
        "candidate_for_separate_review": any_candidate,
        "authority": {
            "learning_admission_withheld": True,
            "auto_admit": False,
            "auto_refit": False,
            "master_routing_authorized": False,
            "gates_action": False,
        },
        "models": {
            "demand_g": g_result.get("model"),
            "energy_h_gross": (h_gross or {}).get("model"),
            "energy_h_net": (h_net or {}).get("model"),
        },
    }
    (root / COMBINED_JSON).write_text(json.dumps(overall, indent=2), encoding="utf-8")
    (root / COMBINED_MD).write_text(_combined_md(overall), encoding="utf-8")
    overall["artifact"] = str(root / COMBINED_JSON).replace("\\", "/")
    return overall


def _g_md(g: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Workload demand train (g)",
            "",
            f"- status: **{g.get('status')}**",
            f"- deployable: false",
            f"- n_train/select/holdout: {g.get('n_train')}/{g.get('n_select')}/{g.get('n_holdout')}",
            f"- tokens admission: `{g.get('admission_tokens')}`",
            f"- duration admission: `{g.get('admission_duration')}`",
            "",
        ]
    )


def _h_md(gross: Mapping[str, Any] | None, net: Mapping[str, Any] | None) -> str:
    lines = ["# Energy map train (h)", "", f"- deployable: false", ""]
    for name, h in (("gross", gross), ("net", net)):
        if not h:
            continue
        lines.append(f"## {name}")
        lines.append(f"- status: **{h.get('status')}**")
        lines.append(f"- admission: `{h.get('admission')}`")
        lines.append(f"- holdout: `{((h.get('metrics') or {}).get('holdout'))}`")
        lines.append("")
    return "\n".join(lines)


def _combined_md(overall: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Action Contract train (g then h)",
            "",
            f"- status: **{overall.get('status')}**",
            f"- candidate_for_separate_review: `{overall.get('candidate_for_separate_review')}`",
            f"- workload_g: `{overall.get('workload_g')}`",
            f"- energy_h_gross: `{overall.get('energy_h_gross')}`",
            f"- energy_h_net: `{overall.get('energy_h_net')}`",
            "",
            "Authority remains closed. Per-stage training_not_justified is a valid outcome.",
            "",
        ]
    )
