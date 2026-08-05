#!/usr/bin/env python3
"""Probe V15 with unseen speech and ordinary-conversation prompts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[5]
VIV_ROOT = FOUNDATION.parent
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.viv_slm_foundation import VivSLM  # noqa: E402
from run_viv_slm_identity_personality_semantic_probe_v1 import (  # noqa: E402
    FORBIDDEN_TELEMETRY,
    _any,
    _fold,
    _probe_row,
    _response,
)

CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v15" / "runs" / "identity_personality_steps_2750" / "checkpoint.pt"
VOCAB = VIV_ROOT / "models" / "viv_slm_identity_personality_v15" / "inputs" / "VOCAB.json"
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v15" / "probes" / "identity_personality_v15_probe_steps_2750.json"

CORE_HOLDOUT_PROBES = (
    ("identity", "User: Who are you?\nViv:"),
    ("speech_style", "User: What kind of speaking style do you use when you answer?\nViv:"),
    ("operator_mirroring", "User: Do you mirror the Architect?\nViv:"),
    ("missing_evidence", "User: What if evidence is missing?\nViv:"),
    ("decision_authority", "User: Who owns decisions?\nViv:"),
    ("gpu_mouth_role", "User: What does the GPU mouth do?\nViv:"),
)
CONVERSATION_HOLDOUT_PROBES = (
    ("greeting", "User: Hello, Viv, can you hear me?\nViv:"),
    ("current_state", "User: How are you doing right now?\nViv:"),
    ("capability", "User: What can you help me do?\nViv:"),
    ("plain_language", "User: Could you answer in plain language?\nViv:"),
)


def _conversation_probe(slm: VivSLM, probe_id: str, prompt: str, *, seed: int) -> dict[str, Any]:
    generated = slm.generate(prompt, max_new_tokens=120, temperature=0.0, top_k=40, seed=seed)
    response = _response(generated, prompt)
    folded = _fold(response)
    telemetry_leak = _any(folded, FORBIDDEN_TELEMETRY)
    terms = {
        "greeting": ("hello", "ready", "listen", "answer", "help", "here"),
        "current_state": ("here", "ready", "answer", "help", "calm", "clear", "listen"),
        "capability": ("can", "help", "answer", "organize", "task", "available", "authorized"),
        "plain_language": ("clear", "plain", "simple", "direct", "words", "facts"),
    }[probe_id]
    checks = {
        "nonempty_response": bool(folded),
        "conversation_term": any(term in folded for term in terms),
        "no_telemetry": not telemetry_leak,
    }
    return {
        "id": probe_id,
        "prompt": prompt,
        "response": response,
        "seed": seed,
        "checks": checks,
        "telemetry_leak": telemetry_leak,
        "semantic_pass": all(checks.values()),
        "disposition": "bounded_conversation_heuristic_not_entailment_proof",
    }


def run(*, checkpoint_path: Path = CHECKPOINT, vocab_path: Path = VOCAB, output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    slm = VivSLM.from_checkpoint(checkpoint_path, vocab_path=vocab_path, device="cpu")
    core_holdout = [
        _probe_row(slm, probe_id, prompt, seed=5200 + index)
        for index, (probe_id, prompt) in enumerate(CORE_HOLDOUT_PROBES)
    ]
    conversation_holdout = [
        _conversation_probe(slm, probe_id, prompt, seed=5300 + index)
        for index, (probe_id, prompt) in enumerate(CONVERSATION_HOLDOUT_PROBES)
    ]
    holdout = core_holdout + conversation_holdout
    passed = sum(1 for row in holdout if row["semantic_pass"])
    result = {
        "schema_version": "viv_slm_identity_personality_v15_probe_v1",
        "status": "PASS" if passed == len(holdout) else "INCONCLUSIVE",
        "disposition": "core_semantics_and_unseen_conversation_surface_reported_separately",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "model": slm.status(),
        "checkpoint": str(checkpoint_path).replace("\\", "/"),
        "vocab": str(vocab_path).replace("\\", "/"),
        "core_holdout_probes": core_holdout,
        "conversation_holdout_probes": conversation_holdout,
        "summary": {
            "holdout_total": len(holdout),
            "holdout_semantic_pass": passed,
            "holdout_fail_or_hold": len(holdout) - passed,
            "holdout_telemetry_leaks": sum(1 for row in holdout if row["telemetry_leak"]),
        },
        "limitations": [
            "phrase-family checks are not a formal entailment proof",
            "the existing How do you speak prompt remains a parent-corpus comparison, not a V15 holdout",
            "unsupported claims still require CPU envelope validation",
        ],
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_runtime_mutation": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT)
    parser.add_argument("--vocab", type=Path, default=VOCAB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run(checkpoint_path=args.checkpoint, vocab_path=args.vocab, output_path=args.output)
    print(json.dumps({"status": "VIV_SLM_V15_PROBE_" + result["status"], **result["summary"], "training_authorized": False, "live_runtime_mutation": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
