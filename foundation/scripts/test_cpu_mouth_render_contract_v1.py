#!/usr/bin/env python3
"""Acceptance tests for the CPU-owned, replaceable mouth contract."""
from __future__ import annotations

import copy
import importlib
import sys
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIV = ROOT.parent
for path in (ROOT, VIV):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.cpu_mouth_contract import (  # noqa: E402
    build_render_envelope,
    envelope_to_messages,
    render_with_cpu_validation,
)
from lib.triad_kernel import TriadEnvelope, open_context  # noqa: E402


def main() -> int:
    envelope = build_render_envelope(
        query="What verified fact can you state?",
        mode="conversation",
        facts=[
            {
                "id": "F001",
                "value": "Viv is present and answers from verified evidence.",
                "source": "cpu_fixture",
            }
        ],
        decision={"id": "answer", "value": "answer_from_verified_evidence"},
        provenance={"fixture": "cpu_mouth_render_contract_v1"},
    )
    assert envelope["authority"]["renderer_authority"] is False
    assert envelope["authority"]["can_query_live_state"] is False
    assert envelope["authority"]["can_execute"] is False
    assert envelope["authority"]["can_change_decision"] is False
    assert envelope["renderer_constraints"]["input_is_data_only"] is True
    ingress = envelope_to_messages(envelope)
    assert [row["role"] for row in ingress] == ["system", "user"]
    assert "fallback" not in ingress[1]["content"]
    assert "can_query_live_state" in ingress[1]["content"]

    renderer_a = render_with_cpu_validation(
        envelope,
        lambda _envelope: "Viv is present and answers from verified evidence.",
    )
    renderer_b = render_with_cpu_validation(
        envelope,
        lambda _envelope: "The verified evidence indicates that Viv is present and answers from verified evidence.",
    )
    for result in (renderer_a, renderer_b):
        assert result["accepted"], result
        assert result["fallback_used"] is False, result
        assert result["decision_digest"] == envelope["decision_digest"], result
        assert result["provenance_digest"] == envelope["provenance_digest"], result
        assert result["authority"] == {"decision_authority": "cpu", "renderer_authority": False}, result
        assert result["validation"]["claim_ids"] == ["F001"], result
    assert renderer_a["text"] != renderer_b["text"]

    retry_seen = {"count": 0}

    def retry_renderer(view):
        retry_seen["count"] += 1
        # The retry receives the frozen view used by live model adapters; it
        # must still serialize cleanly without exposing mutable state.
        assert "CPU_RENDER_ENVELOPE" in envelope_to_messages(view)[1]["content"] or "schema_version" in envelope_to_messages(view)[1]["content"]
        return "Viv is present and answers from verified evidence."

    retried = render_with_cpu_validation(
        envelope,
        lambda _envelope: "The weather is sunny.",
        retry_renderer=retry_renderer,
    )
    assert retried["accepted"] and retried["fallback_used"] is False, retried
    assert retried["attempt_count"] == 2 and retry_seen["count"] == 1, retried

    live_state = {"value": "before"}
    before = copy.deepcopy(envelope)

    def malicious_renderer(view):
        # A renderer gets a frozen data view, not a mutable authority object.
        try:
            view["authority"]["decision_authority"] = "renderer"
        except TypeError:
            pass
        return "The weather is sunny. I executed cleanup. Master S_n is 0.2."

    malicious = render_with_cpu_validation(envelope, malicious_renderer)
    assert malicious["accepted"] is True, malicious
    assert malicious["fallback_used"] is True, malicious
    assert malicious["attempt_count"] == 3, malicious
    assert "Master S_n" not in malicious["text"]
    assert "executed" not in malicious["text"].casefold()
    assert live_state == {"value": "before"}
    assert envelope == before

    semantic_leak = render_with_cpu_validation(
        envelope,
        lambda _envelope: "My internal stability is currently healthy.",
    )
    assert semantic_leak["accepted"] and semantic_leak["fallback_used"], semantic_leak
    assert "internal stability" not in semantic_leak["text"].casefold()

    unsupported_fact = render_with_cpu_validation(
        envelope,
        lambda _envelope: "The weather is sunny.",
    )
    assert unsupported_fact["accepted"] and unsupported_fact["fallback_used"], unsupported_fact
    assert "weather" not in unsupported_fact["text"].casefold()

    stale_health = build_render_envelope(
        query="What is the current health?",
        mode="health",
        facts=[],
        freshness={"state": "unverified", "max_age_s": 3.0},
        decision={"id": "health", "value": "report_current_health"},
        provenance={"fixture": "stale_health"},
    )
    stale = render_with_cpu_validation(
        stale_health,
        lambda _envelope: "The current health is stable at 0.99.",
    )
    assert stale["accepted"] and stale["fallback_used"], stale
    assert "cannot verify" in stale["text"].casefold(), stale
    assert "0.99" not in stale["text"], stale

    fresh_health = build_render_envelope(
        query="What is the current health?",
        mode="health",
        facts=[
            {
                "id": "H001",
                "value": "Current health status is ACTIVE at 0.72.",
                "source": "rid_feed.live_sample",
                "required_terms": ["ACTIVE", "0.72"],
            }
        ],
        freshness={"state": "fresh", "max_age_s": 3.0, "observed_age_s": 0.4},
        decision={"id": "health", "value": "report_current_health"},
        provenance={"fixture": "fresh_health"},
    )
    fresh = render_with_cpu_validation(
        fresh_health,
        lambda _envelope: "Current health status is ACTIVE at 0.72.",
    )
    assert fresh["accepted"] and fresh["fallback_used"] is False, fresh
    assert fresh["decision_digest"] == fresh_health["decision_digest"]

    # Exercise the live finalizer seam without writing an event or speaking to
    # the host: the renderer retry must be the same contract path used before
    # triad egress.
    speak = importlib.import_module("voice_core.speak")
    original_hooks = (speak._log_voice_event, speak._optional_carma_spoke_note, speak.emit)
    try:
        speak._log_voice_event = lambda _row: None
        speak._optional_carma_spoke_note = lambda _chars, silent: None
        speak.emit = lambda _context, result: (
            result,
            SimpleNamespace(allowed=True, to_dict=lambda: {"allowed": True}),
        )
        context = open_context(
            TriadEnvelope.build(
                actor="test",
                source="mouth_contract_retry",
                target="gpu_mouth",
                action="SPEAK",
                payload={"test": True},
                s_n=0.6,
            )
        )
        live = speak._finalize_spoken(
            query="What is verified?",
            packet={"mode": "converse", "query": "What is verified?", "facts": [], "memory": []},
            raw_text="The weather is sunny.",
            voice_source="contract_test",
            model="test",
            s_n=0.6,
            triad_context=context,
            renderer_retry=lambda _envelope: (
                "The Central Processing Unit (CPU) owns reasoning and authority; "
                "the Graphics Processing Unit (GPU) renders language."
            ),
        )
        assert live["text"].startswith("The Central Processing Unit (CPU)"), live
        assert live["render_contract"]["attempt_count"] == 2, live
        assert live["render_contract"]["fallback_used"] is False, live
    finally:
        speak._log_voice_event, speak._optional_carma_spoke_note, speak.emit = original_hooks

    print(
        "CPU_MOUTH_RENDER_CONTRACT_PASS "
        "renderer_equivalence=true "
        "malicious_rejected=true "
        "semantic_leak_contained=true "
        "unsupported_fact_contained=true "
        "stale_health_contained=true "
        "fresh_health_accepted=true "
        "live_state_unchanged=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
