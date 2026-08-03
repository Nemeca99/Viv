#!/usr/bin/env python3
"""Unit tests for production accounting operations (no plant run)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_accounting_ops import (  # noqa: E402
    evaluate_ops_bootstrap_gates,
    scan_config_mismatch,
)
from lib.rid_electrical_accounting_registry_release import (  # noqa: E402
    RELEASE_ID,
    assert_release_intact,
)
from lib.rid_electrical_energy_ledger import append_action_row, load_actions  # noqa: E402
from lib.rid_electrical_ops_hook import (  # noqa: E402
    maybe_record_from_speak_result,
    record_ordinary_gpu_action,
    timings_from_ollama_raw,
)
from lib.rid_electrical_policy import policy_stamp  # noqa: E402
from lib.rid_electrical_predictor import PLANT_CONFIG_ID  # noqa: E402
import lib.rid_electrical_policy as _policy  # noqa: E402


def main() -> int:
    stamp = policy_stamp()
    assert stamp["master_weight_enabled"] is False
    assert stamp["advisory_routing_enabled"] is False
    assert stamp["admission_granted"] is False
    assert stamp.get("auto_admit") is not True

    # Timings from Ollama ns
    t = timings_from_ollama_raw(
        {
            "eval_duration": 3_500_000_000,
            "prompt_eval_duration": 200_000_000,
            "eval_count": 360,
        }
    )
    assert abs(float(t["eval_duration_s"]) - 3.5) < 1e-9
    assert abs(float(t["prompt_eval_duration_s"]) - 0.2) < 1e-9

    # Hook never raises; timing-only persists registry fields
    with tempfile.TemporaryDirectory() as td:
        # Patch append path by calling account path with append_ledger via tmp ledger
        from lib import rid_electrical_energy_ledger as ledger_mod

        tmp = Path(td) / "actions.jsonl"
        orig = ledger_mod.ACTIONS_JSONL
        ledger_mod.ACTIONS_JSONL = tmp
        try:
            # Force exception path still soft
            bad = maybe_record_from_speak_result({"ok": False})
            assert bad.get("accounted") is False
            assert bad.get("gates_action") is not True

            silent = maybe_record_from_speak_result({"ok": True, "silent": True})
            assert silent.get("accounted") is False

            out = record_ordinary_gpu_action(
                model="viv-voice-qwen",
                raw={
                    "eval_duration": 3_500_000_000,
                    "prompt_eval_duration": 100_000_000,
                    "eval_count": 360,
                },
                action_type="viv_speak_generate",
                session_id="test_ops_session",
                plant_config_id=PLANT_CONFIG_ID,
                append_ledger=True,
                refresh_drift=False,
            )
            assert out.get("gates_action") is False
            assert out.get("operational_authority") is False
            assert out.get("measurement_state") == "timing_only"
            rows = load_actions(tmp)
            assert len(rows) >= 1
            r = rows[-1]
            assert r.get("measurement_state") == "timing_only"
            assert r.get("action_type") == "viv_speak_generate"
            assert r.get("plant_config_id") == PLANT_CONFIG_ID
            assert r.get("gates_action") is False
        finally:
            ledger_mod.ACTIONS_JSONL = orig

    # Config mismatch burst → review signal (fail closed for review flag)
    mm_rows = [
        {
            "selection_reason": "config_mismatch",
            "confidence": "config_mismatch",
            "predicted_E_j": None,
        }
        for _ in range(3)
    ] + [{"selection_reason": "warm_eval_only_v1_specialty", "registry_selected_predictor": "V1"}]
    mm = scan_config_mismatch(mm_rows, window=50)
    assert mm["burst"] is True
    assert mm["config_mismatch_count"] >= 3
    assert mm["authority"]["auto_admit"] is False

    # Release hashes intact
    intact = assert_release_intact()
    assert intact.get("ok") is True, intact

    # Bootstrap gates structure (may pass after monitor run)
    boot = evaluate_ops_bootstrap_gates()
    assert "gates" in boot
    assert "registry_release_and_health" in boot["gates"]
    assert "authority_closed" in boot["gates"]
    assert boot["gates"]["authority_closed"]["pass"] is True

    # Speak result helper soft-fail
    soft = maybe_record_from_speak_result(None)  # type: ignore[arg-type]
    assert soft.get("gates_action") is not True

    print(json.dumps({"ok": True, "tests": "pass", "release_id": RELEASE_ID}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
