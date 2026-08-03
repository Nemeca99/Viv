"""Local stub OpenAI-compatible voice server — pipeline proof without GPU/weights."""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


def _facts_summary(user_content: str) -> str:
    """Deterministic translator: turn packet JSON / text into a spoken line."""
    try:
        data = json.loads(user_content)
    except (json.JSONDecodeError, TypeError):
        text = (user_content or "").strip()
        return text[:400] if text else "No facts provided."

    status = data.get("status", "?")
    s_n = data.get("s_n", "?")
    facts = data.get("facts") or []
    mem = data.get("memory") or []
    query = data.get("query") or "state"
    fact_bits = "; ".join(str(f) for f in facts[:6])
    mem_bits = ""
    if mem:
        first = mem[0].get("text") if isinstance(mem[0], dict) else str(mem[0])
        mem_bits = f" Memory cue: {(first or '')[:120]}."
    return (
        f"Viv voice stub: query={query}. Status {status}, Master S_n {s_n}. "
        f"Facts: {fact_bits or 'none'}.{mem_bits}"
    )


class StubHandler(BaseHTTPRequestHandler):
    server_version = "VivVoiceStub/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("[stub] " + (fmt % args) + "\n")

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/v1/models", "/models"):
            self._json(
                200,
                {
                    "object": "list",
                    "data": [{"id": "viv-voice", "object": "model", "owned_by": "viv-stub"}],
                },
            )
            return
        if path in ("/health", "/"):
            self._json(200, {"ok": True, "stub": True})
            return
        self._json(404, {"error": "not_found", "path": path})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json(400, {"error": "invalid_json"})
            return

        if path not in ("/v1/chat/completions", "/chat/completions"):
            self._json(404, {"error": "not_found", "path": path})
            return

        messages = req.get("messages") or []
        user_content = ""
        for m in messages:
            if m.get("role") == "user":
                user_content = str(m.get("content") or "")
        spoken = _facts_summary(user_content)
        model = req.get("model") or "viv-voice"
        self._json(
            200,
            {
                "id": "stub-chatcmpl",
                "object": "chat.completion",
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": spoken},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": len(spoken.split()), "total_tokens": 0},
            },
        )


def serve(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), StubHandler)
    return httpd


def serve_background(host: str = "127.0.0.1", port: int = 8000) -> tuple[ThreadingHTTPServer, threading.Thread]:
    httpd = serve(host, port)
    t = threading.Thread(target=httpd.serve_forever, name="viv-voice-stub", daemon=True)
    t.start()
    return httpd, t


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Viv voice stub server (no GPU)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args(argv)
    httpd = serve(args.host, args.port)
    print(f"viv voice stub listening on http://{args.host}:{args.port}/v1", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstub stopped", flush=True)
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
