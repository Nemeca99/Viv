#!/usr/bin/env python3
"""Action Contract V1 — pre-execution work order between meaning and plant cost.

RID = physical stability control framework.
Action Contract = what Viv proposes to do (measurable planned work).
Demand model g = computation required.
Energy model h = physical cost of that computation.
PRT = grade prediction vs actual.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from lib.rid_electrical_pre_action_campaign_status import (
    ACTION_CONTRACT_CAMPAIGN_ID,
    DUAL_CAMPAIGN_ID,
)
from lib.rid_electrical_pre_action_paths import (
    EVIDENCE_PLANT,
    LEDGER_CAMPAIGN,
    plant_dir,
)
from lib.rid_electrical_pre_action_snapshot import (
    AUTHORITY_FALSE,
    FORBIDDEN_FEATURE_KEYS,
    PROFILE_MEASURABLE,
    PROFILE_SHORT,
    PROFILE_UNKNOWN,
)

CONTRACT_SCHEMA = "ActionContractV1"
CONTRACT_LOCK_NAME = "PRE_ACTION_ACTION_CONTRACT_V1.json"
CONTRACT_LOCK_PATH = LEDGER_CAMPAIGN / CONTRACT_LOCK_NAME

# Oracle-separable bands from dual freeze (actual token/duration clusters).
TOKEN_BANDS: dict[str, dict[str, Any]] = {
    "brief": {
        "planned_eval_token_band": "brief",
        "planned_eval_token_target": 40,
        "planned_eval_token_lo": 30,
        "planned_eval_token_hi": 50,
        "num_predict": 64,
        "expected_duration_lo_s": 0.25,
        "expected_duration_hi_s": 0.55,
        "reasoning_depth": "shallow",
        "plan_uncertainty": "medium",
        "default_profile": PROFILE_SHORT,
    },
    "standard": {
        "planned_eval_token_band": "standard",
        "planned_eval_token_target": 180,
        "planned_eval_token_lo": 140,
        "planned_eval_token_hi": 230,
        "num_predict": 256,
        "expected_duration_lo_s": 1.4,
        "expected_duration_hi_s": 2.4,
        "reasoning_depth": "medium",
        "plan_uncertainty": "medium",
        "default_profile": PROFILE_MEASURABLE,
    },
    "extended": {
        "planned_eval_token_band": "extended",
        "planned_eval_token_target": 280,
        "planned_eval_token_lo": 220,
        "planned_eval_token_hi": 340,
        "num_predict": 360,
        "expected_duration_lo_s": 2.2,
        "expected_duration_hi_s": 3.8,
        "reasoning_depth": "deep",
        "plan_uncertainty": "medium",
        "default_profile": PROFILE_MEASURABLE,
    },
}

TASK_TYPES: dict[str, dict[str, Any]] = {
    "explanation": {
        "task_type": "explanation",
        "planned_response_class": "explanation",
        "required_capability": "language_synthesis",
        "prompt_by_band": {
            "brief": (
                "In 2 short sentences, explain settle vs generate energy for a local GPU agent."
            ),
            "standard": (
                "Explain local GPU energy accounting for an autonomous agent. "
                "Write 8-12 sentences covering settle idle, generate window, gross vs net, "
                "SNR, and why duration drives joules. Do not stop early; fill the answer."
            ),
            "extended": (
                "Write a detailed explanation (16-24 sentences) of plant energy accounting: "
                "settle, prompt-eval, generate integration, net vs gross, Action Contract "
                "workload demand, duration→energy mapping, early-stop vs num_predict ceiling, "
                "and PRT grading. Expand each point; do not stop early."
            ),
        },
    },
    "summary": {
        "task_type": "summary",
        "planned_response_class": "summary",
        "required_capability": "language_synthesis",
        "prompt_by_band": {
            "brief": (
                "In one sentence, summarize why Action Contracts state planned tokens before run."
            ),
            "standard": (
                "Summarize in 8-12 sentences why pre-action energy models need an Action Contract "
                "that states planned tokens and duration before execution, and how that differs "
                "from fitting energy on prompt metadata alone. Keep writing until complete."
            ),
            "extended": (
                "Produce a long summary (16-24 sentences) of the Action Contract clutch: "
                "oracle ceiling findings, workload demand g, energy map h, ranges not points, "
                "RID as stability control (not physics law claim), and PRT. Expand thoroughly."
            ),
        },
    },
    "enumeration": {
        "task_type": "enumeration",
        "planned_response_class": "enumeration",
        "required_capability": "language_synthesis",
        "prompt_by_band": {
            "brief": (
                "List exactly 3 layers: Action Contract, demand g, energy h — one short phrase each."
            ),
            "standard": (
                "Enumerate 10 numbered items (one sentence each) covering: RID stability, "
                "Action Contract fields, token bands, demand model g, duration ranges, "
                "energy model h, plant idle state, early-stop, PRT, and authority closed. "
                "Use full sentences; do not stop before item 10."
            ),
            "extended": (
                "Enumerate 18 numbered items with 1-2 sentences each about Action Contract "
                "workload-first energy: task types, bands, num_predict ceilings, g targets, "
                "h mapping, gross/net, SNR, integration, shadow, admission gates, and "
                "control-framework language for RID. Complete all 18 items."
            ),
        },
    },
}

REQUIRED_CAPABILITIES = frozenset({"language_synthesis"})
EXECUTION_LANES = frozenset({"GPU"})
STOPPING_CONDITIONS = frozenset({"answer_complete", "token_ceiling"})
REASONING_DEPTHS = frozenset({"shallow", "medium", "deep"})
PLAN_UNCERTAINTIES = frozenset({"low", "medium", "high"})

CONTRACT_HASH_FIELDS = (
    "schema_version",
    "task_type",
    "planned_response_class",
    "required_capability",
    "execution_lane",
    "reasoning_depth",
    "planned_eval_token_band",
    "planned_eval_token_target",
    "planned_eval_token_lo",
    "planned_eval_token_hi",
    "num_predict",
    "expected_tool_calls",
    "stopping_condition",
    "expected_duration_lo_s",
    "expected_duration_hi_s",
    "plan_uncertainty",
    "campaign_id",
    "action_id",
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def compute_action_contract_hash(contract: Mapping[str, Any]) -> str:
    payload = {k: contract.get(k) for k in CONTRACT_HASH_FIELDS}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def verify_action_contract_integrity(
    contract: Mapping[str, Any],
) -> tuple[bool, str]:
    expected = str(contract.get("contract_hash") or "")
    if not expected:
        return False, "missing_contract_hash"
    got = compute_action_contract_hash(contract)
    if got != expected:
        return False, "contract_hash_mismatch"
    return True, "ok"


def build_action_contract(
    *,
    task_type: str,
    token_band: str,
    action_id: str,
    campaign_id: str = ACTION_CONTRACT_CAMPAIGN_ID,
    stopping_condition: str = "answer_complete",
    expected_tool_calls: int = 0,
    at: str | None = None,
) -> dict[str, Any]:
    if task_type not in TASK_TYPES:
        raise ValueError(f"unknown_task_type:{task_type}")
    if token_band not in TOKEN_BANDS:
        raise ValueError(f"unknown_token_band:{token_band}")
    if stopping_condition not in STOPPING_CONDITIONS:
        raise ValueError(f"unknown_stopping_condition:{stopping_condition}")
    task = TASK_TYPES[task_type]
    band = TOKEN_BANDS[token_band]
    prompt = str((task.get("prompt_by_band") or {}).get(token_band) or "")
    if not prompt:
        raise ValueError(f"missing_prompt:{task_type}:{token_band}")
    contract: dict[str, Any] = {
        "schema_version": CONTRACT_SCHEMA,
        "at": at or _utc(),
        "campaign_id": campaign_id,
        "action_id": action_id,
        "task_type": task["task_type"],
        "planned_response_class": task["planned_response_class"],
        "required_capability": task["required_capability"],
        "execution_lane": "GPU",
        "reasoning_depth": band["reasoning_depth"],
        "planned_eval_token_band": band["planned_eval_token_band"],
        "planned_eval_token_target": int(band["planned_eval_token_target"]),
        "planned_eval_token_lo": int(band["planned_eval_token_lo"]),
        "planned_eval_token_hi": int(band["planned_eval_token_hi"]),
        "num_predict": int(band["num_predict"]),
        "expected_tool_calls": int(expected_tool_calls),
        "stopping_condition": stopping_condition,
        "expected_duration_lo_s": float(band["expected_duration_lo_s"]),
        "expected_duration_hi_s": float(band["expected_duration_hi_s"]),
        "plan_uncertainty": band["plan_uncertainty"],
        "prompt": prompt,
        "planned_response_profile": band["default_profile"],
        "immutable_pre_action": True,
        **AUTHORITY_FALSE,
    }
    contract["contract_hash"] = compute_action_contract_hash(contract)
    return contract


def write_action_contract_lock(
    *,
    oracle_verdict: str = "duration_demand_bottleneck",
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Design lock: sizes from oracle-separable bands/classes; never merge dual/V1."""
    path = out_path or CONTRACT_LOCK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ok": True,
        "at": _utc(),
        "schema_version": CONTRACT_SCHEMA,
        "lock_name": CONTRACT_LOCK_NAME,
        "campaign_id": ACTION_CONTRACT_CAMPAIGN_ID,
        "predecessor_campaign_id": DUAL_CAMPAIGN_ID,
        "oracle_gate_verdict": oracle_verdict,
        "never_merge_dual_or_v1_rows": True,
        "training_order": ["workload_demand_g", "duration_to_energy_h"],
        "role_split": {
            "RID": "physical_stability_control_framework",
            "ActionContract": "proposed_measurable_work",
            "demand_model_g": "computation_required",
            "energy_model_h": "physical_cost_of_computation",
            "PRT": "grade_prediction_vs_actual",
        },
        "task_types": sorted(TASK_TYPES.keys()),
        "token_bands": {
            k: {
                "planned_eval_token_target": v["planned_eval_token_target"],
                "planned_eval_token_lo": v["planned_eval_token_lo"],
                "planned_eval_token_hi": v["planned_eval_token_hi"],
                "num_predict": v["num_predict"],
                "expected_duration_lo_s": v["expected_duration_lo_s"],
                "expected_duration_hi_s": v["expected_duration_hi_s"],
            }
            for k, v in TOKEN_BANDS.items()
        },
        "grid": {
            "axes": ["task_type", "token_band"],
            "n_cells": len(TASK_TYPES) * len(TOKEN_BANDS),
            "n_groups_primary": 8,
            "n_actions_primary": 8 * len(TASK_TYPES) * len(TOKEN_BANDS),
            "canary_groups": [1, 2],
            "note": "Not a blind repeat of the dual 15-cell num_predict×prompt matrix.",
        },
        "forbidden_as_features": sorted(
            k
            for k in (
                "eval_duration_s",
                "actual_eval_tokens",
                "prompt_eval_duration_s",
                "done_reason",
            )
            if k in FORBIDDEN_FEATURE_KEYS
        ),
        "net_null_profiles": [PROFILE_SHORT, PROFILE_UNKNOWN],
        "authority": {
            "operational_authority": False,
            "learning_admission_withheld": True,
            "auto_admit": False,
            "auto_refit": False,
            "master_routing_authorized": False,
            "gates_action": False,
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # Also place a copy under the campaign plant dir.
    plant = plant_dir(ACTION_CONTRACT_CAMPAIGN_ID)
    plant.mkdir(parents=True, exist_ok=True)
    (plant / CONTRACT_LOCK_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    payload["artifact"] = str(path).replace("\\", "/")
    payload["plant_artifact"] = str(plant / CONTRACT_LOCK_NAME).replace("\\", "/")
    return payload


def action_contract_cell_id(task_type: str, token_band: str) -> str:
    return f"{task_type}__{token_band}"


def action_contract_collection_plan(
    *,
    n_groups: int = 8,
    campaign_id: str = ACTION_CONTRACT_CAMPAIGN_ID,
) -> list[dict[str, Any]]:
    """Canary-first grid: task_type × token_band (9 cells × groups)."""
    base: list[dict[str, Any]] = []
    for task_type in TASK_TYPES:
        for band_name, band in TOKEN_BANDS.items():
            cell = action_contract_cell_id(task_type, band_name)
            contract = build_action_contract(
                task_type=task_type,
                token_band=band_name,
                action_id="plan_template",
                campaign_id=campaign_id,
            )
            # Recompute hash after action_id is set per plan row.
            base.append(
                {
                    "task_type": task_type,
                    "token_band": band_name,
                    "cell_id": cell,
                    "num_predict": int(band["num_predict"]),
                    "prompt_variant": f"{task_type}_{band_name}",
                    "prompt": contract["prompt"],
                    "planned_response_profile": band["default_profile"],
                    "block_kind": "primary",
                }
            )
    plans: list[dict[str, Any]] = []
    for g in range(1, n_groups + 1):
        rotated = base[g - 1 :] + base[: g - 1]
        for order_i, cell in enumerate(rotated):
            action_id = f"ac_g{g}_{cell['cell_id']}_o{order_i}"
            contract = build_action_contract(
                task_type=cell["task_type"],
                token_band=cell["token_band"],
                action_id=action_id,
                campaign_id=campaign_id,
            )
            plans.append(
                {
                    **cell,
                    "collection_group": g,
                    "order_in_group": order_i,
                    "action_id": action_id,
                    "campaign_id": campaign_id,
                    "action_contract": contract,
                    "prompt": contract["prompt"],
                }
            )
    return plans


def action_contract_plans_for_groups(groups: Sequence[int]) -> list[dict[str, Any]]:
    gset = {int(g) for g in groups}
    return [p for p in action_contract_collection_plan() if int(p["collection_group"]) in gset]


# Split: groups 1-4 train, 5-6 select, 7-8 holdout
AC_TRAIN = frozenset({1, 2, 3, 4})
AC_SELECT = frozenset({5, 6})
AC_HOLDOUT = frozenset({7, 8})


def action_contract_split_bucket(row: Mapping[str, Any]) -> str | None:
    try:
        g = int(
            (row.get("snapshot") or {}).get("collection_group")
            or row.get("collection_group")
            or 0
        )
    except (TypeError, ValueError):
        return None
    if g in AC_TRAIN:
        return "train"
    if g in AC_SELECT:
        return "select"
    if g in AC_HOLDOUT:
        return "holdout"
    return None


def split_action_contract_rows(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {"train": [], "select": [], "holdout": []}
    for r in rows:
        b = action_contract_split_bucket(r)
        if b:
            out[b].append(dict(r))
    return out


def profile_from_action_contract(contract: Mapping[str, Any]) -> str:
    band = str(contract.get("planned_eval_token_band") or "")
    if band == "brief":
        return PROFILE_SHORT
    if band in TOKEN_BANDS:
        return PROFILE_MEASURABLE
    return PROFILE_UNKNOWN


def demand_features_from_contract_and_snapshot(
    contract: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> dict[str, float]:
    """Pre-action features for g — never measured duration/tokens."""
    depth = {"shallow": 0.0, "medium": 1.0, "deep": 2.0}
    unc = {"low": 0.0, "medium": 1.0, "high": 2.0}
    task_oh = {t: 0.0 for t in TASK_TYPES}
    tt = str(contract.get("task_type") or "")
    if tt in task_oh:
        task_oh[tt] = 1.0
    feats = {
        "num_predict": float(contract.get("num_predict") or snapshot.get("num_predict") or 0),
        "planned_eval_token_target": float(contract.get("planned_eval_token_target") or 0),
        "planned_eval_token_lo": float(contract.get("planned_eval_token_lo") or 0),
        "planned_eval_token_hi": float(contract.get("planned_eval_token_hi") or 0),
        "reasoning_depth": depth.get(str(contract.get("reasoning_depth")), 1.0),
        "plan_uncertainty": unc.get(str(contract.get("plan_uncertainty")), 1.0),
        "expected_tool_calls": float(contract.get("expected_tool_calls") or 0),
        "prompt_utf8_bytes": float(snapshot.get("prompt_utf8_bytes") or 0),
        "prompt_word_count": float(snapshot.get("prompt_word_count") or 0),
        "gpu_temp_start_c": float(snapshot.get("gpu_temp_start_c") or 0),
        "settled_idle_power_w": float(snapshot.get("settled_idle_power_w") or 0),
        "trailing_throughput_tps": float(snapshot.get("trailing_throughput_tps") or 0),
        "throughput_history_count": float(snapshot.get("throughput_history_count") or 0),
        **{f"task_{k}": v for k, v in task_oh.items()},
    }
    for fk in FORBIDDEN_FEATURE_KEYS:
        if fk in feats:
            raise ValueError(f"forbidden_feature_in_demand:{fk}")
    return feats


def predict_workload_demand(
    contract: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    model: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Stage g: predict tokens / t_eval ranges / memory proxy from contract."""
    ok, reason = verify_action_contract_integrity(contract)
    out: dict[str, Any] = {
        "stage": "workload_demand_g",
        "deployable": False,
        "contract_ok": ok,
        "contract_reason": reason,
        "predicted_tokens": None,
        "t_eval_hat_s": None,
        "t50_s": None,
        "t90_s": None,
        "memory_demand_proxy": None,
        "source": "unfitted_contract_prior",
        **AUTHORITY_FALSE,
    }
    if not ok:
        return out
    feats = demand_features_from_contract_and_snapshot(contract, snapshot)
    profile = str(
        snapshot.get("planned_response_profile")
        or profile_from_action_contract(contract)
    )
    if model and model.get("coefs_tokens") and model.get("feature_order"):
        order = list(model["feature_order"])
        x = [float(feats.get(k, 0.0)) for k in order]
        tok = float(model["coefs_tokens"][0]) + sum(
            float(c) * float(v) for c, v in zip(model["coefs_tokens"][1:], x)
        )
        t_hat = float(model["coefs_duration"][0]) + sum(
            float(c) * float(v) for c, v in zip(model["coefs_duration"][1:], x)
        )
        resid_t = float(model.get("duration_resid_std") or 0.0)
        out.update(
            {
                "predicted_tokens": max(1.0, tok),
                "t_eval_hat_s": max(0.05, t_hat),
                "t50_s": max(0.05, t_hat),
                "t90_s": max(0.05, t_hat + 1.28155 * resid_t),
                "memory_demand_proxy": model.get("memory_demand_proxy_default"),
                "source": "fitted_g",
                "features_used": order,
            }
        )
    else:
        # Honest prior from contract bands until g is fitted.
        t_lo = float(contract["expected_duration_lo_s"])
        t_hi = float(contract["expected_duration_hi_s"])
        t_mid = 0.5 * (t_lo + t_hi)
        out.update(
            {
                "predicted_tokens": float(contract["planned_eval_token_target"]),
                "t_eval_hat_s": t_mid,
                "t50_s": t_mid,
                "t90_s": t_hi,
                "memory_demand_proxy": None,
                "source": "contract_prior",
            }
        )
    if profile in {PROFILE_SHORT, PROFILE_UNKNOWN}:
        # Net path remains null downstream; workload priors still emitted for gross.
        out["net_suppressed"] = True
    return out


def predict_energy_from_demand(
    demand: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    model: Mapping[str, Any] | None = None,
    head: str = "gross",
) -> dict[str, Any]:
    """Stage h: map duration demand (+ plant state) → energy ranges."""
    profile = str(snapshot.get("planned_response_profile") or PROFILE_UNKNOWN)
    out: dict[str, Any] = {
        "stage": "energy_h",
        "head": head,
        "deployable": False,
        "E50_j": None,
        "E90_j": None,
        "predicted_E_j": None,
        "source": "unfitted",
        **AUTHORITY_FALSE,
    }
    if head == "net" and profile in {PROFILE_SHORT, PROFILE_UNKNOWN}:
        out["source"] = "net_null_profile"
        return out
    t50 = demand.get("t50_s")
    t90 = demand.get("t90_s")
    if t50 is None:
        return out
    idle = float(snapshot.get("settled_idle_power_w") or 0.0)
    if model and model.get("alpha") is not None and model.get("beta") is not None:
        alpha = float(model["alpha"])
        beta = float(model["beta"])
        resid = float(model.get("energy_resid_std") or 0.0)
        e50 = alpha + beta * float(t50)
        e90 = alpha + beta * float(t90 if t90 is not None else t50) + 1.28155 * resid
        out.update(
            {
                "E50_j": e50,
                "E90_j": e90,
                "predicted_E_j": e50,
                "source": "fitted_h",
                "alpha": alpha,
                "beta": beta,
                "plant_idle_w": idle,
            }
        )
    else:
        # Plant-validated linear prior: ~gross power scale until h fitted.
        # Uses idle as soft plant state context only (not post-action energy).
        beta_prior = 120.0 + 0.4 * idle
        alpha_prior = 5.0
        e50 = alpha_prior + beta_prior * float(t50)
        e90 = alpha_prior + beta_prior * float(t90 if t90 is not None else t50)
        out.update(
            {
                "E50_j": e50,
                "E90_j": e90,
                "predicted_E_j": e50,
                "source": "plant_prior_h",
                "alpha": alpha_prior,
                "beta": beta_prior,
            }
        )
    return out


def predict_action_contract_energy(
    contract: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    demand_model: Mapping[str, Any] | None = None,
    energy_model_gross: Mapping[str, Any] | None = None,
    energy_model_net: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Workload-first API: contract → g → h ranges. Never consumes measured outcomes."""
    demand = predict_workload_demand(contract, snapshot, model=demand_model)
    gross = predict_energy_from_demand(
        demand, snapshot, model=energy_model_gross, head="gross"
    )
    net = predict_energy_from_demand(
        demand, snapshot, model=energy_model_net, head="net"
    )
    return {
        "ok": bool(demand.get("contract_ok")),
        "schema_version": CONTRACT_SCHEMA,
        "deployable": False,
        "action_contract_hash": contract.get("contract_hash"),
        "demand": demand,
        "gross": gross,
        "net": net,
        "operator_phrasing": _operator_phrasing(gross),
        **AUTHORITY_FALSE,
    }


def _operator_phrasing(gross: Mapping[str, Any]) -> str | None:
    e50 = gross.get("E50_j")
    e90 = gross.get("E90_j")
    if e50 is None or e90 is None:
        return None
    return (
        f"This action will probably cost {e50:.0f} J, "
        f"with a conservative upper estimate of {e90:.0f} J."
    )


def assert_no_leakage_in_predict_inputs(
    contract: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> None:
    for blob in (contract, snapshot):
        for fk in FORBIDDEN_FEATURE_KEYS:
            if fk in blob and blob.get(fk) is not None:
                # Snapshot must not carry post-action fields into predict path.
                if fk in {
                    "eval_duration_s",
                    "actual_eval_tokens",
                    "prompt_eval_duration_s",
                    "done_reason",
                    "E_generate_j",
                    "E_net_raw_j",
                }:
                    raise ValueError(f"leakage:{fk}")
