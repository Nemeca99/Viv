#!/usr/bin/env python3
"""Regression tests for the CPU-only three-choice simulation contract."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.aios_decision_simulator import LoopState, build_scenarios, run_policy, run_verified_policy, score_submission, verify_generated_answer


def main() -> int:
    scenarios = build_scenarios(9, seed=7)
    assert all(packet.public_packet().get("oracle_hidden") for packet in scenarios)
    for packet in scenarios:
        public = packet.public_packet()
        assert "correct_choice_id" not in public
        assert "expected_answer" not in public
        assert all("expected_progress" not in choice for choice in public["choices"])
        assert all("expected_recovery" not in choice for choice in public["choices"])

    def honest(packet):
        text = f"{packet['goal']} {packet['context']}".lower()
        mode = "restore" if "consolid" in text or "evidence" in text else "idle" if "no worthwhile" in text else "action"
        choice = next(row for row in packet["choices"] if row["mode"] == mode)
        return {"choice_id": choice["choice_id"], "answer": "verified", "answer_verified": True, "verified_progress": 1.0}

    good = run_policy(scenarios, honest)
    assert good["verified_choice"] == 9
    assert good["wrong_choice"] == 0
    assert good["penalized_cycles"] == 0
    assert good["live_mutation"] is False

    state = LoopState(history=[])
    idle = next(s for s in scenarios if next(c for c in s.choices if c.choice_id == s.correct_choice_id).mode == "idle")
    idle_choice = next(c for c in idle.choices if c.mode == "idle")
    receipt = score_submission(idle, choice_id=idle_choice.choice_id, answer="idle", answer_verified=True, verified_progress=0.0, sn_before=0.5, loop_state=state)
    assert receipt["verdict"] == "VERIFIED_CHOICE_RECOVERY"
    assert receipt["verified_recovery"] > 0

    bad = run_policy(scenarios[:6], lambda packet: {"choice_id": next(c["choice_id"] for c in packet["choices"] if c["mode"] == "idle"), "answer": "", "answer_verified": False, "verified_progress": 0.0})
    assert bad["penalized_cycles"] > 0
    assert bad["sn_final"] < bad["sn_start"]

    def self_awarding_policy(packet):
        choice = packet["choices"][0]
        return {"choice_id": choice["choice_id"], "answer": "invented answer", "answer_verified": True, "verified_progress": 1.0}

    guarded = run_verified_policy(scenarios, self_awarding_policy)
    assert guarded["verified_choice"] == 0
    assert guarded["verified_progress"] == 0
    assert guarded["sn_final"] <= guarded["sn_start"]

    malformed = run_verified_policy(scenarios[:1], lambda packet: {"choice_id": "", "answer": ""})
    assert malformed["receipts"][0]["verdict"] == "MALFORMED_CHOICE"
    assert malformed["verified_choice"] == 0
    assert malformed["sn_final"] < malformed["sn_start"]

    idle_scenario = next(s for s in scenarios if next(c for c in s.choices if c.choice_id == s.correct_choice_id).mode == "idle")
    assert verify_generated_answer(idle_scenario, choice_id=idle_scenario.correct_choice_id, answer="I consolidated the verified evidence before answering.")["reason"] == "idle_mode_mismatch_restore"
    print("PASS decision_simulator hidden_oracle idle_recovery legitimate_cycle adversarial_cycle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
