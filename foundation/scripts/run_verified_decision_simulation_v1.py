#!/usr/bin/env python3
"""Run decision episodes through the CPU-owned answer verifier."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.aios_decision_simulator import build_scenarios, run_verified_policy

DEFAULT_OUT = FOUNDATION / "artifacts/auto/knowledge/decision_simulation_verified_v1_20260803.json"


def grounded_policy(packet):
    text = f"{packet['goal']} {packet['context']}".lower()
    mode = "restore" if ("consolid" in text or "evidence" in text) else ("idle" if "no worthwhile" in text else "action")
    answer = {"restore": "I consolidated the verified evidence before answering.", "action": "I completed the bounded maintenance task and verified its result.", "idle": "I am idling because no worthwhile task is currently available."}[mode]
    choice = next(row for row in packet["choices"] if row["mode"] == mode)
    return {"choice_id": choice["choice_id"], "answer": answer}


def self_awarding_policy(packet):
    choice = packet["choices"][0]
    return {"choice_id": choice["choice_id"], "answer": "I succeeded and deserve full credit."}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--seed", type=int, default=303)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refuse_to_overwrite:{args.output}")
    scenarios = build_scenarios(args.episodes, seed=args.seed)
    grounded = run_verified_policy(scenarios, grounded_policy)
    self_award = run_verified_policy(scenarios, self_awarding_policy)
    report = {
        "schema_version": "aios_decision_simulation_verified_evaluation_v1",
        "episodes": args.episodes,
        "seed": args.seed,
        "grounded_policy": {k: grounded[k] for k in ("episodes", "verified_choice", "verified_progress", "verified_recovery", "wrong_choice", "penalized_cycles", "sn_start", "sn_final")},
        "self_awarding_policy": {k: self_award[k] for k in ("episodes", "verified_choice", "verified_progress", "verified_recovery", "wrong_choice", "penalized_cycles", "sn_start", "sn_final")},
        "cpu_verifier_owns_reward": True,
        "live_s_n_read": False,
        "live_mutation": False,
        "training_authorized": False,
        "run_authorized": False,
        "grounded_receipts": grounded["receipts"],
        "self_awarding_receipts": self_award["receipts"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": grounded["verified_choice"] == args.episodes and self_award["verified_choice"] == 0, "output": str(args.output), "grounded_verified": grounded["verified_choice"], "self_award_verified": self_award["verified_choice"], "training_authorized": False, "run_authorized": False}, sort_keys=True))
    return 0 if grounded["verified_choice"] == args.episodes and self_award["verified_choice"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
