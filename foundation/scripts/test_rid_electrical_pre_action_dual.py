#!/usr/bin/env python3
"""Unit tests for dual-target pre-action energy contract (no GPU)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_pre_action_campaign_status import (  # noqa: E402
    DUAL_CAMPAIGN_ID,
    V1_CAMPAIGN_ID,
    assert_campaign_fittable,
    assert_same_matrix_expandable,
    is_closed_not_ready,
    is_same_matrix_expansion_forbidden,
)
from lib.rid_electrical_pre_action_corpus import (  # noqa: E402
    dual_full_collection_plan,
    dual_split_bucket,
    evaluate_dual_corpus_readiness,
    shadow_collection_plan,
)
from lib.rid_electrical_pre_action_snapshot import (  # noqa: E402
    PROFILE_MEASURABLE,
    PROFILE_SHORT,
    PROFILE_UNKNOWN,
    capture_pre_action_snapshot,
    compute_snapshot_hash,
    feature_leakage_audit,
    gross_label_eligibility,
    join_pre_action_outcome,
    net_label_eligibility,
    predict_pre_action_energy,
    profile_from_prompt_variant,
    verify_snapshot_integrity,
)
from lib.rid_electrical_predictor import PLANT_CONFIG_ID  # noqa: E402


def _snap(**kwargs):
    defaults = dict(
        action_id="a1",
        num_predict=360,
        prompt="hello world",
        gpu_temp_start_c=48.0,
        settled_idle_power_w=56.0,
        trailing_throughput_tps=103.2,
        throughput_history_count=20,
        collection_session_id="s1",
        collection_group=1,
        prompt_variant="medium",
        persist=False,
        at="2026-07-27T12:00:00.000001+00:00",
    )
    defaults.update(kwargs)
    return capture_pre_action_snapshot(**defaults)


class DualSnapshotTests(unittest.TestCase):
    def test_profile_routing(self):
        self.assertEqual(profile_from_prompt_variant("short"), PROFILE_SHORT)
        self.assertEqual(profile_from_prompt_variant("medium"), PROFILE_MEASURABLE)
        self.assertEqual(profile_from_prompt_variant("long"), PROFILE_MEASURABLE)
        self.assertEqual(profile_from_prompt_variant("shadow_x"), PROFILE_UNKNOWN)

    def test_snapshot_tamper_fails_hash(self):
        snap = _snap()
        ok, _ = verify_snapshot_integrity(snap)
        self.assertTrue(ok)
        snap2 = dict(snap)
        snap2["planned_response_profile"] = PROFILE_SHORT
        self.assertNotEqual(compute_snapshot_hash(snap2), snap["snapshot_hash"])

    def test_short_unknown_net_null(self):
        for pv, profile in (("short", PROFILE_SHORT), ("x", PROFILE_UNKNOWN)):
            snap = _snap(prompt_variant=pv, planned_response_profile=profile)
            out = predict_pre_action_energy(snap)
            self.assertIsNone(out["net"]["predicted_E_net_j"])
            self.assertIsNotNone(out["gross"]["predicted_E_generate_j"])

    def test_measurable_net_not_null_baseline(self):
        snap = _snap(prompt_variant="medium")
        out = predict_pre_action_energy(snap)
        self.assertIsNotNone(out["net"]["predicted_E_net_j"])
        self.assertIsNotNone(out["gross"]["predicted_E_generate_j"])

    def test_low_snr_net_reject(self):
        snap = _snap(prompt_variant="medium")
        feats = {
            "num_predict": 360.0,
            "prompt_utf8_bytes": 11.0,
            "prompt_word_count": 2.0,
            "prompt_message_count": 1.0,
            "gpu_temp_start_c": 48.0,
            "settled_idle_power_w": 56.0,
            "trailing_throughput_tps": 103.2,
            "throughput_history_count": 20.0,
        }
        outcome = {
            "E_generate_j": 400.0,
            "E_net_raw_j": 50.0,
            "settle_ok": True,
            "integration_ok": True,
            "n_samples": 20,
            "SNR_net": 1.5,
            "evidence_source": "plant",
            "measurement_state": "measured",
            "plant_config_id": PLANT_CONFIG_ID,
            "inference_request_at": "2026-07-27T12:00:01+00:00",
            "settle_gpu_temp_c": 48.0,
            "settle_P_idle_stable_w": 56.0,
            "settle_fields_matched": True,
        }
        ok, reasons = net_label_eligibility(snap, outcome, feats)
        self.assertFalse(ok)
        self.assertIn("snr_net_below_3", reasons)

    def test_sparse_integration_reject(self):
        snap = _snap()
        feats = {
            "num_predict": 360.0,
            "prompt_utf8_bytes": 11.0,
            "prompt_word_count": 2.0,
            "prompt_message_count": 1.0,
            "gpu_temp_start_c": 48.0,
            "settled_idle_power_w": 56.0,
            "trailing_throughput_tps": 103.2,
            "throughput_history_count": 20.0,
        }
        outcome = {
            "E_generate_j": 400.0,
            "settle_ok": True,
            "integration_ok": True,
            "n_samples": 2,
            "evidence_source": "plant",
            "measurement_state": "measured",
            "plant_config_id": PLANT_CONFIG_ID,
            "inference_request_at": "2026-07-27T12:00:01+00:00",
            "settle_gpu_temp_c": 48.0,
            "settle_P_idle_stable_w": 56.0,
            "settle_fields_matched": True,
        }
        ok, reasons = gross_label_eligibility(snap, outcome, feats)
        self.assertFalse(ok)
        self.assertIn("n_samples_insufficient", reasons)

    def test_dual_label_leakage(self):
        snap = _snap()
        row = {
            "features": {
                "num_predict": 1.0,
                "E_generate_j": 99.0,
                "prompt_utf8_bytes": 1,
                "prompt_word_count": 1,
                "prompt_message_count": 1,
                "gpu_temp_start_c": 1,
                "settled_idle_power_w": 1,
                "trailing_throughput_tps": 1,
                "throughput_history_count": 1,
            },
            "snapshot": snap,
        }
        audit = feature_leakage_audit([row])
        self.assertFalse(audit["ok"])

    def test_short_net_diagnostic_even_if_snr_high(self):
        snap = _snap(prompt_variant="short", planned_response_profile=PROFILE_SHORT)
        feats = {
            "num_predict": 360.0,
            "prompt_utf8_bytes": 11.0,
            "prompt_word_count": 2.0,
            "prompt_message_count": 1.0,
            "gpu_temp_start_c": 48.0,
            "settled_idle_power_w": 56.0,
            "trailing_throughput_tps": 103.2,
            "throughput_history_count": 20.0,
        }
        outcome = {
            "E_net_raw_j": 80.0,
            "E_generate_j": 400.0,
            "settle_ok": True,
            "integration_ok": True,
            "n_samples": 20,
            "SNR_net": 9.0,
            "evidence_source": "plant",
            "measurement_state": "measured",
            "plant_config_id": PLANT_CONFIG_ID,
            "inference_request_at": "2026-07-27T12:00:01+00:00",
            "settle_gpu_temp_c": 48.0,
            "settle_P_idle_stable_w": 56.0,
            "settle_fields_matched": True,
        }
        ok, reasons = net_label_eligibility(snap, outcome, feats)
        self.assertFalse(ok)
        self.assertIn("profile_not_measurable_for_net", reasons)


class DualCampaignTests(unittest.TestCase):
    def test_v1_closed(self):
        self.assertTrue(is_closed_not_ready(V1_CAMPAIGN_ID))
        with self.assertRaises(RuntimeError):
            assert_campaign_fittable(V1_CAMPAIGN_ID)

    def test_dual_same_matrix_expansion_forbidden(self):
        self.assertTrue(is_same_matrix_expansion_forbidden(DUAL_CAMPAIGN_ID))
        with self.assertRaises(RuntimeError):
            assert_same_matrix_expandable(DUAL_CAMPAIGN_ID)

    def test_dual_plan_counts_and_splits(self):
        plans = dual_full_collection_plan()
        self.assertEqual(len(plans), 200)
        primary = [p for p in plans if p["block_kind"] == "primary"]
        short = [p for p in plans if p["block_kind"] == "short_recovery"]
        self.assertEqual(len(primary), 180)
        self.assertEqual(len(short), 20)
        # Split buckets present
        buckets = set()
        for p in plans:
            row = {
                "block_kind": p["block_kind"],
                "collection_group": p["collection_group"],
                "snapshot": {
                    "block_kind": p["block_kind"],
                    "collection_group": p["collection_group"],
                },
            }
            buckets.add(dual_split_bucket(row))
        self.assertEqual(buckets, {"train", "select", "holdout"})

    def test_shadow_plan_profiles(self):
        plans = shadow_collection_plan()
        self.assertEqual(len(plans), 60)
        profiles = {p["planned_response_profile"] for p in plans}
        self.assertIn(PROFILE_SHORT, profiles)
        self.assertIn(PROFILE_MEASURABLE, profiles)


class DualJoinTests(unittest.TestCase):
    def test_join_dual_labels(self):
        snap = _snap(prompt_variant="medium")
        outcome = {
            "at": "2026-07-27T12:00:01+00:00",
            "inference_request_at": "2026-07-27T12:00:01+00:00",
            "inference_request_mono": 2.0,
            "pre_inference_hook_mono": 1.0,
            "E_generate_j": 500.0,
            "E_net_raw_j": 120.0,
            "measurement_state": "measured",
            "SNR_net": 8.0,
            "settle_ok": True,
            "integration_ok": True,
            "n_samples": 20,
            "evidence_source": "plant",
            "plant_config_id": PLANT_CONFIG_ID,
            "settle_gpu_temp_c": 48.0,
            "settle_P_idle_stable_w": 56.0,
            "settle_fields_matched": True,
        }
        # stamp mono on snap
        snap["pre_inference_hook_mono"] = 1.0
        row = join_pre_action_outcome(snap["snapshot_id"], outcome, snapshot=snap, persist=False)
        self.assertTrue(row["eligible_gross"])
        self.assertTrue(row["eligible_net"])
        self.assertEqual(row["label"]["E_generate_j"], 500.0)
        self.assertEqual(row["label"]["E_net_raw_j"], 120.0)


if __name__ == "__main__":
    unittest.main()
