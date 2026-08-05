#!/usr/bin/env python3
"""Compare CPU-route-conditioned and unconditioned Viv-SLM speech."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.viv_slm_foundation import VivSLM  # noqa: E402
from run_viv_slm_identity_personality_semantic_probe_v1 import (  # noqa: E402
    _probe_row,
)
from run_viv_slm_identity_personality_v15_probe_v1 import (  # noqa: E402
    CONVERSATION_HOLDOUT_PROBES,
    CORE_HOLDOUT_PROBES,
    _conversation_probe,
)

CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v22_route_conditioned" / "runs" / "route_conditioned_steps_0250" / "checkpoint.pt"
VOCAB = VIV_ROOT / "models" / "viv_slm_identity_personality_v22_route_conditioned" / "inputs" / "VOCAB.json"
DEFAULT_OUTPUT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v22_route_conditioned" / "probes" / "route_conditioned_probe_steps_0250.json"

ROUTE_BY_PROBE = {
    "identity": "identity",
    "speech_style": "conversation",
    "operator_mirroring": "conversation",
    "missing_evidence": "evidence",
    "decision_authority": "architecture",
    "gpu_mouth_role": "architecture",
    "greeting": "conversation",
    "current_state": "conversation",
    "capability": "conversation",
    "plain_language": "conversation",
}


def _route_prompt(route: str, prompt: str) -> str:
    return f"Route: {route}\n{prompt}"


def _run_set(slm: VivSLM, *, conditioned: bool, seed_offset: int) -> list[dict[str, Any]]:
    core: list[dict[str, Any]] = []
    for index, (probe_id, prompt) in enumerate(CORE_HOLDOUT_PROBES):
        rendered_prompt = _route_prompt(ROUTE_BY_PROBE[probe_id], prompt) if conditioned else prompt
        row = _probe_row(slm, probe_id, rendered_prompt, seed=seed_offset + index)
        row["conditioned"] = conditioned
        row["cpu_route"] = ROUTE_BY_PROBE[probe_id] if conditioned else None
        core.append(row)
    conversation: list[dict[str, Any]] = []
    for index, (probe_id, prompt) in enumerate(CONVERSATION_HOLDOUT_PROBES):
        rendered_prompt = _route_prompt(ROUTE_BY_PROBE[probe_id], prompt) if conditioned else prompt
        row = _conversation_probe(slm, probe_id, rendered_prompt, seed=seed_offset + 100 + index)
        row["conditioned"] = conditioned
        row["cpu_route"] = ROUTE_BY_PROBE[probe_id] if conditioned else None
        conversation.append(row)
    return core + conversation


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(rows),
        "semantic_pass": sum(1 for row in rows if row["semantic_pass"]),
        "telemetry_leaks": sum(1 for row in rows if row["telemetry_leak"]),
    }


def run(*, checkpoint_path: Path = CHECKPOINT, vocab_path: Path = VOCAB, output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    slm = VivSLM.from_checkpoint(checkpoint_path, vocab_path=vocab_path, device="cpu")
    conditioned = _run_set(slm, conditioned=True, seed_offset=6200)
    unconditioned = _run_set(slm, conditioned=False, seed_offset=7200)
    result = {
        "schema_version": "viv_slm_route_conditioned_probe_v1",
        "status": "INCONCLUSIVE",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "model": slm.status(),
        "checkpoint": str(checkpoint_path).replace("\\", "/"),
        "vocab": str(vocab_path).replace("\\", "/"),
        "route_owner": "cpu",
        "route_header": "Route",
        "conditioned_probes": conditioned,
        "unconditioned_probes": unconditioned,
        "summary": {
            "conditioned": _summary(conditioned),
            "unconditioned": _summary(unconditioned),
        },
        "limitations": [
            "route-conditioned results assume the CPU supplies the correct semantic route",
            "phrase-family checks are not a formal entailment proof",
            "the unconditioned comparison is intentionally out of the V22 training packet",
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
    print(json.dumps({"status": "VIV_SLM_ROUTE_CONDITIONED_PROBE_" + result["status"], **result["summary"], "training_authorized": False, "live_runtime_mutation": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
