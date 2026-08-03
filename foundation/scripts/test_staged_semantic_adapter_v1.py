#!/usr/bin/env python3
"""Read-only regression for the explicit staged semantic knowledge mode."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIV = ROOT.parent
for path in (VIV, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.knowledge_staged_adapter import query_packet  # noqa: E402
from lib.aios_tagged_packet import verify_gpu_draft  # noqa: E402
from voice_core.intent_packet import build_intent_packet  # noqa: E402
from voice_core.intent_packet import contains_telemetry_disclosure  # noqa: E402
from voice_core.runtime_contract import finalize_draft  # noqa: E402


ARTIFACT = ROOT / "artifacts" / "auto" / "knowledge" / "wikipedia_redirect_resolved_staged_vectors_v1_20260803T014000Z.json"
MODEL = r"C:\Users\nemec\.cache\huggingface\sentence_transformers\models--sentence-transformers--all-MiniLM-L6-v2\snapshots\c9745ed1d9f207416be6d2e6f8de32d1f16199bf"


def main() -> int:
    old = os.environ.get("VIV_EMBED_MODEL_PATH")
    os.environ["VIV_EMBED_MODEL_PATH"] = MODEL
    try:
        result = query_packet("Autism spectrum", artifact_path=ARTIFACT, k=3, threshold=0.35)
        packet = build_intent_packet(
            query="What is autism spectrum?",
            knowledge_query="Autism spectrum",
            knowledge_mode="staged_semantic",
            mode="converse",
        )
    finally:
        if old is None:
            os.environ.pop("VIV_EMBED_MODEL_PATH", None)
        else:
            os.environ["VIV_EMBED_MODEL_PATH"] = old
    assert result["ok"] and result["mode"] == "staged_semantic_read_only", result
    hits = result["hits"]
    assert hits and any("Autism" in str(hit.get("doc")) for hit in hits), result
    assert result["packet"]["facts"][0]["source"]["root"] == "F_AI_DATASETS"
    assert result["evidence"]["vector_index_written"] is False
    assert packet["knowledge_packet"]["facts"]
    assert any(str(fact).startswith("know=") for fact in packet["facts"])
    finalized = finalize_draft(
        query=packet["query"],
        packet=packet,
        raw_text="Autism spectrum is definitely whatever the draft invents.",
        voice_source="staged_semantic_test",
    )
    assert "autism" in finalized["text"].casefold()
    assert not contains_telemetry_disclosure(finalized["text"])
    assert verify_gpu_draft(packet["tagged_packet"], finalized["text"]).status == "PASS"
    print(f"STAGED_SEMANTIC_ADAPTER_PASS hits={len(hits)} top={hits[0]['doc']} writes=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
