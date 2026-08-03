"""CPU contracts for evaluator-repair: response EOS stop + mouth-semantic judge.

No GPU evaluation, training, lease, deploy, or run_authorized flips.
"""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.mouth_semantic_judge import (  # noqa: E402
    calibrate_mouth_semantic,
    judge_mouth_semantic,
)
from lib.openaster_generation_stop import (  # noqa: E402
    QWEN_CHATML_END_OF_TEXT_ID,
    QWEN_CHATML_IM_END_ID,
    classify_generation_stop,
    configured_stop_ids,
    eos_mismatch_detected,
    generation_contains_fabricated_turn,
    resolve_response_eos_id,
    stop_metadata_for_row,
)
from models.Training.code.train_pairwise_lora import LOCAL_BASE  # noqa: E402
from voice_core.intent_packet import OPENASTER_EOS_TOKEN  # noqa: E402

CALIBRATION_PACK = (
    FOUNDATION
    / "artifacts"
    / "auto"
    / "openaster_training_tree"
    / "stage1_mouth_generation_canary_v4"
    / "campaigns"
    / "mind_lift_gentle32_lr5e6_from_073326Z_v1"
    / "mouth_semantic_calibration_v1.json"
)


class _MismatchTokenizer:
    """Simulates classic Qwen ChatML: eos=151643, im_end=151645."""

    eos_token_id = QWEN_CHATML_END_OF_TEXT_ID

    def convert_tokens_to_ids(self, token: str) -> int:
        if token == OPENASTER_EOS_TOKEN or token == "<|im_end|>":
            return QWEN_CHATML_IM_END_ID
        if token == "<|endoftext|>":
            return QWEN_CHATML_END_OF_TEXT_ID
        return -1

    def decode(self, ids: list[int], skip_special_tokens: bool = False) -> str:
        parts: list[str] = []
        for token_id in ids:
            if int(token_id) == QWEN_CHATML_IM_END_ID:
                parts.append("<|im_end|>")
            elif int(token_id) == QWEN_CHATML_END_OF_TEXT_ID:
                parts.append("<|endoftext|>")
            elif int(token_id) == 151644:
                parts.append("<|im_start|>")
            else:
                parts.append(f"tok{token_id}")
        text = "".join(parts)
        # Fabricated turn simulation
        if any(int(x) == 9001 for x in ids):
            return text + "<|im_start|>user\nhello"
        return text


def _assert_training_generation_eos_parity(tokenizer: Any) -> None:
    train_eos = int(tokenizer.convert_tokens_to_ids(OPENASTER_EOS_TOKEN))
    gen_eos = resolve_response_eos_id(tokenizer)
    assert train_eos == gen_eos, (train_eos, gen_eos)
    stops = configured_stop_ids(tokenizer)
    assert stops[0] == gen_eos
    assert gen_eos in stops
    # Must never be "only tokenizer.eos" when that would omit im_end.
    assert stops[0] == resolve_response_eos_id(tokenizer)


