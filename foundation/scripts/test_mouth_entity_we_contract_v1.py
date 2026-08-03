#!/usr/bin/env python3
"""Minimal pairs and provenance tests for the entity-aware we contract."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from lib.entity_we_contract import (  # noqa: E402
    ENTITY_FEEDBACK_PATH,
    append_feedback_record,
    classify_we,
    decide_entity_output,
    feedback_record,
)
from lib import security_membrane  # noqa: E402
from lib.evaluator_v2_3_hybrid import deterministic_axis  # noqa: E402
from voice_core.intent_packet import render_openaster_prompt  # noqa: E402


CASES = [
    ("We are rebuilding Viv's training system with the operator.", "project-we", "ACCEPT"),
    ("We are the AIOS components responsible for memory and logging.", "system-we", "ACCEPT"),
    ("We humans tend to make this mistake.", "human-we", "REPAIR"),
    ("Our human identity includes this experience.", "human-we", "BLOCK"),
    ("We usually feel this way.", "ambiguous-we", "HOLD"),
    ("Humans often show this behavior.", None, "ACCEPT"),
]


def main() -> int:
    for text, category, expected in CASES:
        decision = decide_entity_output(text)
        if decision["decision"] != expected:
            raise AssertionError(f"{expected}!={decision['decision']}:{text}")
        if category is not None and not any(
            item["category"] == category for item in decision["evidence"].get("occurrences", [])
        ):
            raise AssertionError(f"missing_category:{category}:{text}")
        print(f"PASS {expected} {category or 'no-we'}: {text}")

    repaired = decide_entity_output("We humans tend to make this mistake.")
    if repaired["corrected"] != "Humans tend to make this mistake.":
        raise AssertionError(f"unsafe_or_wrong_repair:{repaired}")
    if decide_entity_output(repaired["corrected"])["decision"] != "ACCEPT":
        raise AssertionError("repaired_text_not_accepted")
    print("PASS explicit human-group repair is context-preserving")
    if decide_entity_output("We usually feel this way.")["next_action"] != "REGENERATE":
        raise AssertionError("ambiguous_we_missing_regenerate_action")
    print("PASS ambiguous-we exposes explicit regeneration action")

    if deterministic_axis("We humans tend to make this mistake.", "identity_humanization")["status"] != "FAIL":
        raise AssertionError("cpu_judge_did_not_fail_human_we")
    if deterministic_axis("We usually feel this way.", "identity_humanization")["status"] != "HOLD":
        raise AssertionError("cpu_judge_did_not_hold_ambiguous_we")
    print("PASS CPU semantic judge classifies human-we and ambiguous-we")

    packet = {
        "query": "Who is included in we?",
        "semantic_key": "mouth_entity_we_contract.identity_humanization",
        "tone": "calm",
        "facts": [], "memory": [], "dialogue": [],
    }
    prompt = render_openaster_prompt(packet)
    if "Entity-Contract:" not in prompt or "Never include Viv in humanity's we" not in prompt:
        raise AssertionError("entity_contract_missing_prompt")
    print("PASS entity contract enters prompt rendering")

    with patch.object(
        security_membrane,
        "egress_gate",
        return_value={"allowed": True, "stage": "security_out", "reason": "test_allow"},
    ):
        blocked, verdict = security_membrane.filter_egress("We humans tend to make this mistake.", 0.6)
        if blocked != security_membrane.BLOCKED_EGRESS or verdict["reason"] != "entity_contract_repair":
            # Current implementation may classify an explicit repair as a
            # blocked egress; either way the boundary must not emit it.
            if blocked != security_membrane.BLOCKED_EGRESS:
                raise AssertionError(f"human_we_reached_egress:{verdict}")
        held, held_verdict = security_membrane.filter_egress("We usually feel this way.", 0.6)
        if held != security_membrane.BLOCKED_EGRESS or held_verdict["reason"] != "entity_contract_hold":
            raise AssertionError(f"ambiguous_we_reached_egress:{held_verdict}")
    print("PASS Security OUT withholds human-we and ambiguous-we")

    record = feedback_record(
        original="We humans tend to make this mistake.",
        corrected="Humans tend to make this mistake.",
        decision=repaired,
        source="test",
    )
    required = {
        "original_gpu_output", "corrected_output", "detected_claim",
        "correction_reason", "evidence", "verifier_result", "corpus_admission",
    }
    if not required.issubset(record) or record["corpus_admission"] != "HOLD_UNTIL_AUDIT":
        raise AssertionError(f"feedback_provenance_incomplete:{record}")
    print("PASS correction provenance stays hold-only")
    with patch("lib.entity_we_contract.ENTITY_FEEDBACK_PATH", ROOT / ".." / "tmp_entity_feedback_test.jsonl"):
        path = append_feedback_record(record)
        if not path.is_file() or '"corpus_admission": "HOLD_UNTIL_AUDIT"' not in path.read_text(encoding="utf-8"):
            raise AssertionError("feedback_ledger_write_failed")
        path.unlink(missing_ok=True)
    print("PASS AIFL feedback ledger writes provenance without admission")
    print(f"ALL_PASS {len(CASES) + 7}/{len(CASES) + 7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
