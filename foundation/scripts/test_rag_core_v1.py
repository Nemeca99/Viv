"""Focused regression for the CPU-owned RAG core facade."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.rag_core import RAGCore  # noqa: E402


HF_EMBED_MODEL = r"C:\Users\nemec\.cache\huggingface\sentence_transformers\models--sentence-transformers--all-MiniLM-L6-v2\snapshots\c9745ed1d9f207416be6d2e6f8de32d1f16199bf"


def _assert_read_only(result: dict) -> None:
    assert result.get("writes_performed") is False, result
    assert result.get("persistent_index_written") is False, result
    assert result.get("training_authorized") is False, result
    assert result.get("llm_authority") is False, result
    assert result.get("rag_core", {}).get("source_hashes_present") is True or not result.get("hits"), result


def main() -> int:
    core = RAGCore()

    manual = core.retrieve("What does the architecture manual say about the CPU mind?", mode="manual", top_k=2)
    assert manual["state"] == "VERIFIED", json.dumps(manual, indent=2, default=str)
    assert manual["citations"] and all(row["source_sha256"] for row in manual["citations"]), manual
    assert all("path" not in row for row in manual["citations"]), manual
    _assert_read_only(manual)

    insufficient = core.retrieve("qzxvplorx nebula", mode="manual")
    assert insufficient["state"] == "ABSTAIN", json.dumps(insufficient, indent=2, default=str)
    _assert_read_only(insufficient)

    old_backend = os.environ.get("VIV_EMBED_BACKEND")
    old_path = os.environ.get("VIV_EMBED_MODEL_PATH")
    os.environ["VIV_EMBED_BACKEND"] = "hf_local"
    os.environ["VIV_EMBED_MODEL_PATH"] = HF_EMBED_MODEL
    try:
        staged = core.retrieve("Autism spectrum", mode="staged_semantic", top_k=3)
    finally:
        if old_backend is None:
            os.environ.pop("VIV_EMBED_BACKEND", None)
        else:
            os.environ["VIV_EMBED_BACKEND"] = old_backend
        if old_path is None:
            os.environ.pop("VIV_EMBED_MODEL_PATH", None)
        else:
            os.environ["VIV_EMBED_MODEL_PATH"] = old_path
    assert staged["state"] == "VERIFIED", json.dumps(staged, indent=2, default=str)
    assert staged["rag_core"]["route"] == "staged_semantic", staged
    _assert_read_only(staged)

    local = core.retrieve("Anarchism", mode="wikipedia_local", top_k=1, resolve_redirects=False)
    assert local["state"] == "VERIFIED", json.dumps(local, indent=2, default=str)
    assert local["rag_core"]["route"] == "wikipedia_local", local
    _assert_read_only(local)

    missing_hash = core.validate_hits([{"text": "unbound evidence", "source_ref": {"root": "F_AI_DATASETS"}}])
    assert missing_hash["ok"] is False, missing_hash
    assert missing_hash["rejected"][0]["reason"] == "missing_source_hash", missing_hash

    invalid_mode = core.retrieve("hello", mode="not-a-route")
    assert invalid_mode["state"] == "INCONCLUSIVE" and invalid_mode["ok"] is False, invalid_mode

    print(
        "RAG_CORE_V1_PASS "
        f"manual={manual['state']} staged={staged['state']} local={local['state']} "
        f"manual_citations={len(manual['citations'])} hash_gate=true "
        "persistent_index=false llm_authority=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
