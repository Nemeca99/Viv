#!/usr/bin/env python3
"""Unit tests for pre-action corpus, baseline, train, shadow."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_pre_action_baseline import (  # noqa: E402
    baseline_predict_E_net,
    trailing_throughput_tps,
)
from lib.rid_electrical_pre_action_corpus import (  # noqa: E402
    collection_plan,
    evaluate_corpus_readiness,
    freeze_corpus,
    synthesize_ready_corpus,
    synthesize_signal_corpus_for_admission,
)
from lib.rid_electrical_pre_action_shadow import (  # noqa: E402
    commit_prediction,
    run_synthetic_shadow_campaign,
    shadow_step,
)
from lib.rid_electrical_pre_action_snapshot import capture_pre_action_snapshot  # noqa: E402
from lib.rid_electrical_pre_action_train import run_offline_training  # noqa: E402
from lib.rid_electrical_predictor import PLANT_CONFIG_ID  # noqa: E402
from lib.rid_electrical_pre_action_snapshot import MODEL_ID  # noqa: E402


def main() -> int:
    plan = collection_plan()
    assert len(plan) == 120
    assert plan[0]["collection_group"] == 1

    # Throughput past-only
    hist = [
        {
            "plant_config_id": PLANT_CONFIG_ID,
            "model": MODEL_ID,
            "residency": "warm_repeat",
            "tokens_per_s": 100.0 + i,
        }
        for i in range(10)
    ]
    tps, n = trailing_throughput_tps(
        hist, plant_config_id=PLANT_CONFIG_ID, model=MODEL_ID, as_of_index=5
    )
    assert n == 5 and tps is not None
    # insufficient
    tps2, n2 = trailing_throughput_tps(
        hist[:3], plant_config_id=PLANT_CONFIG_ID, model=MODEL_ID
    )
    assert tps2 is None and n2 == 3

    b = baseline_predict_E_net(
        num_predict=360, trailing_throughput_tps=103.0, throughput_history_count=20
    )
    assert b["predicted_E_net_j"] is not None and b["in_domain"] is True
    b2 = baseline_predict_E_net(
        num_predict=360, trailing_throughput_tps=103.0, throughput_history_count=2
    )
    assert b2["predicted_E_net_j"] is None
    assert b2["confidence"] == "insufficient_throughput_history"
    b3 = baseline_predict_E_net(
        num_predict=1000, trailing_throughput_tps=50.0, throughput_history_count=20
    )
    assert b3["confidence"] == "out_of_validated_domain"

    rows = synthesize_ready_corpus()
    ready = evaluate_corpus_readiness(rows)
    assert ready["ok"] is True, ready["gates"]
    freeze = freeze_corpus(rows, write=True)
    assert freeze["ok"] is True

    train = run_offline_training(rows, write=False)
    assert train.get("ok") is True
    assert train.get("status") in {
        "pre_action_offline_candidate_for_shadow",
        "training_not_justified",
    }

    # Positive path: extra temp signal should justify training vs throughput baseline
    signal_rows = synthesize_signal_corpus_for_admission()
    freeze_corpus(
        signal_rows,
        write=True,
        out_dir=None,
        evidence_source="synthetic_harness_only",
        campaign_id="synthetic_harness",
    )
    train_pos = run_offline_training(signal_rows, write=False)
    assert train_pos.get("ok") is True
    assert train_pos.get("status") == "pre_action_offline_candidate_for_shadow", train_pos.get(
        "admission"
    )

    # Shadow protocol: commit before execute
    snap = capture_pre_action_snapshot(
        action_id="shadow_proto",
        num_predict=360,
        prompt="short",
        gpu_temp_start_c=50.0,
        settled_idle_power_w=55.0,
        trailing_throughput_tps=103.0,
        throughput_history_count=20,
        collection_session_id="s",
        persist=False,
    )
    flag = {"ran": False}

    def _exec():
        flag["ran"] = True
        return {"E_net_raw_j": 400.0, "eligible": True}

    commit = commit_prediction(snap)
    assert flag["ran"] is False
    assert commit["gates_action"] is False
    rec = shadow_step(snapshot=snap, execute_fn=_exec, persist_log=False)
    assert flag["ran"] is True
    assert rec["commit"]["prediction_committed_before_execution"] is True

    shadow = run_synthetic_shadow_campaign(n_actions=60, write=True)
    assert shadow.get("protocol_checks", {}).get("all_commits_before_execute") is True
    # Plant candidate required for shadow validation status; harness proves protocol only.

    print(
        json.dumps(
            {
                "ok": True,
                "corpus_ready": ready["ok"],
                "train_status": train.get("status"),
                "train_pos_status": train_pos.get("status"),
                "shadow_protocol_ok": shadow.get("protocol_checks", {}).get(
                    "all_commits_before_execute"
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
