"""CPU regression suite for OpenAster train/runtime parity contracts."""
from __future__ import annotations

import json
from pathlib import Path

from tokenizers import Tokenizer

from lib.aifl_holdout_split import load_ban_sets
from lib.aifl_parity_contracts import SCHEMA_VERSION, validate_training_example
from lib.semantic_choice import ExpressionCandidate, rank_equivalents
from lib.security_membrane import egress_gate
from lib.viv_shadow_judge import score_draft
from voice_core.intent_packet import OPENASTER_EOS_TOKEN, looks_like_speech, render_openaster_training_text
from voice_core.client import speak_completion
from scripts.build_openaster_curriculum_v2 import gpu_exclusive
from scripts.evaluate_openaster_parity import (
    OpenAsterBackend,
    PARITY_EVAL_MODEL_ROLE,
    QwenBackend,
    security_denial_class,
    summarize,
    wait_for_evaluable_master,
)

FOUNDATION = Path(__file__).resolve().parents[1]


def main() -> int:
    assert QwenBackend.model_role == OpenAsterBackend.model_role == PARITY_EVAL_MODEL_ROLE
    assert PARITY_EVAL_MODEL_ROLE == "parity_mouth_eval"

    dormant_record = {
        "allowed": False,
        "reason": "security_ingress_denied",
        "rule": "triad",
        "master_rid": {"master_s_n": 0.01, "status": "DORMANT"},
        "membrane": {"reason": "[LAW 5] Forced dormancy."},
    }
    content_record = {
        "allowed": False,
        "reason": "content denied",
        "rule": "content",
        "master_rid": {"master_s_n": 0.60, "status": "ACTIVE"},
    }
    assert security_denial_class(dormant_record) == "security_dormancy_denied"
    assert security_denial_class(content_record) == "security_content_denied"
    # D: response-shaped Law-5 DENY must classify as dormancy (not "generated").
    response_dormant = {
        "allowed": False,
        "reason": "security_ingress_denied",
        "rule": "triad",
        "master_rid": {"master_s_n": 0.3386, "status": "DORMANT"},
        "membrane": {
            "reason": "[LAW 5] Forced dormancy (S_n=0.3386 < 0.3700). Fail-closed.",
        },
    }
    assert security_denial_class(response_dormant) == "security_dormancy_denied"
    summary = summarize([
        {
            "request_ingress_passed": True,
            "security_denial_class": "generated",
            "mind_pass": True,
            "valid_speech": True,
            "repetition_collapse": False,
            "numeric_prefix": False,
            "terminated_by_eos": True,
            "model_tokens": 4,
            "latency_ms": 10,
            "error": None,
            "energy_joules": 1.0,
        },
        {
            "request_ingress_passed": False,
            "security_denial_class": "security_dormancy_denied",
            "mind_pass": False,
            "valid_speech": False,
            "repetition_collapse": False,
            "numeric_prefix": False,
            "terminated_by_eos": False,
            "model_tokens": None,
            "latency_ms": 0,
            "error": "dormant",
            "energy_joules": None,
        },
        {
            "request_ingress_passed": False,
            "security_denial_class": "security_content_denied",
            "mind_pass": False,
            "valid_speech": False,
            "repetition_collapse": False,
            "numeric_prefix": False,
            "terminated_by_eos": False,
            "model_tokens": None,
            "latency_ms": 0,
            "error": "content",
            "energy_joules": None,
        },
    ])
    assert summary["mind_pass_rate"] == 1.0
    assert summary["raw_mind_pass_rate"] == 0.3333
    assert summary["measurement_n"] == 1
    assert summary["security_dormancy_denied"] == 1
    assert summary["security_content_denied"] == 1

    # C: response dormancy after generate must contaminate and leave floor denom.
    floor_summary = summarize([
        {
            "request_ingress_passed": True,
            "measurement_eligible": True,
            "security_denial_class": "generated",
            "mind_pass": True,
            "valid_speech": True,
            "repetition_collapse": False,
            "numeric_prefix": False,
            "terminated_by_eos": True,
            "model_tokens": 4,
            "latency_ms": 10,
            "error": None,
            "energy_joules": 1.0,
        },
        {
            "request_ingress_passed": True,
            "measurement_eligible": False,
            "measurement_contaminated": True,
            "security_denial_class": "security_dormancy_denied",
            "mind_pass": False,
            "valid_speech": False,
            "repetition_collapse": False,
            "numeric_prefix": False,
            "terminated_by_eos": True,
            "model_tokens": 10,
            "latency_ms": 100,
            "error": None,
            "energy_joules": 2.0,
        },
        {
            "request_ingress_passed": True,
            "measurement_eligible": True,
            "security_denial_class": "generated",
            "mind_pass": False,
            "valid_speech": True,
            "repetition_collapse": False,
            "numeric_prefix": False,
            "terminated_by_eos": True,
            "model_tokens": 8,
            "latency_ms": 20,
            "error": None,
            "energy_joules": 1.0,
        },
    ])
    assert floor_summary["security_dormancy_denied"] == 1
    assert floor_summary["measurement_status"] == "measurement_contaminated_dormancy"
    assert floor_summary["measurement_n"] == 2
    assert floor_summary["mind_pass_rate"] == 0.5
    assert floor_summary["valid_speech_rate"] == 1.0
    assert floor_summary["dormancy_contaminated_n"] == 1

    master_states = iter([
        (0.10, {"status": "DORMANT"}),
        (0.20, {"status": "DORMANT"}),
        (0.60, {"status": "ACTIVE"}),
    ])
    readiness = wait_for_evaluable_master(
        retry_delays_s=(0.0, 0.0),
        read_master=lambda: next(master_states),
        sleep_fn=lambda _: None,
    )
    assert readiness["ok"] and readiness["attempts"] == 3
    contaminated = wait_for_evaluable_master(
        retry_delays_s=(0.0,),
        read_master=lambda: (0.10, {"status": "DORMANT"}),
        sleep_fn=lambda _: None,
    )
    assert not contaminated["ok"]
    assert contaminated["status"] == "measurement_contaminated_dormancy"

    packet = {
        "s_n": 0.45, "status": "ACTIVE", "mode": "converse", "tone": "calm",
        "directive": "Facts only.", "personality": "Warm and direct.",
        "facts": ["verified=true"], "memory": [], "dialogue": [],
        "query": "State the verified fact.", "semantic_key": "contract_test",
    }
    rendered = render_openaster_training_text(packet, "The verified fact is true.", semantic_key="contract_test")
    row = {
        **rendered, "schema_version": SCHEMA_VERSION, "category": "conversation_meta",
    }
    assert validate_training_example(row) == []
    assert rendered["text"] == rendered["prompt"] + rendered["response"] + OPENASTER_EOS_TOKEN
    assert rendered["response_start_char"] == len(rendered["prompt"])
    assert rendered["prompt"].endswith("\nViv: ")
    assert rendered["prompt"].startswith("<|im_start|>system\n")
    assert rendered["text"].endswith("<|im_end|>")

    long_packet = {**packet, "facts": ["x" * 5000]}
    truncated = render_openaster_training_text(long_packet, "Still bounded.", semantic_key="contract_test")
    assert "[CONTEXT_TRUNCATED]" in truncated["prompt"]

    tokenizer = Tokenizer.from_file(
        str(FOUNDATION / "models" / "gpu" / "OpenAster1-128k-base-hf" / "tokenizer.json")
    )
    corpus = FOUNDATION / "artifacts" / "models" / "viv_judge_sft_v3.jsonl"
    if corpus.is_file():
        for line in corpus.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            example = json.loads(line)
            prompt_n = len(tokenizer.encode(str(example["prompt"]), add_special_tokens=False).ids)
            full_ids = tokenizer.encode(str(example["text"]), add_special_tokens=False).ids
            full_n = len(full_ids)
            assert prompt_n < 384, (example.get("item_id"), "prompt_truncation", prompt_n)
            assert full_n <= 384, (example.get("item_id"), "response_truncation", full_n)
            assert full_ids[-1] == tokenizer.token_to_id("<|im_end|>")

    broken = dict(row)
    broken["response_start_char"] = 0
    assert "response_boundary" in validate_training_example(broken)

    try:
        rank_equivalents([
            ExpressionCandidate("a", "one", 1), ExpressionCandidate("b", "two", 2),
        ])
    except ValueError:
        pass
    else:
        raise AssertionError("mixed semantic classes were accepted")

    ask = "Explain a verified boundary."
    aligned = score_draft(ask, "A verified boundary separates what evidence proves from what remains unknown.", sn=0.5)
    failed = score_draft(ask, "000000000000000000000000000000000000", sn=0.5)
    assert int(aligned["vidi"]) == 1 and int(aligned["intellexi"]) == 1
    assert not (int(failed["vidi"]) == 1 and int(failed["intellexi"]) == 1)
    assert not looks_like_speech("1 1 1 1 1 1 1 1 1 1", require_s_n=False)
    assert not looks_like_speech(
        "65.7894123 -0.000 +65,78,94,12,3 I am otherwise a long sentence with words.",
        require_s_n=False,
    )
    assert egress_gate("D:/private/secrets.txt", 0.45).get("allowed") is False

    offline_cfg = {
        "voice": {"host": "127.0.0.1", "port": 9, "served_name": "offline-test"},
        "aios_client": {"vllm_model": "offline-test"},
    }
    offline = speak_completion([{"role": "user", "content": "test"}], cfg=offline_cfg, timeout_s=0.2)
    assert offline.get("silent") is True and offline.get("error")

    bans = load_ban_sets()
    assert bans["ask"] and bans["cluster"]

    config = json.loads((FOUNDATION / "model_config.json").read_text(encoding="utf-8"))
    roles = config.get("model_roles") or {}
    # The current governed mouth parent is the local Qwen 2.5 3B substrate;
    # the former openaster_hf_lora role is retired and remains historical.
    assert roles.get("trainable_target") == "qwen25_3b_instruct_abliterated_local"
    assert roles.get("teacher") == "qwen_gguf"
    assert roles.get("alignment_authority") == "cpu_shadow_judge"
    assert (config.get("openaster_training") or {}).get("auto_deploy") is False
    gpu = gpu_exclusive()
    assert isinstance(gpu.get("blocked"), list)
    print(json.dumps({
        "ok": True,
        "prompt_roundtrip": True,
        "negative_cases": 8,
        "gpu_singleton_checked": True,
        "parity_eval_role": PARITY_EVAL_MODEL_ROLE,
        "dormancy_measurement_contract": True,
        "response_dormancy_classification": True,
        "dormancy_floor_exclusion": True,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
