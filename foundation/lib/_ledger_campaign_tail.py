def evaluate_cell_repeatability(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Classify one cell: repeatable_signature | unstable_signature | insufficient_evidence."""
    valid = [
        r
        for r in rows
        if r.get("confidence") in {"valid", "degraded"} and r.get("E_net_j") is not None
    ]
    strict = [r for r in valid if r.get("confidence") == "valid"]
    use = strict if len(strict) >= MIN_REPEATS else valid
    e_vals = [float(r["E_net_j"]) for r in use]
    p_vals = [float(r["P_peak_w"]) for r in use if r.get("P_peak_w") is not None]
    cv_e = _cv(e_vals)
    cv_p = _cv(p_vals)
    mu_e = statistics.fmean(e_vals) if e_vals else None
    mu_p = statistics.fmean(p_vals) if p_vals else None
    sig_e = statistics.pstdev(e_vals) if len(e_vals) > 1 else (0.0 if e_vals else None)
    sig_p = statistics.pstdev(p_vals) if len(p_vals) > 1 else (0.0 if p_vals else None)
    n = len(use)
    n_rows = len(rows)
    missing_or_degraded = n_rows - len(strict)

    if n < MIN_REPEATS or (not e_vals):
        outcome = "insufficient_evidence"
        reasons: list[str] = []
        if n < MIN_REPEATS:
            reasons.append(f"n_valid={n}<{MIN_REPEATS}")
        if missing_or_degraded and n < MIN_REPEATS:
            reasons.append("missing_or_degraded_repeats")
        if not e_vals:
            reasons.append("no_E_net")
    elif (
        cv_e is not None
        and cv_p is not None
        and cv_e <= CV_E_MAX
        and cv_p <= CV_P_MAX
        and mu_e is not None
        and mu_e > 0
    ):
        outcome = "repeatable_signature"
        reasons = []
    else:
        outcome = "unstable_signature"
        reasons = []
        if cv_e is not None and cv_e > CV_E_MAX:
            reasons.append(f"CV_E={cv_e:.3f}>{CV_E_MAX}")
        if cv_p is not None and cv_p > CV_P_MAX:
            reasons.append(f"CV_P={cv_p:.3f}>{CV_P_MAX}")
        if mu_e is not None and mu_e <= 0:
            reasons.append("non_positive_mu_E_net")
        if cv_e is None or cv_p is None:
            reasons.append("cv_undefined")

    return {
        "n_rows": n_rows,
        "n_valid": n,
        "n_strict_valid": len(strict),
        "valid_frac": n / max(1, n_rows),
        "mu_E_net_j": mu_e,
        "sigma_E_net_j": sig_e,
        "CV_E": cv_e,
        "mu_P_peak_w": mu_p,
        "sigma_P_peak_w": sig_p,
        "CV_P": cv_p,
        "gates": {
            "CV_E_MAX": CV_E_MAX,
            "CV_P_MAX": CV_P_MAX,
            "MIN_REPEATS": MIN_REPEATS,
            "MIN_VALID_FRAC": MIN_VALID_FRAC,
        },
        "outcome": outcome,
        "outcome_reasons": reasons,
        "repeatable": outcome == "repeatable_signature",
        "learning_eligible_cell": outcome == "repeatable_signature",
    }


def _pooled_uncertainty(
    sig_a: float | None, n_a: int, sig_b: float | None, n_b: int
) -> float | None:
    if sig_a is None or sig_b is None or n_a < 2 or n_b < 2:
        return None
    num = (n_a - 1) * (sig_a**2) + (n_b - 1) * (sig_b**2)
    den = n_a + n_b - 2
    if den <= 0:
        return None
    return math.sqrt(num / den)


def evaluate_factor_separability(
    cell_reports: dict[str, dict[str, Any]],
    *,
    factor: str,
) -> dict[str, Any]:
    """|μ_a-μ_b| must exceed pooled within-cell uncertainty."""
    cells = []
    for cell_id, rep in cell_reports.items():
        if not cell_id.startswith(f"{factor}__"):
            continue
        if rep.get("mu_E_net_j") is None:
            continue
        cells.append((cell_id, rep))
    pairs = []
    distinguishable = 0
    for i in range(len(cells)):
        for j in range(i + 1, len(cells)):
            id_a, a = cells[i]
            id_b, b = cells[j]
            mu_a = float(a["mu_E_net_j"])
            mu_b = float(b["mu_E_net_j"])
            delta = abs(mu_a - mu_b)
            pooled = _pooled_uncertainty(
                a.get("sigma_E_net_j"),
                int(a.get("n_valid") or 0),
                b.get("sigma_E_net_j"),
                int(b.get("n_valid") or 0),
            )
            both_rep = bool(a.get("repeatable")) and bool(b.get("repeatable"))
            sep_ok = pooled is not None and delta > pooled and both_rep
            if sep_ok:
                distinguishable += 1
            pairs.append(
                {
                    "a": id_a,
                    "b": id_b,
                    "abs_delta_mu_E": delta,
                    "pooled_within_sigma_E": pooled,
                    "separable": bool(sep_ok),
                    "both_repeatable": both_rep,
                    "rel_sep": delta / max(abs(mu_a), abs(mu_b), 1.0),
                }
            )
    return {
        "factor": factor,
        "n_cells": len(cells),
        "n_pairs": len(pairs),
        "n_separable_pairs": distinguishable,
        "factor_separable": distinguishable >= 1,
        "pairs": pairs,
    }


def evaluate_learning_admission(cell_reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Never auto-admits. Emits reviewable candidate status only."""
    outcome_counts = {
        "repeatable_signature": 0,
        "unstable_signature": 0,
        "insufficient_evidence": 0,
    }
    for rep in cell_reports.values():
        oc = str(rep.get("outcome") or "insufficient_evidence")
        outcome_counts[oc] = outcome_counts.get(oc, 0) + 1

    passing = {
        k: v for k, v in cell_reports.items() if v.get("outcome") == "repeatable_signature"
    }
    factors = sorted({cid.split("__", 1)[0] for cid in cell_reports})
    sep_by_factor = {
        f: evaluate_factor_separability(cell_reports, factor=f) for f in factors
    }
    separable_factors = [f for f, s in sep_by_factor.items() if s.get("factor_separable")]

    n_unstable = outcome_counts.get("unstable_signature", 0)
    if passing and separable_factors:
        decision = "predictor_dataset_candidate"
        decision_note = (
            "Repeatable within cells and separable between conditions — "
            "reviewable predictor dataset candidate only (auto_admit=false)."
        )
    elif passing and not separable_factors:
        decision = "accounting_ledger_only"
        decision_note = (
            "Repeatable within cells but not separable between conditions — "
            "keep as accounting ledger only."
        )
    elif n_unstable > 0 and not passing:
        decision = "improve_controls_or_instrumentation"
        decision_note = (
            "Unstable within cells — improve experimental controls or instrumentation."
        )
    elif n_unstable > 0 and passing:
        decision = "train_only_passing_factors_cells"
        decision_note = (
            "Mixed results — any future learning may use only factors/cells that "
            "independently pass; still requires explicit review (auto_admit=false)."
        )
    else:
        decision = "insufficient_evidence"
        decision_note = "Insufficient independent repeats or valid samples."

    return {
        "learning_admission_withheld": True,
        "learning_admission_granted": False,
        "auto_admit": False,
        "campaign_decision": decision,
        "campaign_decision_note": decision_note,
        "cell_outcome_counts": outcome_counts,
        "n_cells": len(cell_reports),
        "n_repeatable_cells": len(passing),
        "repeatable_cell_ids": sorted(passing.keys()),
        "separability_by_factor": sep_by_factor,
        "separable_factors": separable_factors,
        "criteria": {
            "CV_E_MAX": CV_E_MAX,
            "CV_P_MAX": CV_P_MAX,
            "MIN_REPEATS": MIN_REPEATS,
            "separability": "|mu_a-mu_b| > pooled_within_cell_sigma_E",
            "auto_admit": False,
        },
        "state": {
            "accounting_implemented": True,
            "measurements_valid": True,
            "cost_signatures_repeatable": len(passing) > 0,
            "learning_admission_withheld": True,
        },
        "note": (
            "Even a fully passing campaign yields a reviewable learning-candidate "
            "artifact only; never automatic predictor authorization."
        ),
    }


def write_learning_candidate(summary: dict[str, Any]) -> dict[str, Any]:
    """Reviewable artifact — never grants predictor authority."""
    adm = summary.get("learning_admission") or {}
    decision = adm.get("campaign_decision")
    candidate = {
        "ok": True,
        "at": summary.get("at"),
        "artifact_type": "learning_candidate_review",
        "auto_admit": False,
        "predictor_authorized": False,
        "learning_admission_granted": False,
        "campaign_decision": decision,
        "campaign_decision_note": adm.get("campaign_decision_note"),
        "is_predictor_dataset_candidate": decision == "predictor_dataset_candidate",
        "passing_cells": adm.get("repeatable_cell_ids") or [],
        "separable_factors": adm.get("separable_factors") or [],
        "cell_outcome_counts": adm.get("cell_outcome_counts"),
        "criteria": adm.get("criteria"),
        "review_required": True,
        "note": (
            "Reviewable only. Do not create or authorize an energy predictor "
            "without explicit operator approval after this artifact."
        ),
    }
    path = OUT_DIR / "learning_candidate_latest.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    md = OUT_DIR / "learning_candidate_latest.md"
    md.write_text(
        "\n".join(
            [
                "# Energy learning candidate (REVIEW ONLY)",
                "",
                f"- **Decision:** `{decision}`",
                "- **Predictor authorized:** false",
                "- **auto_admit:** false",
                f"- **Passing cells:** {candidate['passing_cells']}",
                f"- **Separable factors:** {candidate['separable_factors']}",
                "",
                str(adm.get("campaign_decision_note") or ""),
                "",
            ]
        ),
        encoding="utf-8",
    )
    candidate["artifact_json"] = str(path).replace("\\", "/")
    candidate["artifact_md"] = str(md).replace("\\", "/")
    return candidate


def summarize_campaign(action_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_cell: dict[str, list[dict[str, Any]]] = {}
    for r in action_rows:
        cid = (r.get("cell") or {}).get("cell_id") or "unknown"
        by_cell.setdefault(cid, []).append(r)
    cell_reports = {cid: evaluate_cell_repeatability(rows) for cid, rows in by_cell.items()}
    admission = evaluate_learning_admission(cell_reports)
    summary = {
        "ok": True,
        "at": _utc(),
        "experiment_id": "rid_electrical_ledger_campaign_v1",
        "n_actions": len(action_rows),
        "n_cells": len(by_cell),
        "cells": cell_reports,
        "learning_admission": admission,
        "predictor_blocked": True,
        "auto_admit": False,
        "authority": "controlled_ledger_only",
        "enters_A_t": False,
        "enters_master_s_n": False,
    }
    summary["learning_candidate"] = write_learning_candidate(summary)
    return summary
