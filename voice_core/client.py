"""OpenAI-compatible voice client — soft-fail when GPU/server is offline."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1] / "foundation"
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.model_config import load_config  # noqa: E402

DEFAULT_TIMEOUT_S = 60.0


def _voice_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    c = cfg or load_config()
    voice = dict(c.get("voice") or {})
    client = dict(c.get("aios_client") or {})
    host = voice.get("host", "127.0.0.1")
    port = int(voice.get("port", 8000))
    base = client.get("vllm_base_url") or f"http://{host}:{port}/v1"
    model = client.get("vllm_model") or voice.get("served_name") or "viv-voice"
    return {
        "host": host,
        "port": port,
        "base_url": str(base).rstrip("/"),
        "model": model,
        "served_name": voice.get("served_name") or model,
    }


def voice_endpoint(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    v = _voice_cfg(cfg)
    return {
        "base_url": v["base_url"],
        "chat_url": f"{v['base_url']}/chat/completions",
        "models_url": f"{v['base_url']}/models",
        "host": v["host"],
        "port": v["port"],
        "model": v["model"],
    }


def server_reachable(
    cfg: dict[str, Any] | None = None,
    *,
    timeout_s: float = 2.0,
) -> dict[str, Any]:
    ep = voice_endpoint(cfg)
    url = ep["models_url"]
    wanted = str(ep.get("model") or "").strip()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        model_ids: list[str] = []
        served_present = False
        try:
            payload = json.loads(body)
            model_ids = [str(m.get("id") or "") for m in (payload.get("data") or [])]
            served_present = any(
                mid == wanted
                or mid.startswith(wanted + ":")
                or mid.split(":", 1)[0] == wanted
                for mid in model_ids
                if mid
            )
        except (json.JSONDecodeError, TypeError, AttributeError):
            served_present = False
        return {
            "ok": True,
            "reachable": True,
            "url": url,
            "status": resp.status,
            "body_preview": body[:200],
            "served_name": wanted,
            "served_present": served_present,
            "model_ids": model_ids[:20],
        }
    except (urllib.error.URLError, TimeoutError, OSError) as ex:
        return {
            "ok": True,
            "reachable": False,
            "silent": True,
            "url": url,
            "error": str(ex),
            "served_name": wanted,
            "served_present": False,
            "model_ids": [],
        }


def speak_completion(
    messages: list[dict[str, str]],
    *,
    cfg: dict[str, Any] | None = None,
    max_tokens: int = 128,
    temperature: float = 0.6,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """POST chat/completions. Soft-fail: ok=True, silent=True when offline."""
    ep = voice_endpoint(cfg)
    url = ep["chat_url"]
    body = json.dumps(
        {
            "model": ep["model"],
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = ""
        choices = data.get("choices") or []
        if choices:
            text = str((choices[0].get("message") or {}).get("content") or "")
        out = {
            "ok": True,
            "silent": False,
            "text": text.strip(),
            "raw": data,
            "url": url,
            "model": ep["model"],
            "mode": "chat",
        }
        # Read-only energy accounting; never gates speak success
        try:
            import sys
            from pathlib import Path

            _found = Path(__file__).resolve().parents[1] / "foundation"
            if _found.is_dir() and str(_found) not in sys.path:
                sys.path.insert(0, str(_found))
            from lib.rid_electrical_ops_hook import maybe_record_from_speak_result

            out["accounting"] = maybe_record_from_speak_result(out)
        except Exception:  # noqa: BLE001
            out["accounting"] = {"ok": True, "accounted": False, "silent": True}
        return out
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError) as ex:
        return {
            "ok": True,
            "silent": True,
            "text": None,
            "error": str(ex),
            "url": url,
            "model": ep["model"],
            "mode": "chat",
        }


def speak_generate(
    prompt: str,
    *,
    cfg: dict[str, Any] | None = None,
    max_tokens: int = 128,
    temperature: float = 0.6,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Ollama /api/generate — preferred for BASE GGUFs (no chat template). Soft-fail silent."""
    c = cfg or load_config()
    voice = dict(c.get("voice") or {})
    host = voice.get("host", "127.0.0.1")
    port = int(voice.get("port", 11434))
    model = (c.get("aios_client") or {}).get("vllm_model") or voice.get("served_name") or "viv-voice"
    url = f"http://{host}:{port}/api/generate"
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": int(voice.get("max_model_len") or 2048),
            },
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = str(data.get("response") or "").strip()
        out = {
            "ok": True,
            "silent": False,
            "text": text,
            "raw": data,
            "url": url,
            "model": model,
            "mode": "generate",
        }
        # Read-only energy accounting; never gates speak success
        try:
            import sys
            from pathlib import Path

            _found = Path(__file__).resolve().parents[1] / "foundation"
            if _found.is_dir() and str(_found) not in sys.path:
                sys.path.insert(0, str(_found))
            from lib.rid_electrical_ops_hook import maybe_record_from_speak_result

            out["accounting"] = maybe_record_from_speak_result(out)
        except Exception:  # noqa: BLE001
            out["accounting"] = {"ok": True, "accounted": False, "silent": True}
        return out
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError) as ex:
        return {
            "ok": True,
            "silent": True,
            "text": None,
            "error": str(ex),
            "url": url,
            "model": model,
            "mode": "generate",
        }


def clean_base_output(text: str) -> str:
    """Strip common base-model markup garbage; keep first spoken paragraph."""
    import re

    t = text.strip()
    t = re.sub(r"</?output>", "", t, flags=re.I)
    t = re.sub(r"</?[^>]+>", "", t)
    # Internal prompt markers must never survive even when the model leaks
    # them mid-line rather than after a newline.
    for marker in (
        "INTERNAL mood hint",
        "CURRENT mood",
        "Current Architect message",
        "Facts for your answer:",
    ):
        pos = t.lower().find(marker.lower())
        if pos >= 0:
            t = t[:pos].rstrip()
    # Cut at second demo / leaked prompts
    for stop in (
        "\nTranslate facts",
        "\nSpoken report:",
        "\nTone:",
        "\nFacts:",
        "\nArchitect:",
        "\nINTERNAL mood hint",
        "\nCURRENT mood hint",
        "\nAnswer:",
    ):
        if stop in t:
            t = t.split(stop, 1)[0]
    lines = []
    for ln in t.splitlines():
        s = ln.strip()
        if not s or s in ("]}", "{", "}"):
            continue
        if s.startswith("- [") and "smoke" in s.lower():
            continue
        lines.append(s)
    out = " ".join(lines).strip()
    if out.lower().startswith("architect:"):
        out = out.split(":", 1)[1].strip()
    # One or two sentences max for clarity
    parts = re.split(r"(?<=[.!?])\s+", out)
    return " ".join(parts[:3]).strip()

