#!/usr/bin/env python3
"""Unit tests for V2 candidate stack (no plant run)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_decomposition_corpus_freeze import (  # noqa: E402
    load_frozen_corpus,
    write_freeze,
)
from lib.rid_electrical_policy import (  # noqa: E402
    ACCOUNTING_PREDICTOR_V2_APPROVED,
    PREDICTOR_V1_FROZEN,
    apply_v2_candidate_verdict,
)
from lib.rid_electrical_predictor import ALPHA, BETA  # noqa: E402
from lib.rid_electrical_predictor_v2 import (  # noqa: E402
    clear_candidate_cache,
    predict_E_action,
)
from lib.rid_electrical_v2_fit import (  # noqa: E402
    decision_ladder,
    featurize_rows,
    fit_model,
    nnls,
    run_v2_fit_pipeline,
    session_split,
)
from lib.rid_electrical_v2_shadow import shadow_account_v2  # noqa: E402
import numpy as np  # noqa: E402


def test_freeze_and_hash_guard() -> None:
    out = FOUNDATION / "artifacts" / "auto" / "rid_electrical" / "ledger_campaign"
    manifest = write_freeze(out_dir=out)
    assert manifest.get("immutable") is True
    assert manifest.get("fit_must_not_modify") is True
    assert manifest.get("n_actions") == 60
    m2, rows = load_frozen_corpus(out_dir=out, verify_hashes=True)
    assert len(rows) == 60
    assert m2.get("freeze_id") == "DECOMPOSITION_CORPUS_FROZEN_V1"


def test_session_split_no_leak() -> None:
    rows = [
        {"session_i": s, "infer": {"eval_duration_s": 3.5, "prompt_eval_duration_s": 0.1},
         "E_net_raw_j": 400.0, "E_tail_j": 600.0, "tail_tau_s": 5.0,
         "residency": "warm_repeat", "cell_id": "x"}
        for s in range(1, 6)
        for _ in range(3)
    ]
    feats = featurize_rows(rows)
    split = session_split(feats)
    assert split["ok"] is True
    assert split["leak_sessions"] == []
    train_s = {f["session_i"] for f in split["train"]}
    hold_s = {f["session_i"] for f in split["holdout"]}
    assert train_s.isdisjoint(hold_s)


def test_nnls_nonneg() -> None:
    rng = np.random.default_rng(0)
    X = np.abs(rng.normal(size=(40, 3)))
    beta_true = np.array([10.0, 2.0, 5.0])
    y = X @ beta_true + rng.normal(scale=0.1, size=40)
    beta = nnls(X, y)
    assert np.all(beta >= -1e-9)


def test_v1_not_mutated() -> None:
    a0, b0 = ALPHA, BETA
    assert PREDICTOR_V1_FROZEN is True
    # Fit on frozen corpus must not change module constants
    out = FOUNDATION / "artifacts" / "auto" / "rid_electrical" / "ledger_campaign"
    _, rows = load_frozen_corpus(out_dir=out, verify_hashes=True)
    run_v2_fit_pipeline(rows)
    assert ALPHA == a0 and BETA == b0
    assert PREDICTOR_V1_FROZEN is True
    assert ACCOUNTING_PREDICTOR_V2_APPROVED is False


def test_authority_false_and_ladder() -> None:
    clear_candidate_cache()
    pred = predict_E_action(
        t_eval_s=3.5,
        t_prompt_s=0.2,
        tail_horizon_s=5.0,
        residency="warm_repeat",
    )
    # May be ok if candidate exists from prior fit
    assert pred.get("operational_authority") is False
    assert pred.get("auto_admit") is False
    assert pred.get("accounting_predictor_v2_approved") is False

    lad = decision_ladder(
        gates_pass=True,
        overlap={"v2_improves_overlap": False},
        expands_coverage=True,
    )
    assert lad["decision"] == "keep_both_domain_registry"
    assert lad["proceed_to_prospective"] is True

    lad2 = decision_ladder(
        gates_pass=False,
        overlap={"v2_improves_overlap": True},
        expands_coverage=True,
    )
    assert lad2["decision"] == "retain_v1_decomposition_diagnostic_only"


def test_shadow_no_approval() -> None:
    tmp = FOUNDATION / "artifacts" / "auto" / "rid_electrical" / "ledger_campaign" / "_test_v2_shadow.jsonl"
    if tmp.exists():
        tmp.unlink()
    # shadow_account_v2 uses default log; call with append False path via direct
    row = shadow_account_v2(
        action_id="test",
        session_id="s",
        t_eval_s=3.5,
        t_prompt_s=0.2,
        tail_horizon_s=5.0,
        residency="warm_repeat",
        measured_E_net_j=480.0,
        measured_E_tail_j=620.0,
        append=False,
    )
    assert row.get("accounting_predictor_v2_approved") is False
    assert row.get("operational_authority") is False
    assert row.get("gates_action") is False


def test_ablation_prefers_duration_without_gain() -> None:
    out = FOUNDATION / "artifacts" / "auto" / "rid_electrical" / "ledger_campaign"
    _, rows = load_frozen_corpus(out_dir=out, verify_hashes=True)
    pipe = run_v2_fit_pipeline(rows)
    assert pipe.get("ok")
    # Token ablation should not keep tokens unless ≥5% gain (corpus typically duration-only)
    assert pipe["ablation"]["keep_tokens"] is False
    assert pipe["coefficients"]["E_load_cold_j"] >= 0
    assert pipe["coefficients"]["beta_eval_j_per_s"] >= 0
    for v in pipe["coefficients"]["E_tail_by_horizon_j"].values():
        assert float(v) >= 0


def test_apply_v2_candidate_no_approval() -> None:
    r = apply_v2_candidate_verdict(True)
    assert r["v2_predictor_candidate"] is True
    assert r["accounting_predictor_v2_approved"] is False
    assert r["predictor_v1_frozen"] is True
    apply_v2_candidate_verdict(False)


def main() -> int:
    test_freeze_and_hash_guard()
    test_session_split_no_leak()
    test_nnls_nonneg()
    test_v1_not_mutated()
    test_authority_false_and_ladder()
    test_shadow_no_approval()
    test_ablation_prefers_duration_without_gain()
    test_apply_v2_candidate_no_approval()
    print(json.dumps({"ok": True, "tests": "v2_predictor_candidate"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
