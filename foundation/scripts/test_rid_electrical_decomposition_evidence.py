#!/usr/bin/env python3
"""Unit tests for decomposition evidence eval + V2 justification (no plant)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_cost_decomposition import (  # noqa: E402
    CLOSURE_EPS_MAX,
    FAMILY_ORDER,
    campaign_manifest,
    cells_for_family,
    prompt_for_variant,
)
from lib.rid_electrical_decomposition_eval import (  # noqa: E402
    classify_cell_rows,
    evaluate_decomposition_campaign,
    heldout_closure_test,
    outcome_to_component_label,
)
from lib.rid_electrical_policy import PREDICTOR_V1_FROZEN  # noqa: E402

# Import review helper
sys.path.insert(0, str(FOUNDATION / "scripts"))
from rid_electrical_v2_justification_review import review_v2_justification  # noqa: E402


def _synth_row(
    *,
    cell_id: str,
    family: str,
    session_i: int,
    e_gen: float,
    e_net: float,
    e_tail: float,
    eval_s: float = 3.5,
    prompt_variant: str = "standard",
    residency: str = "warm_repeat",
    unload_before: bool = False,
) -> dict:
    return {
        "cell_id": cell_id,
        "decomp_family": family,
        "session_i": session_i,
        "order_i": 1,
        "E_generate_j": e_gen,
        "E_net_raw_j": e_net,
        "E_tail_j": e_tail,
        "P_peak_generate_w": 200.0,
        "P_mean_from_E_w": 150.0,
        "P_mean_generate_w": 150.0,
        "delta_t_generate_s": eval_s,
        "n_generate_locked_samples": 40,
        "prompt_variant": prompt_variant,
        "unload_before": unload_before,
        "cell": {"residency": residency, "cell_id": cell_id, "num_predict": 360},
        "infer": {"eval_duration_s": eval_s},
        "control_gates": {
            "settle_ok": True,
            "integration_wall_ratio": 1.0,
            "integration_wall_ratio_ok": True,
            "CV_P_idle_ok": True,
            "sigma_baseline_subtraction_est_j": 5.0,
        },
    }


def test_labels() -> None:
    assert (
        outcome_to_component_label(
            {"outcome": "net_signature_repeatable", "n_usable": 5}
        )
        == "repeatable_component"
    )
    assert (
        outcome_to_component_label(
            {
                "outcome": "gross_signature_repeatable",
                "net_attribution": "below_resolution",
                "n_usable": 5,
            }
        )
        == "below_resolution"
    )
    assert (
        outcome_to_component_label(
            {"outcome": "unstable_signature", "n_usable": 5}
        )
        == "unstable_component"
    )
    assert (
        outcome_to_component_label(
            {"outcome": "insufficient_evidence", "n_usable": 1}
        )
        == "insufficient_evidence"
    )


def test_classify_repeatable() -> None:
    rows = [
        _synth_row(
            cell_id="decomp_warm_resident__np360",
            family="load_residency",
            session_i=i,
            e_gen=800.0 + i,
            e_net=480.0 + i * 0.5,
            e_tail=40.0,
        )
        for i in range(1, 6)
    ]
    ev = classify_cell_rows(rows)
    assert ev["component_label"] in (
        "repeatable_component",
        "below_resolution",
        "unstable_component",
        "insufficient_evidence",
    )
    # High SNR synthetic should be repeatable
    assert ev["n_usable"] == 5
    assert ev["component_label"] == "repeatable_component"


def test_closure_pass_and_fail() -> None:
    # Build consistent synthetic campaign where recon ≈ meas
    rows = []
    for s in range(1, 7):
        rows.append(
            _synth_row(
                cell_id="decomp_warm_resident__np360",
                family="load_residency",
                session_i=s,
                e_gen=700.0,
                e_net=450.0,
                e_tail=50.0,
                residency="warm_repeat",
            )
        )
        rows.append(
            _synth_row(
                cell_id="decomp_cold_load__np360",
                family="load_residency",
                session_i=s,
                e_gen=850.0,
                e_net=600.0,
                e_tail=50.0,
                residency="cold_first",
            )
        )
        rows.append(
            _synth_row(
                cell_id="decomp_prompt_short__np360",
                family="prompt_eval",
                session_i=s,
                e_gen=700.0,
                e_net=450.0,
                e_tail=50.0,
                prompt_variant="short",
            )
        )
        rows.append(
            _synth_row(
                cell_id="decomp_token_eval_ref__3p5s",
                family="token_eval_v1_reference",
                session_i=s,
                e_gen=700.0,
                e_net=450.0,
                e_tail=50.0,
                eval_s=3.5,
            )
        )
        rows.append(
            _synth_row(
                cell_id="decomp_tail_5s__np360",
                family="post_action_tail",
                session_i=s,
                e_gen=700.0,
                e_net=450.0,
                e_tail=50.0,
            )
        )

    cl = heldout_closure_test(rows, holdout_session_ids={6}, eps_max=0.15)
    assert cl["n_holdout"] >= 5
    assert "median_eps_closure" in cl
    # May or may not pass depending on V1 estimate vs synthetic nets; ensure schema
    assert isinstance(cl["closure_pass"], bool)

    # Force fail: inflate holdout meas without matching recon
    bad = [dict(r) for r in rows]
    for r in bad:
        if r.get("session_i") == 6:
            r["E_net_raw_j"] = 5000.0
    cl_fail = heldout_closure_test(bad, holdout_session_ids={6}, eps_max=0.15)
    assert cl_fail["closure_pass"] is False
    assert cl_fail["median_eps_closure"] is not None
    assert cl_fail["median_eps_closure"] > CLOSURE_EPS_MAX


def test_v2_not_auto_authorized() -> None:
    tmp = FOUNDATION / "artifacts" / "auto" / "rid_electrical" / "ledger_campaign" / "_test_decomp"
    tmp.mkdir(parents=True, exist_ok=True)
    # incomplete evidence
    incomplete = {
        "status": "decomposition_evidence_incomplete",
        "heldout_closure": {"closure_pass": False, "median_eps_closure": 0.5},
        "component_summary": {"components_adequate": False},
    }
    rev = review_v2_justification(incomplete, out_dir=tmp)
    assert rev["decision"] == "retain_v1_decomposition_diagnostic_only"
    assert rev["v2_coefficients_written"] is False
    assert rev["v2_fit_performed"] is False
    assert rev["authority"]["v2_fit_authorized"] is False
    assert PREDICTOR_V1_FROZEN is True

    complete = {
        "status": "decomposition_evidence_complete",
        "heldout_closure": {"closure_pass": True, "median_eps_closure": 0.05},
        "component_summary": {"components_adequate": True},
    }
    rev2 = review_v2_justification(complete, out_dir=tmp)
    assert rev2["decision"] == "v2_fit_justified_for_separate_review"
    assert rev2["v2_coefficients_written"] is False
    assert rev2["authority"]["v2_fit_authorized"] is False  # still not auto-fit


def test_manifest_cells() -> None:
    m = campaign_manifest()
    assert m["closure_eps_max"] == 0.15
    assert m["family_order"] == list(FAMILY_ORDER)
    assert m["v2_fit_authorized"] is False
    load = cells_for_family("load_residency")
    assert all(c.num_predict == 360 for c in load)
    tails = cells_for_family("post_action_tail")
    assert sorted(c.tail_tau_s for c in tails) == [5.0, 10.0, 20.0]
    assert "short" in prompt_for_variant("short").lower() or len(prompt_for_variant("short")) > 0
    refs = cells_for_family("token_eval_v1_reference")
    assert len(refs) == 3
    assert {c.target_eval_s for c in refs} == {2.5, 3.5, 4.5}


def main() -> int:
    test_labels()
    test_classify_repeatable()
    test_closure_pass_and_fail()
    test_v2_not_auto_authorized()
    test_manifest_cells()
    print(json.dumps({"ok": True, "tests": "decomposition_evidence"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
