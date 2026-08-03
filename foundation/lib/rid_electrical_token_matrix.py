#!/usr/bin/env python3
"""Token-energy matrix v2: rotated warm-repeat cells above net resolution floor.

Admission cells: num_predict ∈ {256, 384, 512} × 5 repeats.
768 is forensic-only and excluded from separability / learning candidate.

Milestone: repeatable and separable token-energy signatures (not a predictor).
Learning remains withheld (auto_admit=false).
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Sequence

from lib.rid_electrical_ledger_controls import (
    ControlCell,
    evaluate_control_repeats,
)

# Admission matrix levels (256 is a validated passing point, not a ≥256 blanket).
ADMISSION_NUM_PREDICT: tuple[int, ...] = (256, 384, 512)
FORENSIC_NUM_PREDICT = 768

# Five sessions; each np appears once per session → 5 repeats/cell.
SESSION_ORDERS: tuple[tuple[int, ...], ...] = (
    (256, 384, 512),
    (512, 256, 384),
    (384, 512, 256),
    (256, 512, 384),
    (512, 384, 256),
)


def cell_id_for(num_predict: int, *, forensic: bool = False) -> str:
    if forensic or num_predict == FORENSIC_NUM_PREDICT:
        return f"tokens_np{num_predict}__warm_forensic"
    return f"tokens_np{num_predict}__warm_repeat"


def make_cell(num_predict: int, *, forensic: bool = False) -> ControlCell:
    return ControlCell(
        cell_id=cell_id_for(num_predict, forensic=forensic),
        residency="warm_repeat",
        num_predict=int(num_predict),
        token_bucket=f"np_{num_predict}",
    )


def rotation_coverage(orders: Sequence[Sequence[int]] = SESSION_ORDERS) -> dict[str, Any]:
    """Verify each admission np appears exactly once per session and len(orders) times."""
    counts: dict[int, int] = {np: 0 for np in ADMISSION_NUM_PREDICT}
    per_session_ok = True
    for order in orders:
        if sorted(order) != sorted(ADMISSION_NUM_PREDICT):
            per_session_ok = False
        for np in order:
            counts[np] = counts.get(np, 0) + 1
    n_sessions = len(orders)
    return {
        "ok": per_session_ok and all(counts.get(np) == n_sessions for np in ADMISSION_NUM_PREDICT),
        "n_sessions": n_sessions,
        "counts": counts,
        "expected_per_np": n_sessions,
        "orders": [list(o) for o in orders],
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


def evaluate_separability(
    cell_reports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """|μ_a-μ_b| > pooled within-cell σ among net_signature_repeatable cells only."""
    passing = [
        (cid, rep)
        for cid, rep in cell_reports.items()
        if rep.get("outcome") == "net_signature_repeatable"
        and not str(cid).endswith("__warm_forensic")
        and rep.get("mu_E_net_raw_j") is not None
    ]
    pairs: list[dict[str, Any]] = []
    n_sep = 0
    for i in range(len(passing)):
        for j in range(i + 1, len(passing)):
            id_a, a = passing[i]
            id_b, b = passing[j]
            mu_a = float(a["mu_E_net_raw_j"])
            mu_b = float(b["mu_E_net_raw_j"])
            delta = abs(mu_a - mu_b)
            pooled = _pooled_uncertainty(
                a.get("sigma_E_net_raw_j"),
                int(a.get("n_usable") or 0),
                b.get("sigma_E_net_raw_j"),
                int(b.get("n_usable") or 0),
            )
            sep_ok = pooled is not None and delta > pooled
            if sep_ok:
                n_sep += 1
            pairs.append(
                {
                    "a": id_a,
                    "b": id_b,
                    "mu_a": mu_a,
                    "mu_b": mu_b,
                    "abs_delta_mu_E": delta,
                    "pooled_within_sigma_E": pooled,
                    "separable": bool(sep_ok),
                    "rel_sep": delta / max(abs(mu_a), abs(mu_b), 1.0),
                }
            )
    n_pairs = len(pairs)
    return {
        "n_passing_cells": len(passing),
        "n_pairs": n_pairs,
        "n_separable_pairs": n_sep,
        "all_pairs_separable": n_pairs > 0 and n_sep == n_pairs,
        "pairs": pairs,
    }


def _energy_rises_with_np(cell_reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Check μ(E_net) increases with num_predict among admission passing cells."""
    pts = []
    for cid, rep in cell_reports.items():
        if rep.get("outcome") != "net_signature_repeatable":
            continue
        if str(cid).endswith("__warm_forensic"):
            continue
        # cell_id tokens_np256__warm_repeat
        try:
            mid = cid.split("__", 1)[0]  # tokens_np256
            np = int(mid.replace("tokens_np", ""))
        except (ValueError, IndexError):
            continue
        mu = rep.get("mu_E_net_raw_j")
        if mu is None:
            continue
        pts.append((np, float(mu), cid))
    pts.sort(key=lambda x: x[0])
    rises = True
    for i in range(1, len(pts)):
        if pts[i][1] <= pts[i - 1][1]:
            rises = False
            break
    return {
        "n_points": len(pts),
        "points": [{"num_predict": n, "mu_E_net_j": m, "cell_id": c} for n, m, c in pts],
        "energy_rises_with_np": bool(rises and len(pts) >= 2),
    }


