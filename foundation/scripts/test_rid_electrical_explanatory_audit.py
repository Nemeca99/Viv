#!/usr/bin/env python3
"""Unit tests for explanatory audit (no live Ollama, no plant run)."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_explanatory_audit import (  # noqa: E402
    CANDIDATE_KEYS,
    _pearson_r2,
    _spearman,
    _tertile_bins,
    classify_candidate,
    evaluate_bins,
    run_audit,
    separability_bins,
)


def _feat(
    *,
    eval_dur: float,
    actual_tokens: int,
    e_net: float,
    e_gen: float,
    num_predict: int,
    gpu_temp: float = 55.0,
    dt: float = 3.0,
    sigma: float = 5.0,
) -> dict:
    tps = actual_tokens / eval_dur if eval_dur > 0 else None
    P_mean = e_gen / dt if dt > 0 else None
    P_active_net = e_net / dt if dt > 0 else None
    return {
        "session_id": f"synth_{eval_dur}_{num_predict}",
        "num_predict": num_predict,
        "cell_id": f"tokens_np{num_predict}__warm_repeat",
        "session_i": 1,
        "order_i": 1,
        "E_net_raw_j": e_net,
        "E_generate_j": e_gen,
        "delta_t_generate_s": dt,
        "eval_duration_s": eval_dur,
        "prompt_eval_duration_s": 0.3,
        "load_duration_s": 0.09,
        "total_duration_s": eval_dur + 0.4,
        "actual_eval_tokens": actual_tokens,
        "tokens_per_s": tps,
        "P_mean_w": P_mean,
        "gpu_temp_settle_c": gpu_temp,
        "gpu_temp_end_c": gpu_temp + 3,
        "P_active_net_w": P_active_net,
        "E_load_j": P_active_net * 0.09 if P_active_net else None,
        "E_prompt_eval_j": P_active_net * 0.3 if P_active_net else None,
        "E_token_eval_j": P_active_net * eval_dur if P_active_net else None,
        "E_phases_sum_j": None,
        "E_residual_j": None,
        "settle_ok": True,
        "CV_P_idle": 0.05,
        "integration_wall_ratio": 1.0,
        "sigma_baseline_subtraction_est_j": sigma,
    }


def _build_duration_separable() -> list[dict]:
    """15 features where eval_duration clearly explains E_net, num_predict does not."""
    feats = []
    # low eval_dur ~2s: 5 actions
    for i in range(5):
        feats.append(
            _feat(eval_dur=2.0 + i * 0.05, actual_tokens=200 + i, e_net=200 + i * 2,
                  e_gen=380 + i, num_predict=256, dt=2.5)
        )
    # mid ~3s: 5 actions
    for i in range(5):
        feats.append(
            _feat(eval_dur=3.0 + i * 0.05, actual_tokens=300 + i, e_net=350 + i * 2,
                  e_gen=550 + i, num_predict=384, dt=3.5)
        )
    # high ~4s: 5 actions
    for i in range(5):
        feats.append(
            _feat(eval_dur=4.0 + i * 0.05, actual_tokens=400 + i, e_net=550 + i * 2,
                  e_gen=750 + i, num_predict=512, dt=4.5)
        )
    return feats


def _build_token_overlap() -> list[dict]:
    """num_predict varies but E_net scatters regardless (matching real result)."""
    feats = []
    for i, np in enumerate([256, 256, 256, 256, 256,
                              384, 384, 384, 384, 384,
                              512, 512, 512, 512, 512]):
        # num_predict 384/512 overlap in E_net
        base = 280 if np == 256 else 490 + (i % 3) * 30
        feats.append(
            _feat(eval_dur=2.5 + i * 0.1, actual_tokens=np - 50 + i,
                  e_net=float(base), e_gen=float(base) * 1.6,
                  num_predict=np, dt=3.0)
        )
    return feats


def main() -> int:
    # Spearman / pearson smoke
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [2.0, 4.0, 6.0, 8.0, 10.0]
    assert _pearson_r2(xs, ys) is not None and abs(_pearson_r2(xs, ys) - 1.0) < 1e-9
    assert _spearman(xs, ys) is not None and abs(_spearman(xs, ys) - 1.0) < 1e-9

    # Tertile bins
    feats = _build_duration_separable()
    bins = _tertile_bins(feats, "eval_duration_s")
    assert bins is not None and len(bins) == 3
    assert len(bins[0]) == 5

    # Insufficient contrast
    flat = [_feat(eval_dur=2.0, actual_tokens=256, e_net=280.0, e_gen=450.0, num_predict=256)
            for _ in range(9)]
    assert _tertile_bins(flat, "eval_duration_s") is None

    # Duration-separable → justified review or promising
    audit_dur = run_audit(feats, candidates=["eval_duration_s", "num_predict"])
    cand_dur = next(c for c in audit_dur["candidate_results"] if c["candidate"] == "eval_duration_s")
    assert cand_dur["classification"] in {
        "single_factor_cost_model_justified_review",
        "promising_factor_needs_validation_run",
    }, cand_dur

    # Token overlap
    feats_tok = _build_token_overlap()
    audit_tok = run_audit(feats_tok, candidates=["num_predict"])
    cand_tok = audit_tok["candidate_results"][0]
    # num_predict alone should not fully separate in overlap scenario
    # (may be promising if low/high bins differ but mid/high don't)
    assert cand_tok["classification"] in {
        "ledger_descriptive_only_no_cost_model",
        "promising_factor_needs_validation_run",
    }, cand_tok

    # Freeze fields
    assert audit_dur["auto_admit"] is False
    assert audit_dur["learning_admission_withheld"] is True
    assert audit_dur["predictor_authorized"] is False

    print("PASS test_rid_electrical_explanatory_audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
