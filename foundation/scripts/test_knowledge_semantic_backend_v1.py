#!/usr/bin/env python3
"""Contract tests for the local semantic backend adapter."""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import knowledge_semantic_backend as backend  # noqa: E402


class _FakeResponse:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return self.payload


def main() -> int:
    with patch.object(backend, "_post_embedding", side_effect=[[1.0, 0.0], [0.0, 1.0]]):
        result = backend.semantic_compare("one", "two")
    assert result["ok"] is True and result["backend"] == "ollama_viv_embed"
    assert result["score"] == 0.0 and result["dimensions"] == 2

    with patch.object(backend, "_post_embedding", side_effect=OSError("ollama_unavailable")):
        unavailable = backend.semantic_compare("one", "two")
    assert unavailable["ok"] is False and unavailable["state"] == "INCONCLUSIVE"
    assert unavailable["backend"] == "ollama_viv_embed"

    with patch.object(backend, "_post_embedding", side_effect=[[1.0, 0.0], [1.0, 0.0]]):
        aligned = backend.semantic_compare("one", "one")
    assert aligned["ok"] is True and aligned["score"] == 1.0

    old_endpoint = os.environ.get("VIV_EMBED_ENDPOINT")
    old_model = os.environ.get("VIV_EMBED_MODEL")
    old_backend = os.environ.get("VIV_EMBED_BACKEND")
    try:
        os.environ["VIV_EMBED_ENDPOINT"] = "http://127.0.0.1:1234/v1/embeddings"
        os.environ["VIV_EMBED_MODEL"] = "text-embedding-nomic-embed-text-v1.5"
        with patch.object(
            backend.urllib.request,
            "urlopen",
            return_value=_FakeResponse({"data": [{"embedding": [1.0, 0.0]}]}),
        ):
            vector = backend._post_embedding(
                "one",
                endpoint=os.environ["VIV_EMBED_ENDPOINT"],
                model=os.environ["VIV_EMBED_MODEL"],
                timeout_s=1.0,
            )
        assert vector == [1.0, 0.0]
        with patch.object(backend, "_post_embedding", side_effect=[[1.0, 0.0], [1.0, 0.0]]):
            compatible = backend.semantic_compare("one", "one")
        assert compatible["backend"] == "openai_compatible_embedding"

        os.environ["VIV_EMBED_BACKEND"] = "hf_local"
        with patch.object(backend, "_local_embedding", side_effect=[[1.0, 0.0], [0.0, 1.0]]):
            local = backend.semantic_compare("one", "two")
        assert local["ok"] is True and local["backend"] == "huggingface_local"
    finally:
        if old_endpoint is None:
            os.environ.pop("VIV_EMBED_ENDPOINT", None)
        else:
            os.environ["VIV_EMBED_ENDPOINT"] = old_endpoint
        if old_model is None:
            os.environ.pop("VIV_EMBED_MODEL", None)
        else:
            os.environ["VIV_EMBED_MODEL"] = old_model
        if old_backend is None:
            os.environ.pop("VIV_EMBED_BACKEND", None)
        else:
            os.environ["VIV_EMBED_BACKEND"] = old_backend

    print("KNOWLEDGE_SEMANTIC_BACKEND_PASS cases=5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