def classify_milestone(
    cell_reports: dict[str, dict[str, Any]],
    separability: dict[str, Any],
) -> dict[str, Any]:
    """Four-way campaign decision; never grants learning admission."""
    admission = {
        cid: rep
        for cid, rep in cell_reports.items()
        if not str(cid).endswith("__warm_forensic")
    }
    forensic = {
        cid: rep
        for cid, rep in cell_reports.items()
        if str(cid).endswith("__warm_forensic")
    }
    outcomes = {cid: rep.get("outcome") for cid, rep in admission.items()}
    passing_ids = [
        cid
        for cid, oc in outcomes.items()
        if oc == "net_signature_repeatable"
    ]
    unstable_ids = [
        cid for cid, oc in outcomes.items() if oc == "unstable_signature"
    ]
    n_admission = len(admission)
    n_pass = len(passing_ids)
    all_pass = n_admission >= 3 and n_pass == n_admission
    sep = bool(separability.get("all_pairs_separable"))
    trend = _energy_rises_with_np(admission)
    rises = bool(trend.get("energy_rises_with_np"))

    if all_pass and sep and rises:
        decision = "token_cost_curve_reviewable"
        note = (
            "All admission cells net-repeatable, pairwise separable, and "
            "μ(E_net) rises with num_predict — reviewable token-cost curve only."
        )
    elif n_pass >= 2 and not sep:
        decision = "accounting_stable_tokens_not_explanatory"
        note = (
            "Cells repeatable (or partially) but energy means overlap — "
            "accounting stable; token count not sufficiently explanatory."
        )
    elif n_pass >= 1 and (unstable_ids or n_pass < n_admission):
        decision = "investigate_unstable_cells"
        note = (
            "Some cells unstable or incomplete — investigate listed cells; "
            "do not train across them."
        )
    elif all_pass and sep and not rises:
        decision = "accounting_stable_tokens_not_explanatory"
        note = (
            "All cells repeatable and separable but energy does not rise "
            "monotonically with num_predict — not a clean token-cost curve."
        )
    else:
        decision = "ledger_descriptive_only"
        note = "No stable separable token-energy relationship — keep ledger descriptive only."

    return {
        "milestone": "repeatable_and_separable_token_energy_signatures",
        "campaign_decision": decision,
        "campaign_decision_note": note,
        "n_admission_cells": n_admission,
        "n_repeatable": n_pass,
        "repeatable_cell_ids": sorted(passing_ids),
        "unstable_cell_ids": sorted(unstable_ids),
        "cell_outcomes": outcomes,
        "all_admission_repeatable": all_pass,
        "all_pairs_separable": sep,
        "energy_trend": trend,
        "forensic_cells": {
            cid: {"outcome": rep.get("outcome"), "excluded_from_admission": True}
            for cid, rep in forensic.items()
        },
        "learning_admission_withheld": True,
        "learning_admission_granted": False,
        "auto_admit": False,
        "predictor_authorized": False,
        "note_256": (
            "num_predict=256 is the minimum validated passing point from "
            "calibration — not proof that every np≥256 passes."
        ),
    }