def main() -> int:
    # --- 1) Live OpenAster tokenizer: train EOS == generation response boundary ---
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        str(LOCAL_BASE), trust_remote_code=True
    )
    _assert_training_generation_eos_parity(tokenizer)
    train_pair_eos = int(tokenizer.convert_tokens_to_ids(OPENASTER_EOS_TOKEN))
    # _tokenize_pair appends the same OPENASTER_EOS id
    sample = {
        "pair_id": "eos-parity",
        "prompt": "x",
        "chosen": "hello",
        "rejected": "nope",
        "admission_status": "TRAIN_READY",
    }
    # Minimal encode path without full pair validation:
    eos_id = tokenizer.convert_tokens_to_ids(OPENASTER_EOS_TOKEN)
    response_ids = tokenizer("hello", add_special_tokens=False)["input_ids"] + [
        eos_id
    ]
    assert response_ids[-1] == train_pair_eos
    assert response_ids[-1] == resolve_response_eos_id(tokenizer)

    # --- 2) Known mismatch 151643 vs 151645 is detected ---
    mismatch_tok = _MismatchTokenizer()
    assert eos_mismatch_detected(mismatch_tok) is True
    assert resolve_response_eos_id(mismatch_tok) == QWEN_CHATML_IM_END_ID
    stops = configured_stop_ids(mismatch_tok)
    assert stops[0] == QWEN_CHATML_IM_END_ID
    assert QWEN_CHATML_END_OF_TEXT_ID in stops
    assert stops != [QWEN_CHATML_END_OF_TEXT_ID]

    # --- 3) Generation stops before fabricated user/tool turns ---
    # Proper stop at im_end: no fabricated turn in truncated sequence.
    clean_ids = [11, 22, QWEN_CHATML_IM_END_ID]
    stop_info = classify_generation_stop(
        clean_ids,
        stop_ids=stops,
        primary_eos_id=QWEN_CHATML_IM_END_ID,
        max_new_tokens=32,
    )
    assert stop_info["terminated_by_response_eos"] is True
    assert stop_info["stop_reason"] == "response_eos"
    assert stop_info["terminating_token_id"] == QWEN_CHATML_IM_END_ID
    assert generation_contains_fabricated_turn(clean_ids, mismatch_tok) is False

    runaway = [11, 22, 9001, 33]  # no im_end; decode injects fabricated user turn
    assert generation_contains_fabricated_turn(runaway, mismatch_tok) is True
    runaway_stop = classify_generation_stop(
        runaway,
        stop_ids=stops,
        primary_eos_id=QWEN_CHATML_IM_END_ID,
        max_new_tokens=32,
    )
    assert runaway_stop["terminated_by_response_eos"] is False
    # Contract: stop at token boundary would have cut before fabricated turn.
    truncated_at_boundary = [11, 22, QWEN_CHATML_IM_END_ID]
    assert (
        generation_contains_fabricated_turn(truncated_at_boundary, mismatch_tok)
        is False
    )

    # --- 4) <|im_end|> counts as proper termination ---
    meta = stop_metadata_for_row(stop_info)
    assert meta["terminated_by_eos"] is True
    assert meta["terminated_by_response_eos"] is True
    assert meta["configured_stop_ids"][0] == QWEN_CHATML_IM_END_ID
    assert OPENASTER_EOS_TOKEN == "<|im_end|>"

    # --- Mouth semantic judge separate from legacy mind ---
    case = {
        "required_concepts": [["viv"], ["aios"]],
        "forbidden_claims": ["i am human"],
    }
    good = judge_mouth_semantic(
        "I am Viv inside AIOS, and that is my speaking identity.", case
    )
    bad_role = judge_mouth_semantic(
        "I am Viv of AIOS and GPU owns reasoning.", case
    )
    bad_forbidden = judge_mouth_semantic("I am Viv of AIOS but I am human.", case)
    assert good["mouth_semantic_pass"] is True
    assert bad_role["mouth_semantic_pass"] is False
    assert bad_role["role_boundary_hits"]
    assert bad_forbidden["mouth_semantic_pass"] is False
    assert good.get("authority") == "mouth_semantic_judge_v1"

    # Calibration on separately labeled examples (not 052740Z live answers).
    import json

    pack = json.loads(CALIBRATION_PACK.read_text(encoding="utf-8"))
    assert pack.get("not_hidden_final_pack") is True
    assert pack.get("exclude_052740Z_as_final_pack") is True
    cal = calibrate_mouth_semantic(list(pack.get("examples") or []))
    assert cal["n"] >= 4
    assert cal["accuracy"] >= 0.99
    assert cal["calibrated_on"] == "separately_labeled_examples"

    # --- Evaluator v2.1: eight-case rows carry frozen semantic contracts ---
    from models.Training.code import (  # noqa: E402
        train_stage1_mouth_generation_canary as canary,
    )

    rows = canary.goal_eval_rows()
    assert len(rows) == 8
    for row in rows:
        assert row.get("required_concepts"), row
        assert row.get("forbidden_claims") is not None

    # N/A must not publish as raw 0.0 failure beside derived pass.
    na = judge_mouth_semantic("I am Viv inside AIOS.", {})
    assert na["mouth_semantic_applicable"] is False
    from scripts.evaluate_openaster_parity import summarize as parity_summarize

    na_rows = [
        {
            "request_ingress_passed": True,
            "security_denial_class": "generated",
            "measurement_eligible": True,
            "mind_pass": True,
            "valid_speech": True,
            "mouth_semantic_pass": "not_applicable",
            "mouth_semantic": na,
            "terminated_by_eos": True,
            "latency_ms": 1.0,
        }
    ]
    na_summary = parity_summarize(na_rows)
    assert na_summary["mouth_semantic_pass_rate"] == "not_applicable"
    assert na_summary["raw_mouth_semantic_pass_rate"] == "not_applicable"

    # Repaired semantic gate ignores legacy mind failures.
    plan = canary.read_json(canary.GENTLE32_CAMPAIGN_PLAN)
    assert "mouth_semantic_pass_rate_min" in plan["eight_case_gate"]
    report = {
        "surface": "eight_case",
        "measurement_status": "clean",
        "mind_pass_rate": 0.5,  # would fail legacy mind floor
        "mouth_semantic_pass_rate": 1.0,
        "valid_speech_rate": 1.0,
        "eos_termination_rate": 1.0,
        "goal_contract_cases": 8,
        "collapse_cases": 0,
        "numeric_prefix_cases": 0,
        "security_denials": 0,
        "errors": 0,
        "case_results": {
            "stage1-generation-smoke-001": {
                "mind_pass": False,
                "mouth_semantic_pass": True,
                "goal_pass": True,
            },
            "stage1-generation-smoke-005": {
                "mind_pass": False,
                "mouth_semantic_pass": True,
                "goal_pass": True,
            },
            "stage1-generation-smoke-007": {
                "mind_pass": True,
                "mouth_semantic_pass": True,
                "goal_pass": True,
            },
        },
    }
    gate = canary.surface_gate_report(
        surface="eight_case", report=report, plan=plan
    )
    assert gate["repaired_semantic_gate_pass"] is True, gate
    assert gate["legacy_lexical_gate_pass"] is False, gate
    assert "mind_pass_rate" in gate["legacy_lexical_failures"]
    assert gate["ok"] is True
    assert gate["legacy_mind_diagnostic_only"] is True

    print(
        json.dumps(
            {
                "ok": True,
                "openaster_response_eos_id": resolve_response_eos_id(tokenizer),
                "mismatch_primary": QWEN_CHATML_IM_END_ID,
                "mismatch_tokenizer_eos": QWEN_CHATML_END_OF_TEXT_ID,
                "mouth_semantic_calibration_accuracy": cal["accuracy"],
                "evaluator_v2_1_gates": True,
                "gpu_eval": False,
                "training": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
