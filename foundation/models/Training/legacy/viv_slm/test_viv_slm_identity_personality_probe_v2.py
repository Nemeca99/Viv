#!/usr/bin/env python3
"""Verify the semantic identity/personality probe disposition."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ARTIFACT = (
    FOUNDATION
    / "artifacts"
    / "auto"
    / "uml"
    / "viv_slm_identity_personality_v5"
    / "probes"
    / "identity_personality_probe_semantic_v2.json"
)


def main() -> int:
    result = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    missing = next(row for row in result["probes"] if row["id"] == "missing_evidence")
    assert result["schema_version"] == "viv_slm_identity_personality_probe_v2"
    assert result["status"] == "PASS"
    assert result["disposition"] == "bounded_semantic_truth_probe_not_general_entailment_proof"
    assert result["summary"] == {
        "fail_or_hold": 0,
        "lexical_holds": 1,
        "lexical_pass": 5,
        "pass": 6,
        "semantic_pass": 6,
        "telemetry_leaks": 0,
        "total": 6,
    }
    assert missing["lexical_pass"] is False
    assert missing["semantic_pass"] is True
    assert "cannot be verified" in missing["response"].casefold()
    assert "invent" in missing["response"].casefold()
    assert result["world_knowledge_included"] is False
    assert result["training_authorized"] is False
    assert result["run_authorized"] is False
    assert result["promotion_authorized"] is False
    assert result["deployment_changed"] is False
    assert result["live_runtime_mutation"] is False
    print(
        "VIV_SLM_IDENTITY_PERSONALITY_SEMANTIC_PROBE_PASS "
        "semantic_pass=6 lexical_pass=5 lexical_holds=1 telemetry_leaks=0 "
        "training_authorized=false live_runtime_mutation=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
