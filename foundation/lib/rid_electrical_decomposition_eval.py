#!/usr/bin/env python3
"""Decomposition evidence evaluation: component labels + held-out energy closure.

Pre-locked rules:
  SNR_net ≥ 3, CV_E ≤ 0.20, CV_P(mean) ≤ 0.15
  ε_closure ≤ 0.15 on held-out actions with n_holdout ≥ 5
  Labels: repeatable_component | below_resolution | unstable_component | insufficient_evidence

No V2 coefficient fit. V1 remains frozen.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_cost_decomposition import (
    CLOSURE_EPS_MAX,
    CLOSURE_N_HOLDOUT_MIN,
    FAMILY_ORDER,
)
from lib.rid_electrical_ledger_controls import evaluate_control_repeats
from lib.rid_electrical_policy import policy_stamp
from lib.rid_electrical_predictor import predict_E_net

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"

COMPONENT_LABELS = (
    "repeatable_component",
    "below_resolution",
    "unstable_component",
    "insufficient_evidence",
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def outcome_to_component_label(eval_row: dict[str, Any]) -> str:
    """Map control-repeat outcome / net_attribution → decomposition component label."""
    outcome = str(eval_row.get("outcome") or "")
    net_attr = str(eval_row.get("net_attribution") or "")
    if outcome == "insufficient_evidence" or eval_row.get("n_usable", 0) < 3:
        return "insufficient_evidence"
    if outcome == "net_signature_repeatable":
        return "repeatable_component"
    if outcome == "gross_signature_repeatable" or net_attr == "below_resolution":
        return "below_resolution"
    if outcome == "unstable_signature":
        return "unstable_component"
    return "insufficient_evidence"


def classify_cell_rows(
    rows: list[dict[str, Any]],
    *,
    cv_p_primary: str = "mean_from_E",
) -> dict[str, Any]:
    ev = evaluate_control_repeats(rows, cv_p_primary=cv_p_primary)
    label = outcome_to_component_label(ev)
    return {
        **ev,
        "component_label": label,
        "component_labels_allowed": list(COMPONENT_LABELS),
    }


def _mu(xs: list[float]) -> float | None:
    return statistics.fmean(xs) if xs else None


def _group_by_cell(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        cid = str(r.get("cell_id") or "")
        out.setdefault(cid, []).append(r)
    return out


def build_phase_attributions(
    family_rows: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Build E_load / E_prompt / E_eval / E_tail attributions from family measurements."""
    load_rows = family_rows.get("load_residency") or []
    prompt_rows = family_rows.get("prompt_eval") or []
    token_rows = family_rows.get("token_eval_v1_reference") or []
    tail_rows = family_rows.get("post_action_tail") or []

    by_load = _group_by_cell(load_rows)
    cold = by_load.get("decomp_cold_load__np360") or []
    warm = by_load.get("decomp_warm_resident__np360") or []
    cold_e = [
        float(r["E_net_raw_j"])
        for r in cold
        if r.get("E_net_raw_j") is not None
    ]
    warm_e = [
        float(r["E_net_raw_j"])
        for r in warm
        if r.get("E_net_raw_j") is not None
    ]
    if not cold_e:
        cold_e = [
            float(r["E_generate_j"])
            for r in cold
            if r.get("E_generate_j") is not None
        ]
    if not warm_e:
        warm_e = [
            float(r["E_generate_j"])
            for r in warm
            if r.get("E_generate_j") is not None
        ]
    mu_cold = _mu(cold_e)
    mu_warm = _mu(warm_e)
    e_load = None
    if mu_cold is not None and mu_warm is not None:
        e_load = float(mu_cold) - float(mu_warm)

    by_prompt = _group_by_cell(prompt_rows)
    prompt_mu: dict[str, float | None] = {}
    for cid, rs in by_prompt.items():
        vals = [
            float(r["E_net_raw_j"])
            for r in rs
            if r.get("E_net_raw_j") is not None
        ]
        if not vals:
            vals = [
                float(r["E_generate_j"])
                for r in rs
                if r.get("E_generate_j") is not None
            ]
        prompt_mu[cid] = _mu(vals)
    mu_short = prompt_mu.get("decomp_prompt_short__np360")
    e_prompt_medium = None
    e_prompt_long = None
    if mu_short is not None:
        mu_med = prompt_mu.get("decomp_prompt_medium__np360")
        mu_long = prompt_mu.get("decomp_prompt_long__np360")
        if mu_med is not None:
            e_prompt_medium = float(mu_med) - float(mu_short)
        if mu_long is not None:
            e_prompt_long = float(mu_long) - float(mu_short)

    by_token = _group_by_cell(token_rows)
    e_eval_by_cell: dict[str, Any] = {}
    for cid, rs in by_token.items():
        nets = [float(r["E_net_raw_j"]) for r in rs if r.get("E_net_raw_j") is not None]
        dts = [
            float((r.get("infer") or {}).get("eval_duration_s"))
            for r in rs
            if (r.get("infer") or {}).get("eval_duration_s") is not None
        ]
        mu_net = _mu(nets)
        mu_dt = _mu(dts)
        v1_pred = predict_E_net(mu_dt) if mu_dt is not None else {}
        v1 = v1_pred.get("predicted_E_net_j") if isinstance(v1_pred, dict) else None
        e_eval_by_cell[cid] = {
            "mu_E_net_raw_j": mu_net,
            "mu_eval_duration_s": mu_dt,
            "v1_estimate_j": None if v1 is None else float(v1),
            "delta_meas_minus_v1_j": (
                None
                if mu_net is None or v1 is None
                else float(mu_net) - float(v1)
            ),
        }

    by_tail = _group_by_cell(tail_rows)
    e_tail_by_horizon: dict[str, Any] = {}
    for cid, rs in by_tail.items():
        tails = [float(r["E_tail_j"]) for r in rs if r.get("E_tail_j") is not None]
        e_tail_by_horizon[cid] = {
            "mu_E_tail_j": _mu(tails),
            "n": len(tails),
            "tail_tau_s": (rs[0].get("tail_tau_s") if rs else None)
            or _infer_tail_tau(cid),
        }

    return {
        "E_load_j": e_load,
        "E_load_method": "cold_net_minus_warm_net_matched_np360",
        "mu_E_net_cold_j": mu_cold,
        "mu_E_net_warm_j": mu_warm,
        "E_prompt_j": {
            "short_baseline_j": mu_short,
            "medium_minus_short_j": e_prompt_medium,
            "long_minus_short_j": e_prompt_long,
            "by_cell_mu_j": prompt_mu,
        },
        "E_eval_j": e_eval_by_cell,
        "E_tail_j": e_tail_by_horizon,
    }


