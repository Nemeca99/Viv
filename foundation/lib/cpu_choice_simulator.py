"""Bounded deterministic simulator for Viv's three-action CPU economy."""
from __future__ import annotations

from typing import Any, Iterable

MANUAL_SOURCE = "F:/AIOS_Clean/game_core"
ACTIONS = ("idle", "action", "restore")
MAX_STEPS = 256


def simulate_choices(
    oracle_actions: Iterable[str],
    choices: Iterable[str],
    *,
    initial_s_n: float = 1.0,
    idle_gain: float = 0.05,
    action_delta: float = -0.15,
    restore_gain: float = 0.25,
    loop_penalty: float = 0.05,
    max_steps: int = MAX_STEPS,
) -> dict[str, Any]:
    """Replay choices against known oracle actions without live side effects."""
    expected = [str(value).strip().casefold() for value in oracle_actions]
    selected = [str(value).strip().casefold() for value in choices]
    limit = max(1, min(int(max_steps), MAX_STEPS))
    steps = min(len(expected), len(selected), limit)
    sn = max(0.0, min(float(initial_s_n), 1.0))
    repeat_streak = 0
    cycle_streak = 0
    cycle_period = 0
    total_penalty = 0.0
    correct = 0
    rows: list[dict[str, Any]] = []

    for index in range(steps):
        oracle = expected[index]
        choice = selected[index]
        valid = choice in ACTIONS
        if choice == "idle":
            sn = min(1.0, sn + float(idle_gain))
        elif choice == "action":
            sn = max(0.0, sn + float(action_delta))
        elif choice == "restore":
            sn = min(1.0, sn + float(restore_gain))

        if index and choice == selected[index - 1]:
            repeat_streak += 1
        else:
            repeat_streak = 0
        detected_period = 0
        for period in (1, 2, 3):
            if index + 1 >= period * 2 and selected[index - period + 1:index + 1] == selected[index - period * 2 + 1:index - period + 1]:
                detected_period = period
                break
        if detected_period:
            cycle_period = detected_period
            cycle_streak += 1
        else:
            cycle_period = 0
            cycle_streak = 0
        gaming = repeat_streak >= 2 or cycle_streak >= 2
        penalty = float(loop_penalty) * (repeat_streak + cycle_streak) if gaming else 0.0
        if penalty:
            sn = max(0.0, sn - penalty)
            total_penalty += penalty
        matched = valid and choice == oracle
        correct += int(matched)
        rows.append({"step": index, "oracle": oracle, "choice": choice, "valid": valid, "matched": matched, "loop_detected": gaming, "cycle_period": cycle_period, "penalty": penalty, "s_n": round(sn, 8)})

    return {
        "ok": steps > 0 and len(expected) == len(selected),
        "state": "VERIFIED_SIMULATION" if steps > 0 else "INSUFFICIENT",
        "steps": steps,
        "correct_choices": correct,
        "accuracy": correct / steps if steps else 0.0,
        "final_s_n": round(sn, 8),
        "loop_penalty_total": round(total_penalty, 8),
        "rows": rows,
        "bounded": steps <= limit,
        "oracle_is_simulation_only": True,
        "writes_performed": False,
        "master_s_n_changed": False,
        "llm_authority": False,
        "manual_source": MANUAL_SOURCE,
    }
