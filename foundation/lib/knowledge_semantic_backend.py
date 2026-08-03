"""Fail-closed local semantic backend adapter for Ollama ``viv-embed``."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Callable
import urllib.error
import urllib.request
from typing import Any


DEFAULT_ENDPOINT = "http://127.0.0.1:11434/api/embeddings"
DEFAULT_MODEL = "viv-embed:latest"
_LOCAL_ENCODER: Callable[[str], list[float]] | None = None
_LOCAL_ENCODER_PATH: str | None = None


def _protocol_for_endpoint(endpoint: str) -> str:
    configured = os.environ.get("VIV_EMBED_PROTOCOL", "auto").strip().lower()
    if configured in {"ollama", "openai"}:
        return configured
    return "openai" if "/v1/embeddings" in endpoint.lower() else "ollama"


def _local_model_path() -> Path:
    raw = os.environ.get("VIV_EMBED_MODEL_PATH", "").strip()
    if not raw:
        raise ValueError("local_embedding_model_path_missing")
    path = Path(raw).expanduser()
    if not path.is_dir():
        raise ValueError("local_embedding_model_path_missing")
    return path


def _local_embedding(text: str) -> list[float]:
    """Generate a CPU-local sentence embedding from an explicit HF model path."""
    global _LOCAL_ENCODER, _LOCAL_ENCODER_PATH
    path = _local_model_path()
    path_key = str(path.resolve())
    if _LOCAL_ENCODER is None or _LOCAL_ENCODER_PATH != path_key:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise ValueError("local_embedding_dependencies_missing") from exc
        tokenizer = AutoTokenizer.from_pretrained(
            path_key, local_files_only=True, trust_remote_code=False
        )
        model = AutoModel.from_pretrained(
            path_key, local_files_only=True, trust_remote_code=False
        ).to("cpu").eval()

        def encode(value: str) -> list[float]:
            inputs = tokenizer(
                [str(value or "")[:12000]],
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            with torch.inference_mode():
                hidden = model(**inputs).last_hidden_state
                mask = inputs["attention_mask"].unsqueeze(-1)
                pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1)
                vector = torch.nn.functional.normalize(pooled, dim=-1)[0]
            values = [float(item) for item in vector.tolist()]
            if not values or not all(math.isfinite(item) for item in values):
                raise ValueError("local_embedding_vector_invalid")
            return values

        _LOCAL_ENCODER = encode
        _LOCAL_ENCODER_PATH = path_key
    return _LOCAL_ENCODER(str(text or ""))


def _post_embedding(text: str, *, endpoint: str, model: str, timeout_s: float) -> list[float]:
    protocol = _protocol_for_endpoint(endpoint)
    if protocol == "openai":
        body_payload = {"model": model, "input": str(text or "")[:12000]}
    else:
        body_payload = {"model": model, "prompt": str(text or "")[:12000]}
    body = json.dumps(body_payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=max(0.5, float(timeout_s))) as response:
        payload = json.loads(response.read(8_000_000).decode("utf-8", errors="replace"))
    if protocol == "openai":
        data = payload.get("data") if isinstance(payload, dict) else None
        vector = data[0].get("embedding") if isinstance(data, list) and data and isinstance(data[0], dict) else None
    else:
        vector = payload.get("embedding") if isinstance(payload, dict) else None
    if not isinstance(vector, list) or not vector:
        raise ValueError("embedding_vector_missing")
    values = [float(value) for value in vector]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("embedding_vector_nonfinite")
    return values


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        raise ValueError("embedding_dimension_mismatch")
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise ValueError("zero_norm_embedding")
    return round(max(-1.0, min(1.0, dot / (left_norm * right_norm))), 4)


def semantic_compare(left: str, right: str, *, timeout_s: float = 8.0) -> dict[str, Any]:
    """Compare two texts through the local Ollama embedding API.

    Any transport, model, schema, or numeric failure is returned as
    ``INCONCLUSIVE``. No lexical or language-model fallback occurs here.
    """
    backend = os.environ.get("VIV_EMBED_BACKEND", "ollama").strip().lower()
    endpoint = os.environ.get("VIV_EMBED_ENDPOINT", DEFAULT_ENDPOINT)
    model = os.environ.get("VIV_EMBED_MODEL", DEFAULT_MODEL)
    protocol = _protocol_for_endpoint(endpoint)
    backend_name = "huggingface_local" if backend == "hf_local" else (
        "openai_compatible_embedding" if protocol == "openai" else "ollama_viv_embed"
    )
    try:
        if backend == "hf_local":
            left_vector = _local_embedding(left)
            right_vector = _local_embedding(right)
        else:
            left_vector = _post_embedding(left, endpoint=endpoint, model=model, timeout_s=timeout_s)
            right_vector = _post_embedding(right, endpoint=endpoint, model=model, timeout_s=timeout_s)
        return {
            "ok": True,
            "state": "SEMANTIC_SCORE",
            "score": cosine_similarity(left_vector, right_vector),
            "backend": backend_name,
            "model": os.environ.get("VIV_EMBED_MODEL_PATH") if backend == "hf_local" else model,
            "dimensions": len(left_vector),
        }
    except (ImportError, OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError, urllib.error.URLError) as exc:
        return {
            "ok": False,
            "state": "INCONCLUSIVE",
            "backend": backend_name,
            "model": os.environ.get("VIV_EMBED_MODEL_PATH") if backend == "hf_local" else model,
            "error": f"{type(exc).__name__}:{exc}",
        }
