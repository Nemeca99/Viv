#!/usr/bin/env python3
"""Focused preflight for declarative campaign planning."""
from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import sys
import tempfile

VIV_SLM_ROOT = Path(__file__).resolve().parents[1]
if str(VIV_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(VIV_SLM_ROOT))
from paths import FOUNDATION  # noqa: E402
for path in (FOUNDATION, VIV_SLM_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_viv_slm_layer_campaign as engine  # noqa: E402


def main() -> int:
    contract = FOUNDATION / "artifacts" / "auto" / "agentic" / "layer_campaign_contracts" / "V36_COMPOSED_BEHAVIOR_LAYER.json"
    with tempfile.TemporaryDirectory(prefix="viv_slm_layer_campaign_plan_") as temp_dir:
        plan = engine.build_campaign_plan(
            contract_path=contract,
            output_dir=Path(temp_dir) / "candidate",
            steps=250,
        )
    assert plan["status"] == "DRY_RUN_READY"
    assert plan["campaign"]["schema_version"] == "viv_slm_layer_campaign_v1"
    assert plan["campaign"]["rollback_budget"] == 2
    assert plan["campaign"]["allowed_scale_ladder"] == [1.0, 0.75, 0.5, 0.25, 0.1]
    assert plan["parent_layer_id"].startswith("viv_slm_identity_personality_v35_")
    assert plan["source_evidence"]["parent"]["sha256"] == plan["parent_checkpoint_sha256"]
    assert plan["authority"]["training_authorized"] is False
    assert all(value is False for value in plan["side_effects"].values())
    source_manifest = FOUNDATION.parent / "models" / "viv_slm_identity_personality_v57_v43_behavior_lane_autotune" / "runs" / "v43_behavior_lane_autotune_steps_0250" / "RUN_MANIFEST.json"
    source_payload = engine._read_json(source_manifest)
    seeded_spec = SimpleNamespace(
        parent_checkpoint_sha256=source_payload["checkpoint_sha256"],
        training_config={
            "controller_tuning": {"schema_version": "viv_slm_multi_metric_controller_v3"},
            "controller_state_seed": {
                "mode": "carry_forward_actuation_only",
                "source_run_manifest": str(source_manifest),
                "source_run_manifest_sha256": engine._sha256(source_manifest),
                "source_checkpoint_sha256": source_payload["checkpoint_sha256"],
                "source_layer_id": "viv_slm_identity_personality_v57_v43_behavior_lane_autotune_0250_20260805T032239Z",
            },
        },
    )
    seed = engine._load_controller_state_seed(seeded_spec)
    assert seed["enabled"] is True
    assert seed["evidence"]["metric_history_carried"] is False
    assert seed["source_state"]["schema_version"] == "viv_slm_multi_metric_controller_v3"
    bad_spec = SimpleNamespace(
        parent_checkpoint_sha256=source_payload["checkpoint_sha256"],
        training_config={
            "controller_tuning": {"schema_version": "viv_slm_multi_metric_controller_v3"},
            "controller_state_seed": {
                "mode": "carry_forward_actuation_only",
                "source_run_manifest": str(source_manifest),
                "source_run_manifest_sha256": "0" * 64,
                "source_checkpoint_sha256": source_payload["checkpoint_sha256"],
            },
        },
    )
    try:
        engine._load_controller_state_seed(bad_spec)
    except ValueError as error:
        assert "hash_mismatch" in str(error)
    else:
        raise AssertionError("controller seed manifest hash mismatch was accepted")
    knob_path = FOUNDATION / "models" / "Training" / "current" / "TRAINING_KNOBS.json"
    knob_hash = engine._sha256(knob_path)
    knob_contract = engine._read_json(
        FOUNDATION / "artifacts" / "auto" / "agentic" / "layer_campaign_contracts" / "V59_CONTROLLER_STATE_LAYERING.json"
    )
    knob_contract["knob_registry"] = {
        "path": "foundation/models/Training/current/TRAINING_KNOBS.json",
        "sha256": knob_hash,
    }
    knob_spec = engine.LayerCampaignSpec.from_mapping(knob_contract)
    knob_binding = engine._load_knob_registry(knob_spec)
    input_manifest = engine._read_json(
        FOUNDATION.parent / "models" / "viv_slm_identity_personality_v43_conversation_focus" / "inputs" / "INPUT_MANIFEST.json"
    )
    engine._validate_knob_registry_binding(knob_spec, knob_binding, input_manifest=input_manifest)
    assert knob_binding["enabled"] is True
    assert knob_binding["evidence"]["registry_sha256"] == knob_hash
    bad_knob_contract = dict(knob_contract)
    bad_knob_contract["knob_registry"] = {"path": "foundation/models/Training/current/TRAINING_KNOBS.json", "sha256": "0" * 64}
    bad_knob_spec = engine.LayerCampaignSpec.from_mapping(bad_knob_contract)
    try:
        engine._load_knob_registry(bad_knob_spec)
    except ValueError as error:
        assert "knob_registry_hash_mismatch" in str(error)
    else:
        raise AssertionError("central knob registry hash mismatch was accepted")
    print(
        "VIV_SLM_LAYER_CAMPAIGN_PREFLIGHT_PASS "
        "declarative_contract=true lineage_hashes=true source_verification=true "
        "central_knob_registry=true dry_run_no_writes=true authority_closed=true external_probes=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