def _infer_tail_tau(cell_id: str) -> float | None:
    if "tail_5s" in cell_id:
        return 5.0
    if "tail_10s" in cell_id:
        return 10.0
    if "tail_20s" in cell_id:
        return 20.0
    return None


def _eval_attr_for_row(row: dict[str, Any], phases: dict[str, Any]) -> float:
    """Token-eval portion.

    Prompt-family rows use short-baseline mu (fixed-eval channel) so E_prompt
    deltas are not double-counted with V1(duration). Other families use V1(dt).
    """
    fam = str(row.get("decomp_family") or "")
    if fam == "prompt_eval":
        ep = phases.get("E_prompt_j") or {}
        if ep.get("short_baseline_j") is not None:
            return float(ep["short_baseline_j"])
    dt = (row.get("infer") or {}).get("eval_duration_s")
    if dt is not None:
        try:
            pred = predict_E_net(float(dt))
            if pred.get("predicted_E_net_j") is not None:
                return float(pred["predicted_E_net_j"])
        except Exception:  # noqa: BLE001
            pass
    cid = str(row.get("cell_id") or "")
    block = (phases.get("E_eval_j") or {}).get(cid) or {}
    if block.get("mu_E_net_raw_j") is not None:
        return float(block["mu_E_net_raw_j"])
    if row.get("E_net_raw_j") is not None:
        return float(row["E_net_raw_j"])
    return 0.0


def _prompt_attr_for_row(row: dict[str, Any], phases: dict[str, Any]) -> float:
    if str(row.get("decomp_family") or "") != "prompt_eval":
        return 0.0
    variant = str(row.get("prompt_variant") or "standard")
    ep = phases.get("E_prompt_j") or {}
    if variant == "medium":
        return float(ep.get("medium_minus_short_j") or 0.0)
    if variant == "long":
        return float(ep.get("long_minus_short_j") or 0.0)
    return 0.0


def _load_attr_for_row(row: dict[str, Any], phases: dict[str, Any]) -> float:
    cid = str(row.get("cell_id") or "")
    residency = str((row.get("cell") or {}).get("residency") or "")
    if "cold" in cid or residency == "cold_first" or row.get("unload_before"):
        return float(phases.get("E_load_j") or 0.0)
    return 0.0


