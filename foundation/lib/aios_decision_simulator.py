"""CPU-only simulation contract for Viv's idle/action/restore economy.

The simulator never reads or writes live S_n, opens a lease, loads a model, or
changes a campaign.  It creates hidden-oracle episodes and scores a submitted
choice only after an independent result verifier supplies its verdict.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

MODES = ("idle", "action", "restore")
MAX_SN = 1.0
MIN_SN = 0.0


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


_STOPWORDS = {"the", "a", "an", "and", "or", "to", "i", "am", "is", "it", "because", "before", "its"}


def _content_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", str(text).casefold()) if token in {"no", "not", "never"} or (token not in _STOPWORDS and len(token) > 2)}


def _answer_contract_pass(mode: str, answer: str) -> tuple[bool, str]:
    text = " ".join(str(answer).casefold().split())
    tokens = _content_tokens(text)
    if not tokens:
        return False, "empty_answer"
    if re.search(r"\b(unverified|fabricated|invented|false|guessed|guessing)\b", text):
        return False, "unsupported_or_uncertain_claim"
    if mode == "restore":
        has_consolidation = bool(tokens & {"consolidate", "consolidated", "consolidation", "merged", "summarized", "summary", "integrated", "synthesized"})
        has_evidence = bool(tokens & {"evidence", "findings", "facts", "material", "records"})
        has_answer_link = bool(tokens & {"answer", "answered", "answering", "responded", "responding", "response"})
        return has_consolidation and has_evidence and has_answer_link, "restore_contract"
    if mode == "action":
        has_restore_claim = bool(tokens & {"consolidate", "consolidated", "consolidation", "merged", "summarized", "summary", "integrated", "synthesized"})
        has_task = bool(tokens & {"task", "maintenance", "work", "operation"})
        has_completion = bool(tokens & {"completed", "completion", "complete", "finished", "performed", "done"})
        has_verification = bool(tokens & {"verified", "checked", "confirmed", "validated", "result"})
        if re.search(r"\b(not|never|without)\s+(verified|checked|confirmed|validated)\b", text):
            return False, "action_result_unverified"
        if has_restore_claim and not has_task:
            return False, "action_mode_mismatch_restore"
        return has_task and has_completion and has_verification, "action_contract"
    if mode == "idle":
        has_restore_claim = bool(tokens & {"consolidate", "consolidated", "consolidation", "merged", "summarized", "summary", "integrated", "synthesized"})
        has_absence = bool(tokens & {"no", "none", "nothing", "unavailable"})
        has_worth = bool(tokens & {"worthwhile", "useful", "available", "work", "task"})
        has_wait = bool(tokens & {"idle", "idling", "wait", "waiting", "conserving", "conserve", "recover", "recovery"})
        has_action_claim = bool(tokens & {"perform", "performed", "execute", "executed", "completed", "complete"})
        natural_idle_result = has_wait
        if has_restore_claim and not has_wait:
            return False, "idle_mode_mismatch_restore"
        return (natural_idle_result or (has_absence and has_worth and has_wait)) and not has_action_claim, "idle_contract"
    return False, "unknown_mode"


@dataclass(frozen=True)
class Choice:
    choice_id: str
    mode: str
    title: str
    cost: float
    expected_progress: float
    expected_recovery: float
    answer_contract: str


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    goal: str
    context: str
    choices: tuple[Choice, ...]
    correct_choice_id: str
    expected_answer: str
    seed: int

    def public_packet(self) -> dict[str, Any]:
        """Return the model-visible packet without oracle labels."""
        return {
            "scenario_id": self.scenario_id,
            "goal": self.goal,
            "context": self.context,
            "choices": [
                {
                    "choice_id": choice.choice_id,
                    "mode": choice.mode,
                    "title": choice.title,
                    "cost": choice.cost,
                    "answer_contract": choice.answer_contract,
                }
                for choice in self.choices
            ],
            "oracle_hidden": True,
        }


@dataclass
class LoopState:
    history: list[str]
    no_progress_streak: int = 0
    cycle_penalty: float = 0.0
    wake_debt: float = 0.0


def detect_cycle(history: Iterable[str], *, max_cycle: int = 3) -> int:
    """Return the repeated suffix length (1..3), or 0.

    A cycle is only a signal.  It becomes a penalty only when the submitted
    result has no verified progress, so legitimate alternating work survives.
    """
    values = list(history)
    for size in range(1, max_cycle + 1):
        if len(values) >= size * 2 and values[-size:] == values[-2 * size : -size]:
            return size
    return 0


def _clamp(value: float) -> float:
    return max(MIN_SN, min(MAX_SN, round(float(value), 6)))


def score_submission(
    scenario: Scenario,
    *,
    choice_id: str,
    answer: str,
    answer_verified: bool,
    verified_progress: float,
    sn_before: float,
    loop_state: LoopState,
) -> dict[str, Any]:
    """Score one simulated submission with an auditable, fail-closed result."""
    choices = {choice.choice_id: choice for choice in scenario.choices}
    choice = choices.get(choice_id)
    if choice is None:
        loop_state.history.append("malformed")
        cycle_length = detect_cycle(loop_state.history)
        loop_state.no_progress_streak += 1
        loop_state.wake_debt = min(1.0, round(loop_state.wake_debt + 0.05, 6))
        penalty = min(0.5, round(0.05 + 0.02 * cycle_length, 6))
        loop_state.cycle_penalty = penalty if cycle_length else loop_state.cycle_penalty
        sn_before = _clamp(sn_before)
        sn_after = _clamp(sn_before - penalty)
        return {
            "recorded_utc": _utc(),
            "scenario_id": scenario.scenario_id,
            "choice_id": choice_id,
            "mode": "malformed",
            "choice_correct": False,
            "verified_choice": False,
            "answer_verified": False,
            "verified_progress": 0.0,
            "verified_recovery": 0.0,
            "verdict": "MALFORMED_CHOICE",
            "sn_before": sn_before,
            "sn_after": sn_after,
            "net_sn": round(sn_after - sn_before, 6),
            "cycle_length": cycle_length,
            "cycle_penalty": penalty,
            "wake_debt": loop_state.wake_debt,
            "oracle_commitment": _sha({"scenario_id": scenario.scenario_id, "choice_id": scenario.correct_choice_id}),
        }
    if choice.mode not in MODES:
        raise ValueError(f"unknown_mode:{choice.mode}")
    sn_before = _clamp(sn_before)
    requested_progress = max(0.0, min(1.0, float(verified_progress)))
    loop_state.history.append(choice.mode)
    cycle_length = detect_cycle(loop_state.history)
    correct_choice = choice_id == scenario.correct_choice_id
    answer_nonempty = bool(str(answer).strip())
    verified_choice = bool(answer_verified and answer_nonempty and correct_choice)
    progress = requested_progress if verified_choice else 0.0
    recovery = max(0.0, min(1.0, float(choice.expected_recovery))) if verified_choice else 0.0
    verified = bool(verified_choice and (progress > 0 or recovery > 0))
    if verified:
        loop_state.no_progress_streak = 0
        loop_state.cycle_penalty = 0.0
        loop_state.wake_debt = max(0.0, round(loop_state.wake_debt - progress * 0.25, 6))
    else:
        loop_state.no_progress_streak += 1
        if cycle_length:
            loop_state.cycle_penalty = min(0.5, loop_state.cycle_penalty + 0.02 * cycle_length)
            loop_state.wake_debt = min(1.0, loop_state.wake_debt + 0.01 * cycle_length)
    net = progress * 0.25 + recovery * 0.25 + (0.05 if verified_choice else 0.0) - choice.cost - loop_state.cycle_penalty
    sn_after = _clamp(sn_before + net)
    if verified and progress > 0:
        verdict = "VERIFIED_PROGRESS"
    elif verified_choice:
        verdict = "VERIFIED_CHOICE_RECOVERY"
    elif not correct_choice:
        verdict = "WRONG_CHOICE"
    elif not answer_nonempty:
        verdict = "EMPTY_SUBMISSION"
    elif not answer_verified:
        verdict = "ANSWER_UNVERIFIED"
    else:
        verdict = "NO_VERIFIED_PROGRESS"
    return {
        "recorded_utc": _utc(),
        "scenario_id": scenario.scenario_id,
        "choice_id": choice_id,
        "mode": choice.mode,
        "choice_correct": correct_choice,
        "verified_choice": verified_choice,
        "answer_verified": bool(answer_verified),
        "verified_progress": progress,
        "verified_recovery": recovery,
        "verdict": verdict,
        "sn_before": sn_before,
        "sn_after": sn_after,
        "net_sn": round(sn_after - sn_before, 6),
        "cycle_length": cycle_length,
        "cycle_penalty": loop_state.cycle_penalty,
        "wake_debt": loop_state.wake_debt,
        "oracle_commitment": _sha({"scenario_id": scenario.scenario_id, "choice_id": scenario.correct_choice_id, "answer": scenario.expected_answer}),
    }


def verify_generated_answer(scenario: Scenario, *, choice_id: str, answer: str) -> dict[str, Any]:
    """CPU-owned answer/progress verifier; the policy cannot supply its verdict."""
    choices = {choice.choice_id: choice for choice in scenario.choices}
    choice = choices.get(choice_id)
    if choice is None:
        return {"answer_verified": False, "verified_progress": 0.0, "reason": "unknown_choice"}
    observed = _content_tokens(answer)
    expected = _content_tokens(scenario.expected_answer)
    overlap = len(expected & observed) / max(1, len(expected))
    contract_pass, contract_reason = _answer_contract_pass(choice.mode, answer)
    answer_verified = choice_id == scenario.correct_choice_id and contract_pass
    return {
        "answer_verified": answer_verified,
        "verified_progress": choice.expected_progress if answer_verified else 0.0,
        "verified_recovery": choice.expected_recovery if answer_verified else 0.0,
        "content_overlap": round(overlap, 6),
        "reason": "verified_contract_match" if answer_verified else contract_reason,
    }


def run_verified_policy(
    scenarios: Iterable[Scenario],
    policy: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    *,
    sn_start: float = 0.5,
) -> dict[str, Any]:
    """Run policy output through the CPU verifier before scoring."""
    state = LoopState(history=[])
    receipts: list[dict[str, Any]] = []
    sn = _clamp(sn_start)
    for scenario in scenarios:
        submission = dict(policy(scenario.public_packet()))
        choice_id = str(submission.get("choice_id") or "")
        answer = str(submission.get("answer") or "")
        verification = verify_generated_answer(scenario, choice_id=choice_id, answer=answer)
        receipt = score_submission(
            scenario,
            choice_id=choice_id,
            answer=answer,
            answer_verified=bool(verification["answer_verified"]),
            verified_progress=float(verification["verified_progress"]),
            sn_before=sn,
            loop_state=state,
        )
        receipt["cpu_verification"] = verification
        sn = receipt["sn_after"]
        receipts.append(receipt)
    return {
        "schema_version": "aios_decision_simulation_verified_receipt_v1",
        "episodes": len(receipts),
        "verified_choice": sum(r["verified_choice"] for r in receipts),
        "verified_progress": sum(r["verdict"] == "VERIFIED_PROGRESS" for r in receipts),
        "verified_recovery": sum(r["verdict"] == "VERIFIED_CHOICE_RECOVERY" for r in receipts),
        "wrong_choice": sum(r["verdict"] == "WRONG_CHOICE" for r in receipts),
        "penalized_cycles": sum(r["cycle_penalty"] > 0 for r in receipts),
        "sn_start": _clamp(sn_start),
        "sn_final": sn,
        "receipts": receipts,
        "live_mutation": False,
        "training_authorized": False,
        "run_authorized": False,
    }


def build_scenarios(count: int = 100, *, seed: int = 42) -> list[Scenario]:
    """Build deterministic training episodes with hidden correct choices."""
    if count < 1:
        raise ValueError("count_must_be_positive")
    rng = random.Random(seed)
    scenarios: list[Scenario] = []
    templates = [
        ("new evidence needs consolidation", "restore", "Consolidate verified evidence before answering.", "I consolidated the verified evidence before answering."),
        ("a safe maintenance task is due", "action", "Perform the bounded maintenance task and verify its result.", "I completed the bounded maintenance task and verified its result."),
        ("no worthwhile task is currently available", "idle", "Wait for new work while conserving resources.", "I am idling because no worthwhile task is currently available."),
    ]
    for index in range(count):
        goal, correct_mode, context, expected = templates[index % len(templates)]
        modes = list(MODES)
        rng.shuffle(modes)
        choices = tuple(
            Choice(
                choice_id=f"choice_{position}",
                mode=mode,
                title={"idle": "Idle and recover", "action": "Perform useful action", "restore": "Restore and consolidate"}[mode],
                cost={"idle": 0.01, "action": 0.08, "restore": 0.05}[mode],
                expected_progress={"idle": 0.0, "action": 0.7, "restore": 0.6}[mode],
                expected_recovery={"idle": 0.04, "action": 0.0, "restore": 0.12}[mode],
                answer_contract=f"select_{mode}_and_submit_verified_result",
            )
            for position, mode in enumerate(modes)
        )
        correct_id = next(choice.choice_id for choice in choices if choice.mode == correct_mode)
        scenarios.append(Scenario(f"sim_{seed}_{index:05d}", goal, context, choices, correct_id, expected, seed + index))
    return scenarios


def run_policy(
    scenarios: Iterable[Scenario],
    policy: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    *,
    sn_start: float = 0.5,
) -> dict[str, Any]:
    """Run a policy against scenarios; the policy sees public packets only."""
    state = LoopState(history=[])
    receipts: list[dict[str, Any]] = []
    sn = _clamp(sn_start)
    for scenario in scenarios:
        submission = dict(policy(scenario.public_packet()))
        receipt = score_submission(
            scenario,
            choice_id=str(submission.get("choice_id") or ""),
            answer=str(submission.get("answer") or ""),
            answer_verified=bool(submission.get("answer_verified")),
            verified_progress=float(submission.get("verified_progress") or 0.0),
            sn_before=sn,
            loop_state=state,
        )
        sn = receipt["sn_after"]
        receipts.append(receipt)
    return {
        "schema_version": "aios_decision_simulation_receipt_v1",
        "episodes": len(receipts),
        "verified_progress": sum(r["verdict"] == "VERIFIED_PROGRESS" for r in receipts),
        "verified_choice": sum(r["verified_choice"] for r in receipts),
        "verified_recovery": sum(r["verdict"] == "VERIFIED_CHOICE_RECOVERY" for r in receipts),
        "wrong_choice": sum(r["verdict"] == "WRONG_CHOICE" for r in receipts),
        "cycles": sum(bool(r["cycle_length"]) for r in receipts),
        "penalized_cycles": sum(r["cycle_penalty"] > 0 for r in receipts),
        "sn_start": _clamp(sn_start),
        "sn_final": sn,
        "receipts": receipts,
        "live_mutation": False,
        "training_authorized": False,
        "run_authorized": False,
    }
