#!/usr/bin/env python3
"""Read-only canary for CPU identity routing plus the replaceable SLM mouth.

The v8 paraphrase pack is intentionally not treated as proof that the small
character model understands arbitrary intent.  This canary tests the intended
architecture instead: the CPU recognizes a reviewed identity/personality
intent, maps it to a canonical prompt, and supplies the authorized meaning;
the SLM may render that canonical prompt, while the CPU mouth contract can
reject it and use the deterministic fallback.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for path in (FOUNDATION, VIV_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.cpu_identity_router import route_identity_query  # noqa: E402
from lib.cpu_mouth_contract import build_render_envelope, render_with_cpu_validation  # noqa: E402
from lib.viv_slm_foundation import VivSLM  # noqa: E402


CHECKPOINT = (
    VIV_ROOT
    / "models"
    / "viv_slm_identity_personality_v7"
    / "runs"
    / "identity_personality_steps_1750"
    / "checkpoint.pt"
)
VOCAB = VIV_ROOT / "models" / "viv_slm_identity_personality_v7" / "inputs" / "VOCAB.json"
V8_ROOT = VIV_ROOT / "foundation" / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v8"
PARAPHRASE_SOURCE = "viv_identity_personality_paraphrase_pack_v8"


def _paraphrase_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(V8_ROOT.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("source") == PARAPHRASE_SOURCE:
                rows.append(row)
    return rows


def _expected_intent(example_id: str) -> str:
    prefix = str(example_id).split("-para-", 1)[0]
    return {"boundary": "authority", "mirror": "mirroring"}.get(prefix, prefix)


def _render_envelope(route: dict[str, Any], prompt: str) -> dict[str, Any]:
    intent = str(route["intent_id"])
    authorized_text = str(route["authorized_text"])
    kwargs: dict[str, Any] = {
        "query": prompt,
        "mode": str(route["mode"]),
        "facts": [
            {
                "id": f"identity_{intent}",
                "text": authorized_text,
                "source": "cpu_identity_router_v1",
                "confidence": "verified",
            }
        ],
        "decision": {"id": f"identity_{intent}_render", "value": "render_cpu_identity_meaning"},
        "provenance": {
            "source": "read_only_cpu_identity_router_canary",
            "intent_id": intent,
            "router_version": str(route["router_version"]),
            "confidence": "verified",
        },
        "fallback_text": authorized_text,
        "identity": {"name": "Viv", "owner": "cpu"},
    }
    if intent == "health":
        kwargs["freshness"] = {"state": "unverified", "max_age_s": 3.0}
    return build_render_envelope(**kwargs)


def main() -> int:
    rows = _paraphrase_rows()
    assert len(rows) == 40, len(rows)
    slm = VivSLM.from_checkpoint(CHECKPOINT, vocab_path=VOCAB, device="cpu")

    fallback_count = 0
    for row in rows:
        prompt = str(row["prompt"])
        expected = _expected_intent(str(row["example_id"]))
        route = route_identity_query(prompt)
        assert route["ok"] is True, {"prompt": prompt, "route": route}
        assert route["intent_id"] == expected, {"prompt": prompt, "route": route, "expected": expected}
        assert route["renderer_may_change"] is False
        envelope = _render_envelope(route, prompt)
        canonical_query = str(route["canonical_query"])
        result = render_with_cpu_validation(
            envelope,
            lambda _, query=canonical_query: slm.render_query(query),
        )
        assert result["accepted"] is True, {"prompt": prompt, "result": result}
        assert result["decision_digest"] == envelope["decision_digest"]
        assert result["validation"]["status"] == "PASS"
        fallback_count += int(bool(result["fallback_used"]))

    unrelated = route_identity_query("What is photosynthesis?")
    assert unrelated["ok"] is False
    assert unrelated["state"] == "UNROUTED"
    print(
        "CPU_IDENTITY_ROUTER_PASS "
        f"paraphrases_routed={len(rows)} mouth_accepted={len(rows)} "
        f"cpu_fallbacks={fallback_count} unrelated_unrouted=true "
        "live_runtime_mutation=false deployment_changed=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