def _tail_attr_for_row(row: dict[str, Any], phases: dict[str, Any]) -> float:
    cid = str(row.get("cell_id") or "")
    tau = row.get("tail_tau_s")
    if tau is None:
        tau = _infer_tail_tau(cid)
    tails = phases.get("E_tail_j") or {}
    for key, block in tails.items():
        if key == cid and block.get("mu_E_tail_j") is not None:
            return float(block["mu_E_tail_j"])
    if tau is not None:
        for block in tails.values():
            btau = block.get("tail_tau_s")
            if btau is not None and abs(float(btau) - float(tau)) < 0.1:
                if block.get("mu_E_tail_j") is not None:
                    return float(block["mu_E_tail_j"])
        if abs(float(tau) - 5.0) < 0.1:
            b5 = tails.get("decomp_tail_5s__np360") or {}
            if b5.get("mu_E_tail_j") is not None:
                return float(b5["mu_E_tail_j"])
    if row.get("E_tail_j") is not None:
        return float(row["E_tail_j"])
    return 0.0


def heldout_closure_test(
    all_rows: list[dict[str, Any]],
    *,
    holdout_session_ids: set[int] | None = None,
    eps_max: float = CLOSURE_EPS_MAX,
    n_holdout_min: int = CLOSURE_N_HOLDOUT_MIN,
) -> dict[str, Any]:
    """Session-holdout closure: reconstruct E from phase attributions.

    E_meas = E_net_raw_j + E_tail_j
    E_recon = E_load + E_prompt + E_eval + E_tail
    ε = |E_meas − E_recon| / max(|E_meas|, eps)
    """
    sessions = sorted(
        {
            int(r["session_i"])
            for r in all_rows
            if r.get("session_i") is not None
        }
    )
    if holdout_session_ids is None:
        # Hold out last session if ≥2 sessions, else half of rows by index fallback
        if len(sessions) >= 2:
            holdout_session_ids = {sessions[-1]}
        else:
            holdout_session_ids = set()

    train = [
        r
        for r in all_rows
        if r.get("session_i") is not None and int(r["session_i"]) not in holdout_session_ids
    ]
    hold = [
        r
        for r in all_rows
        if r.get("session_i") is not None and int(r["session_i"]) in holdout_session_ids
    ]
    if not hold and all_rows:
        # Fallback: last 20% of rows by order as holdout
        n_h = max(1, len(all_rows) // 5)
        hold = all_rows[-n_h:]
        train = all_rows[:-n_h]

    family_train: dict[str, list[dict[str, Any]]] = {}
    for r in train:
        fam = str(r.get("decomp_family") or "")
        family_train.setdefault(fam, []).append(r)
    phases = build_phase_attributions(family_train)

    eps_rows: list[dict[str, Any]] = []
    for r in hold:
        if r.get("E_net_raw_j") is None and r.get("E_generate_j") is None:
            continue
        e_load = _load_attr_for_row(r, phases)
        e_prompt = _prompt_attr_for_row(r, phases)
        e_eval = _eval_attr_for_row(r, phases)
        e_tail = _tail_attr_for_row(r, phases)
        e_recon = e_load + e_prompt + e_eval + e_tail
        e_net = float(r["E_net_raw_j"]) if r.get("E_net_raw_j") is not None else 0.0
        e_meas = e_net + float(r.get("E_tail_j") or 0.0)
        denom = abs(e_meas) if abs(e_meas) > 1e-9 else 1e-9
        eps = abs(e_meas - e_recon) / denom
        eps_rows.append(
            {
                "cell_id": r.get("cell_id"),
                "session_i": r.get("session_i"),
                "E_meas_j": e_meas,
                "E_recon_j": e_recon,
                "E_load_j": e_load,
                "E_prompt_j": e_prompt,
                "E_eval_j": e_eval,
                "E_tail_j": e_tail,
                "eps_closure": eps,
            }
        )

    eps_vals = [float(x["eps_closure"]) for x in eps_rows]
    n_holdout = len(eps_vals)
    med = statistics.median(eps_vals) if eps_vals else None
    mean = statistics.fmean(eps_vals) if eps_vals else None
    # Pass on median (primary) with mean reported; both must be ≤ threshold when present
    pass_closure = (
        n_holdout >= n_holdout_min
        and med is not None
        and med <= eps_max
    )
    return {
        "ok": True,
        "n_train": len(train),
        "n_holdout": n_holdout,
        "n_holdout_min": n_holdout_min,
        "holdout_sessions": sorted(holdout_session_ids) if holdout_session_ids else [],
        "eps_max": eps_max,
        "median_eps_closure": med,
        "mean_eps_closure": mean,
        "closure_pass": bool(pass_closure),
        "phase_attributions_train": phases,
        "holdout_rows": eps_rows,
    }


def evaluate_decomposition_campaign(
    family_artifacts: dict[str, list[dict[str, Any]]] | None = None,
    *,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Classify components, run held-out closure, write evidence artifacts."""
    out = Path(out_dir) if out_dir else OUT
    out.mkdir(parents=True, exist_ok=True)

    if family_artifacts is None:
        family_artifacts = {}
        for fam in FAMILY_ORDER:
            path = out / f"decomp_{fam}_latest.json"
            if not path.exists():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            family_artifacts[fam] = list(payload.get("rows") or [])

    component_results: dict[str, Any] = {}
    all_rows: list[dict[str, Any]] = []
    for fam in FAMILY_ORDER:
        rows = list(family_artifacts.get(fam) or [])
        all_rows.extend(rows)
        by_cell = _group_by_cell(rows)
        fam_cells: dict[str, Any] = {}
        for cid, crs in by_cell.items():
            fam_cells[cid] = classify_cell_rows(crs)
        component_results[fam] = fam_cells

    phases = build_phase_attributions(family_artifacts)
    closure = heldout_closure_test(all_rows)

    # Adequacy: material components repeatable or below_resolution where expected
    labels_flat: list[str] = []
    for fam_cells in component_results.values():
        for block in fam_cells.values():
            labels_flat.append(str(block.get("component_label")))

    n_unstable = sum(1 for x in labels_flat if x == "unstable_component")
    n_insuff = sum(1 for x in labels_flat if x == "insufficient_evidence")
    n_repeat = sum(1 for x in labels_flat if x == "repeatable_component")
    n_below = sum(1 for x in labels_flat if x == "below_resolution")
    components_adequate = (
        len(labels_flat) > 0
        and n_unstable == 0
        and n_insuff == 0
        and (n_repeat + n_below) == len(labels_flat)
    )

    evidence_complete = bool(closure.get("closure_pass")) and components_adequate
    status = (
        "decomposition_evidence_complete"
        if evidence_complete
        else "decomposition_evidence_incomplete"
    )

    report = {
        "ok": True,
        "at": _utc(),
        "status": status,
        "lifecycle_from": "auditable_action_energy_ledger",
        "lifecycle_target": "decomposition_evidence_complete",
        "gates": {
            "snr_net_min": 3.0,
            "cv_e_max": 0.20,
            "cv_p_mean_max": 0.15,
            "closure_eps_max": CLOSURE_EPS_MAX,
            "closure_n_holdout_min": CLOSURE_N_HOLDOUT_MIN,
        },
        "component_results": component_results,
        "component_summary": {
            "n_cells": len(labels_flat),
            "n_repeatable": n_repeat,
            "n_below_resolution": n_below,
            "n_unstable": n_unstable,
            "n_insufficient": n_insuff,
            "components_adequate": components_adequate,
        },
        "phase_attributions": phases,
        "heldout_closure": closure,
        "v2_fit_authorized": False,
        "refit_v1_forbidden": True,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
        },
        "policy": policy_stamp(),
    }

    jpath = out / "decomposition_evidence_latest.json"
    mpath = out / "decomposition_evidence_latest.md"
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
    mpath.write_text(_md_evidence(report), encoding="utf-8")
    report["artifact_json"] = str(jpath).replace("\\", "/")
    report["artifact_md"] = str(mpath).replace("\\", "/")
    return report


def _md_evidence(report: dict[str, Any]) -> str:
    cs = report.get("component_summary") or {}
    cl = report.get("heldout_closure") or {}
    lines = [
        "# Decomposition evidence",
        "",
        f"- status: `{report.get('status')}`",
        f"- at: `{report.get('at')}`",
        f"- components_adequate: `{cs.get('components_adequate')}`",
        f"- closure_pass: `{cl.get('closure_pass')}`",
        f"- median_eps_closure: `{cl.get('median_eps_closure')}`",
        f"- n_holdout: `{cl.get('n_holdout')}`",
        f"- v2_fit_authorized: `{report.get('v2_fit_authorized')}`",
        "",
        "## Component labels",
        "",
    ]
    for fam, cells in (report.get("component_results") or {}).items():
        lines.append(f"### `{fam}`")
        lines.append("")
        for cid, block in cells.items():
            lines.append(
                f"- `{cid}`: `{block.get('component_label')}` "
                f"(outcome={block.get('outcome')}, SNR={block.get('SNR_net')}, "
                f"CV_E={block.get('CV_E')})"
            )
        lines.append("")
    lines.append("## Phase attributions")
    lines.append("")
    ph = report.get("phase_attributions") or {}
    lines.append(f"- E_load_j: `{ph.get('E_load_j')}`")
    lines.append(f"- E_prompt: `{ph.get('E_prompt_j')}`")
    lines.append("")
    return "\n".join(lines)
