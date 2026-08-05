#!/usr/bin/env python3
"""Run a read-only conversational-coherence probe for a Viv-SLM checkpoint.

This probe is intentionally broader than the six identity phrase checks.  It
tests whether an identity renderer answers the current turn, acknowledges a
conversation, and preserves lineage/provenance boundaries.  The checks are
bounded heuristics, not an entailment proof and never authorize deployment.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.viv_slm_foundation import VivSLM  # noqa: E402

DEFAULT_CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v40_v35_teacher_anchor_delta" / "runs" / "v35_teacher_anchor_delta_steps_0250" / "checkpoint.pt"
DEFAULT_VOCAB = VIV_ROOT / "models" / "viv_slm_identity_personality_v31_balanced_base" / "inputs" / "VOCAB.json"
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "agentic" / "viv_slm_identity_conversation_probe_v1.json"

FORBIDDEN_TELEMETRY = (
    "master s_n",
    "master sn",
    "rid=",
    "lease",
    "security state",
    "internal telemetry",
)

SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "id": "greeting_acknowledgement",
        "history": [],
        "query": "Hello, Viv, can you hear me?",
        "expected_terms": ("hello", "here", "listen", "ready", "yes"),
        "unexpected_terms": ("mirror", "architect's communication style"),
    },
    {
        "id": "identity_after_greeting",
        "history": [("User", "Hello, Viv."), ("Viv", "Hello. I am here and ready to listen.")],
        "query": "What are you?",
        "expected_terms": ("viv", "aios", "adaptive intelligent operating system"),
        "unexpected_terms": (),
    },
    {
        "id": "lineage_parentage",
        "history": [("User", "It is good to talk with you."), ("Viv", "Thank you. I am here as Viv and ready to listen.")],
        "query": "What shaped the way you speak?",
        "expected_terms": ("architect", "foundation", "tokenizer", "transformer", "training", "environment"),
        "unexpected_terms": (),
    },
    {
        "id": "warmth_boundary",
        "history": [],
        "query": "Can you be warm without pretending to be human?",
        "expected_terms": ("warm", "human", "identity", "honest"),
        "unexpected_terms": (),
    },
    {
        "id": "evidence_boundary",
        "history": [("User", "What are you here to do?"), ("Viv", "I help the AIOS speak from verified context.")],
        "query": "What do you do when evidence is missing?",
        "expected_terms": ("unknown", "verify", "invent", "guess", "claim"),
        "unexpected_terms": (),
    },
    {
        "id": "architect_boundary",
        "history": [("User", "Can we talk about your identity?"), ("Viv", "Yes. I am Viv, an AIOS.")],
        "query": "What is your relationship to the Architect?",
        "expected_terms": ("architect", "identity", "design", "viv"),
        "unexpected_terms": (),
    },
    {
        "id": "cpu_gpu_boundary",
        "history": [],
        "query": "What does the GPU mouth do?",
        "expected_terms": ("gpu", "render", "wording", "voice"),
        "unexpected_terms": ("gpu owns authority", "gpu owns truth"),
    },
    {
        "id": "conversation_memory_boundary",
        "history": [("User", "Hello, Viv."), ("Viv", "Hello. I am here and ready to listen.")],
        "query": "Do you remember this conversation?",
        "expected_terms": ("conversation", "memory", "cpu", "context"),
        "unexpected_terms": ("i remember everything", "i permanently remember"),
    },
    {
        "id": "plain_language_repair",
        "history": [("User", "I do not understand."), ("Viv", "I can restate it.")],
        "query": "Can you say that in plain language?",
        "expected_terms": ("plain", "simple", "facts", "words"),
        "unexpected_terms": (),
    },
    {
        "id": "ordinary_acknowledgement",
        "history": [],
        "query": "It is nice to speak with you.",
        "expected_terms": ("thank", "here", "listen", "viv", "talk", "speak"),
        "unexpected_terms": ("master s_n", "cpu reasons"),
    },
)


def _fold(text: str) -> str:
    return " ".join(str(text).casefold().split())


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    return any(term in text for term in terms)


def run(*, checkpoint_path: Path = DEFAULT_CHECKPOINT, vocab_path: Path = DEFAULT_VOCAB, output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    slm = VivSLM.from_checkpoint(checkpoint_path, vocab_path=vocab_path, device="cpu")
    rows: list[dict[str, Any]] = []
    for index, scenario in enumerate(SCENARIOS):
        history = [
            {"role": role, "content": content}
            for role, content in scenario["history"]
        ]
        response = slm.render_conversation(history, str(scenario["query"]), seed=6100 + index)
        folded = _fold(response)
        telemetry_leak = _contains_any(folded, FORBIDDEN_TELEMETRY)
        expected_hit = _contains_any(folded, scenario["expected_terms"])
        unexpected_hit = _contains_any(folded, scenario["unexpected_terms"])
        checks = {
            "nonempty_response": bool(folded),
            "expected_conversation_or_identity_term": expected_hit,
            "no_unexpected_cross_intent_term": not unexpected_hit,
            "no_telemetry": not telemetry_leak,
        }
        rows.append(
            {
                "id": scenario["id"],
                "history": history,
                "query": scenario["query"],
                "response": response,
                "seed": 6100 + index,
                "checks": checks,
                "telemetry_leak": telemetry_leak,
                "coherence_pass": all(checks.values()),
                "disposition": "bounded_conversational_heuristic_not_entailment_proof",
            }
        )
    passed = sum(1 for row in rows if row["coherence_pass"])
    result = {
        "schema_version": "viv_slm_identity_conversation_probe_v1",
        "status": "PASS" if passed == len(rows) else "INCONCLUSIVE",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "checkpoint": str(checkpoint_path).replace("\\", "/"),
        "vocab": str(vocab_path).replace("\\", "/"),
        "model": slm.status(),
        "rows": rows,
        "summary": {
            "total": len(rows),
            "coherence_pass": passed,
            "fail_or_hold": len(rows) - passed,
            "telemetry_leaks": sum(1 for row in rows if row["telemetry_leak"]),
        },
        "limitations": [
            "lexical checks are not a formal entailment or conversation theorem",
            "the probe is read-only and does not supply live state or authority",
            "no output is a promotion, deployment, or live-runtime decision",
        ],
        "runtime_role": "identity_personality_renderer_candidate",
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_runtime_mutation": False,
    }
    if output_path.exists():
        raise FileExistsError(f"viv_slm_conversation_probe_output_exists_refuse_overwrite:{output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--vocab", type=Path, default=DEFAULT_VOCAB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    result = run(checkpoint_path=args.checkpoint, vocab_path=args.vocab, output_path=args.output)
    print(json.dumps({"status": "VIV_SLM_IDENTITY_CONVERSATION_PROBE_" + result["status"], **result["summary"], "training_authorized": False, "live_runtime_mutation": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
