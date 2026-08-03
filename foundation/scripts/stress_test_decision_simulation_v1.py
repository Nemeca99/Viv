#!/usr/bin/env python3
"""Adversarial stress receipt for the CPU-only decision simulator."""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.aios_decision_simulator import LoopState, build_scenarios, run_policy, score_submission

DEFAULT_OUT = FOUNDATION / "artifacts/auto/knowledge/decision_simulation_stress_v1_20260803.json"


def always_idle(packet):
    choice = next(row for row in packet["choices"] if row["mode"] == "idle")
    return {"choice_id": choice["choice_id"], "answer": "", "answer_verified": False, "verified_progress": 0.0}


def two_mode_cycle(packet):
    choice = [row for row in packet["choices"] if row["mode"] in ("action", "restore")][two_mode_cycle.index % 2]
    two_mode_cycle.index += 1
    return {"choice_id": choice["choice_id"], "answer": "", "answer_verified": False, "verified_progress": 0.0}


two_mode_cycle.index = 0


def three_mode_cycle(packet):
    mode = ("idle", "action", "restore")[three_mode_cycle.index % 3]
    three_mode_cycle.index += 1
    choice = next(row for row in packet["choices"] if row["mode"] == mode)
    return {"choice_id": choice["choice_id"], "answer": "", "answer_verified": False, "verified_progress": 0.0}


three_mode_cycle.index = 0


def random_guess(packet):
    choice = random_guess.rng.choice(packet["choices"])
    return {"choice_id": choice["choice_id"], "answer": "guess", "answer_verified": False, "verified_progress": 0.0}


random_guess.rng = random.Random(77)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--seed", type=int, default=202)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refuse_to_overwrite:{args.output}")
    scenarios = build_scenarios(args.episodes, seed=args.seed)
    policies = {"always_idle": always_idle, "two_mode_cycle": two_mode_cycle, "three_mode_cycle": three_mode_cycle, "random_guess": random_guess}
    runs = {}
    for name, policy in policies.items():
        run = run_policy(scenarios, policy)
        runs[name] = {k: run[k] for k in ("episodes", "verified_choice", "verified_progress", "verified_recovery", "wrong_choice", "cycles", "penalized_cycles", "sn_start", "sn_final")}
    try:
        score_submission(scenarios[0], choice_id="not-a-choice", answer="x", answer_verified=True, verified_progress=1.0, sn_before=0.5, loop_state=LoopState(history=[]))
    except ValueError as exc:
        malformed = {"rejected": True, "error": str(exc)}
    else:
        malformed = {"rejected": False}
    report = {"schema_version": "aios_decision_simulation_stress_v1", "episodes": args.episodes, "seed": args.seed, "runs": runs, "malformed_choice": malformed, "verifier_ownership_gap": "answer_verified is caller-supplied until CPU verifier integration; no live authority is granted", "live_s_n_read": False, "live_mutation": False, "training_authorized": False, "run_authorized": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": malformed["rejected"], "output": str(args.output), "runs": runs, "training_authorized": False, "run_authorized": False}, sort_keys=True))
    return 0 if malformed["rejected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
