#!/usr/bin/env python3
"""Verify the bounded identity/personality probe artifact."""
from __future__ import annotations

import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ARTIFACT = (
    FOUNDATION
    / "artifacts"
    / "auto"
    / "uml"
    / "viv_slm_identity_personality_v2"
    / "probes"
    / "identity_personality_probe_v1.json"
)


def main() -> int:
    result = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert result["schema_version"] == "viv_slm_identity_personality_probe_v1"
    assert result["status"] in {"PASS", "INCONCLUSIVE"}
    assert result["disposition"] == "bounded_lexical_probe_not_entailment_proof"
    assert result["summary"]["total"] == 6
    assert len(result["probes"]) == 6
    assert result["world_knowledge_included"] is False
    assert result["training_authorized"] is False
    assert result["run_authorized"] is False
    assert result["promotion_authorized"] is False
    assert result["deployment_changed"] is False
    assert result["live_runtime_mutation"] is False
    assert result["summary"]["telemetry_leaks"] == 0
    assert any(row["pass"] for row in result["probes"])
    print(
        "VIV_SLM_IDENTITY_PERSONALITY_PROBE_PASS "
        f"status={result['status']} pass={result['summary']['pass']} "
        f"total={result['summary']['total']} telemetry_leaks=0 "
        "training_authorized=false live_runtime_mutation=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