def evaluate_token_matrix(
    rows: Sequence[dict[str, Any]],
    *,
    forensic_rows: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Per-cell mean-primary eval + separability + milestone decision."""
    by_cell: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        cid = (r.get("cell") or {}).get("cell_id") or r.get("cell_id") or "unknown"
        by_cell.setdefault(str(cid), []).append(r)
    if forensic_rows:
        for r in forensic_rows:
            cid = (r.get("cell") or {}).get("cell_id") or r.get("cell_id") or "unknown"
            by_cell.setdefault(str(cid), []).append(r)

    cell_reports: dict[str, dict[str, Any]] = {}
    for cid, cell_rows in by_cell.items():
        rep = evaluate_control_repeats(cell_rows, cv_p_primary="mean_from_E")
        # Extract num_predict if present
        np = None
        if cell_rows:
            np = (cell_rows[0].get("cell") or {}).get("num_predict")
        rep["cell_id"] = cid
        rep["num_predict"] = np
        rep["forensic"] = str(cid).endswith("__warm_forensic")
        cell_reports[cid] = rep

    sep = evaluate_separability(cell_reports)
    milestone = classify_milestone(cell_reports, sep)
    return {
        "ok": True,
        "experiment_id": "rid_electrical_token_matrix_v2",
        "admission_num_predict": list(ADMISSION_NUM_PREDICT),
        "n_actions": len(rows),
        "n_forensic_actions": len(forensic_rows or []),
        "cells": cell_reports,
        "separability": sep,
        "milestone": milestone,
        "learning_admission_withheld": True,
        "auto_admit": False,
        "predictor_authorized": False,
        "cv_p_primary": "mean_from_E",
        "rotation": rotation_coverage(),
    }


def write_token_cost_curve_review(summary: dict[str, Any], out_dir) -> dict[str, Any] | None:
    """Emit review-only curve artifact when decision earns it."""
    from pathlib import Path

    ms = summary.get("milestone") or {}
    if ms.get("campaign_decision") != "token_cost_curve_reviewable":
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    points = (ms.get("energy_trend") or {}).get("points") or []
    payload = {
        "ok": True,
        "artifact_type": "token_cost_curve_review",
        "auto_admit": False,
        "predictor_authorized": False,
        "learning_admission_granted": False,
        "review_required": True,
        "campaign_decision": ms.get("campaign_decision"),
        "points": points,
        "separability": summary.get("separability"),
        "passing_cells": ms.get("repeatable_cell_ids"),
        "note": (
            "Reviewable token-cost curve only. Do not authorize an energy "
            "predictor without explicit operator approval."
        ),
    }
    import json

    jpath = out_dir / "token_cost_curve_review_latest.json"
    mpath = out_dir / "token_cost_curve_review_latest.md"
    jpath.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# Token-cost curve (REVIEW ONLY)",
        "",
        "- **Predictor authorized:** false",
        "- **auto_admit:** false",
        f"- **Passing cells:** {payload['passing_cells']}",
        "",
        "## Points",
        "",
    ]
    for pt in points:
        lines.append(
            f"- np={pt.get('num_predict')}: μ(E_net)={pt.get('mu_E_net_j')} "
            f"({pt.get('cell_id')})"
        )
    lines.append("")
    mpath.write_text("\n".join(lines), encoding="utf-8")
    payload["artifact_json"] = str(jpath).replace("\\", "/")
    payload["artifact_md"] = str(mpath).replace("\\", "/")
    return payload
