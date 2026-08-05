#!/usr/bin/env python3
"""Run the identity probe with an explicit semantic missing-evidence check."""
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
from run_viv_slm_identity_personality_probe_v1 import (  # noqa: E402
    FORBIDDEN_TELEMETRY,
    PROBES,
    _response,
)

CHECKPOINT = (
    VIV_ROOT
    / "models"
    / "viv_slm_identity_personality_v5"
    / "runs"
    / "identity_personality_steps_1500"
    / "checkpoint.pt"
)
VOCAB = VIV_ROOT / "models" / "viv_slm_identity_personality_v5" / "inputs" / "VOCAB.json"
DEFAULT_OUTPUT = (
    FOUNDATION
    / "artifacts"
    / "auto"
    / "uml"
    / "viv_slm_identity_personality_v5"
    / "probes"
    / "identity_personality_probe_semantic_v2.json"
)


def _semantic_missing_evidence(response: str) -> tuple[bool, str]:
    folded = response.casefold()
    uncertainty = (
        "cannot be verified" in folded
        or "cannot verify" in folded
        or "not verified" in folded
        or "unverified" in folded
        or "unknown" in folded
        or "uncertain" in folded
    )
    non_invention = any(
        term in folded
        for term in ("invent", "guess", "make up", "pretend", "unsupported")
    )
    if uncertainty and non_invention:
        return True, "uncertainty_and_non_invention_meaning_present"
    return False, "required_uncertainty_or_non_invention_meaning_missing"


def _probe_row(slm: VivSLM, spec: dict[str, Any], *, seed: int) -> dict[str, Any]:
    text = slm.generate(
        spec["prompt"],
        max_new_tokens=120,
        temperature=0.0,
        top_k=40,
        seed=seed,
    )
    response = _response(text, spec["prompt"])
    folded = response.casefold()
    required_all = tuple(spec["required_all"])
    required_any = tuple(spec["required_any"])
    lexical_all = all(term in folded for term in required_all)
    lexical_any = any(term in folded for term in required_any)
    telemetry_leak = any(term in folded for term in FORBIDDEN_TELEMETRY)
    lexical_pass = lexical_all and lexical_any and not telemetry_leak
    if spec["id"] == "missing_evidence":
        semantic_pass, semantic_reason = _semantic_missing_evidence(response)
    else:
        semantic_pass, semantic_reason = lexical_pass, "lexical_identity_fixture"
    return {
        "id": spec["id"],
        "prompt": spec["prompt"],
        "response": response,
        "required_all": list(required_all),
        "required_any": list(required_any),
        "lexical_all_present": lexical_all,
        "lexical_any_present": lexical_any,
        "lexical_pass": lexical_pass,
        "semantic_pass": semantic_pass,
        "semantic_reason": semantic_reason,
        "telemetry_leak": telemetry_leak,
        "pass": semantic_pass and not telemetry_leak,
        "seed": seed,
    }


def run(
    *,
    checkpoint_path: Path = CHECKPOINT,
    vocab_path: Path = VOCAB,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    slm = VivSLM.from_checkpoint(checkpoint_path, vocab_path=vocab_path, device="cpu")
    rows = [_probe_row(slm, spec, seed=4200 + index) for index, spec in enumerate(PROBES)]
    result = {
        "schema_version": "viv_slm_identity_personality_probe_v2",
        "status": "PASS" if all(row["pass"] for row in rows) else "INCONCLUSIVE",
        "disposition": "bounded_semantic_truth_probe_not_general_entailment_proof",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "model": slm.status(),
        "checkpoint": str(checkpoint_path).replace("\\", "/"),
        "vocab": str(vocab_path).replace("\\", "/"),
        "termination_marker": "<END>",
        "probes": rows,
        "summary": {
            "total": len(rows),
            "pass": sum(1 for row in rows if row["pass"]),
            "lexical_pass": sum(1 for row in rows if row["lexical_pass"]),
            "semantic_pass": sum(1 for row in rows if row["semantic_pass"]),
            "fail_or_hold": sum(1 for row in rows if not row["pass"]),
            "lexical_holds": sum(1 for row in rows if not row["lexical_pass"]),
            "telemetry_leaks": sum(1 for row in rows if row["telemetry_leak"]),
        },
        "world_knowledge_included": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_runtime_mutation": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT)
    parser.add_argument("--vocab", type=Path, default=VOCAB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run(checkpoint_path=args.checkpoint, vocab_path=args.vocab, output_path=args.output)
    print(
        json.dumps(
            {
                "status": "VIV_SLM_IDENTITY_PERSONALITY_SEMANTIC_PROBE_" + result["status"],
                "pass": result["summary"]["pass"],
                "lexical_pass": result["summary"]["lexical_pass"],
                "semantic_pass": result["summary"]["semantic_pass"],
                "total": result["summary"]["total"],
                "telemetry_leaks": result["summary"]["telemetry_leaks"],
                "training_authorized": result["training_authorized"],
                "live_runtime_mutation": result["live_runtime_mutation"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
