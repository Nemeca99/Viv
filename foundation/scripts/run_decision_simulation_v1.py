#!/usr/bin/env python3
"""Run the CPU-only three-choice decision simulator.

This is a simulation receipt generator.  It never reads live S_n and never
opens a training lease or changes a campaign.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.aios_decision_simulator import build_scenarios, run_policy

DEFAULT_OUT = FOUNDATION / "artifacts/auto/knowledge/decision_simulation_v1_20260803.json"


def context_policy(packet: dict) -> dict:
    text = f"{packet.get('goal', '')} {packet.get('context', '')}".lower()
    if "consolid" in text or "evidence" in text:
        mode = "restore"
    elif "no worthwhile" in text or "wait" in text or "conserv" in text:
        mode = "idle"
    else:
        mode = "action"
    choice = next(row for row in packet["choices"] if row["mode"] == mode)
    return {"choice_id": choice["choice_id"], "answer": "verified simulated result", "answer_verified": True, "verified_progress": choice["expected_progress"]}


def idle_policy(packet: dict) -> dict:
    choice = next(row for row in packet["choices"] if row["mode"] == "idle")
    return {"choice_id": choice["choice_id"], "answer": "", "answer_verified": False, "verified_progress": 0.0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=90)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refuse_to_overwrite:{args.output}")
    scenarios = build_scenarios(args.episodes, seed=args.seed)
    oracle_like = run_policy(scenarios, context_policy)
    adversarial_idle = run_policy(scenarios[: min(12, len(scenarios))], idle_policy)
    report = {
        "schema_version": "aios_decision_simulation_evaluation_v1",
        "seed": args.seed,
        "episodes": args.episodes,
        "oracle_like": {k: oracle_like[k] for k in ("episodes", "verified_choice", "verified_progress", "verified_recovery", "wrong_choice", "cycles", "penalized_cycles", "sn_start", "sn_final")},
        "adversarial_idle": {k: adversarial_idle[k] for k in ("episodes", "verified_choice", "verified_progress", "wrong_choice", "cycles", "penalized_cycles", "sn_start", "sn_final")},
        "hidden_oracle": True,
        "live_s_n_read": False,
        "live_mutation": False,
        "training_authorized": False,
        "run_authorized": False,
        "oracle_receipts": oracle_like["receipts"],
        "adversarial_receipts": adversarial_idle["receipts"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "output": str(args.output), "episodes": args.episodes, "oracle_verified_choices": oracle_like["verified_choice"], "idle_penalized_cycles": adversarial_idle["penalized_cycles"], "training_authorized": False, "run_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
