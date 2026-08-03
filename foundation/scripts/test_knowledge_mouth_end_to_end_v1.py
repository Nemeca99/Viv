"""Read-only regression for source-grounded knowledge reaching the mouth."""
from __future__ import annotations

import sys
from pathlib import Path

VIV = Path(__file__).resolve().parents[2]
FOUNDATION = VIV / "foundation"
for path in (VIV, FOUNDATION):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.aios_tagged_packet import verify_gpu_draft  # noqa: E402
from voice_core.intent_packet import build_intent_packet, contains_telemetry_disclosure  # noqa: E402
from voice_core.runtime_contract import finalize_draft  # noqa: E402


def main() -> int:
    packet = build_intent_packet(
        query="What is autism spectrum?",
        knowledge_query="Autism spectrum",
        knowledge_mode="multi_source",
        wikipedia_title="Autism",
        include_legacy_wikipedia=True,
        resolve_legacy_redirects=True,
        mode="converse",
    )
    finalized = finalize_draft(
        query=packet["query"],
        packet=packet,
        raw_text="untrusted draft",
        voice_source="regression",
    )
    text = str(finalized["text"])
    verification = verify_gpu_draft(packet["tagged_packet"], text)
    assert packet["knowledge_packet"]["state"] == "VERIFIED"
    assert any(str(f).startswith("know=") for f in packet["facts"])
    assert "autism" in text.casefold()
    assert text != "I'm here with you, and I'll answer that directly."
    assert not contains_telemetry_disclosure(text)
    assert verification.status == "PASS", verification.to_dict()
    assert "ASD" not in text
    print(
        "KNOWLEDGE_MOUTH_END_TO_END_PASS "
        f"grounding={bool(finalized.get('knowledge_grounding'))} "
        f"verification={verification.status} telemetry_contained=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
