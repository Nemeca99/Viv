#!/usr/bin/env python3
"""Unit tests for Action Contract + workload-first predict (no GPU)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_pre_action_action_contract import (  # noqa: E402
    TOKEN_BANDS,
    TASK_TYPES,
    action_contract_collection_plan,
    build_action_contract,
    compute_action_contract_hash,
    predict_action_contract_energy,
    verify_action_contract_integrity,
    write_action_contract_lock,
)
from lib.rid_electrical_pre_action_campaign_status import (  # noqa: E402
    ACTION_CONTRACT_CAMPAIGN_ID,
    DUAL_CAMPAIGN_ID,
    is_same_matrix_expansion_forbidden,
)
from lib.rid_electrical_pre_action_snapshot import (  # noqa: E402
    FORBIDDEN_FEATURE_KEYS,
    PROFILE_SHORT,
    capture_pre_action_snapshot,
    verify_snapshot_integrity,
)


class ActionContractTests(unittest.TestCase):
    def test_contract_hash_integrity(self):
        c = build_action_contract(
            task_type="explanation",
            token_band="standard",
            action_id="ac_test_1",
        )
        ok, reason = verify_action_contract_integrity(c)
        self.assertTrue(ok, reason)
        c2 = dict(c)
        c2["planned_eval_token_target"] = 999
        self.assertNotEqual(compute_action_contract_hash(c2), c["contract_hash"])

    def test_collection_plan_grid(self):
        plans = action_contract_collection_plan()
        self.assertEqual(len(plans), 8 * len(TASK_TYPES) * len(TOKEN_BANDS))
        self.assertEqual(len(plans), 72)
        self.assertTrue(all("action_contract" in p for p in plans))
        hashes = {p["action_contract"]["contract_hash"] for p in plans}
        self.assertEqual(len(hashes), 72)

    def test_snapshot_embeds_contract_hash(self):
        c = build_action_contract(
            task_type="summary",
            token_band="brief",
            action_id="ac_snap_1",
        )
        snap = capture_pre_action_snapshot(
            action_id="ac_snap_1",
            num_predict=c["num_predict"],
            prompt=c["prompt"],
            gpu_temp_start_c=48.0,
            settled_idle_power_w=56.0,
            trailing_throughput_tps=100.0,
            throughput_history_count=20,
            collection_session_id="s",
            collection_group=1,
            prompt_variant="summary_brief",
            planned_response_profile=PROFILE_SHORT,
            persist=False,
            action_contract=c,
            at="2026-07-28T00:00:00.000001+00:00",
        )
        ok, reason = verify_snapshot_integrity(snap)
        self.assertTrue(ok, reason)
        self.assertEqual(snap["action_contract_hash"], c["contract_hash"])

    def test_workload_first_api_ranges_and_net_null(self):
        c = build_action_contract(
            task_type="enumeration",
            token_band="brief",
            action_id="ac_pred_1",
        )
        snap = capture_pre_action_snapshot(
            action_id="ac_pred_1",
            num_predict=c["num_predict"],
            prompt=c["prompt"],
            gpu_temp_start_c=48.0,
            settled_idle_power_w=56.0,
            trailing_throughput_tps=100.0,
            throughput_history_count=20,
            collection_session_id="s",
            collection_group=1,
            prompt_variant="enumeration_brief",
            planned_response_profile=PROFILE_SHORT,
            persist=False,
            action_contract=c,
            at="2026-07-28T00:00:00.000002+00:00",
        )
        out = predict_action_contract_energy(c, snap)
        self.assertTrue(out["ok"])
        self.assertIsNotNone(out["demand"]["t50_s"])
        self.assertIsNotNone(out["demand"]["t90_s"])
        self.assertIsNotNone(out["gross"]["E50_j"])
        self.assertIsNotNone(out["gross"]["E90_j"])
        self.assertIsNone(out["net"]["E50_j"])
        self.assertIn("probably cost", out["operator_phrasing"] or "")
        for fk in ("eval_duration_s", "actual_eval_tokens", "done_reason"):
            self.assertIn(fk, FORBIDDEN_FEATURE_KEYS)

    def test_lock_and_dual_refuse(self):
        lock = write_action_contract_lock()
        self.assertEqual(lock["campaign_id"], ACTION_CONTRACT_CAMPAIGN_ID)
        self.assertTrue(lock["never_merge_dual_or_v1_rows"])
        self.assertTrue(is_same_matrix_expansion_forbidden(DUAL_CAMPAIGN_ID))


if __name__ == "__main__":
    unittest.main()
