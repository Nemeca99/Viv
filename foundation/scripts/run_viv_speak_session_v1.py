#!/usr/bin/env python3
"""Bounded Viv speak session — skeleton→live bridge (text mouth first).

Default is --dry-run: prove status + intent packet + mouth envelope +
deterministic CPU render + honest STT/TTS stubs. Never starts full AIOS.

--live requires an explicit flag and runs one bounded voice_core.speak turn
(text mouth via Ollama/Qwen or deterministic fallback). Mic listen / TTS
audio remain stubbed until a later Codex pass.

Examples:

    L:\\Continue\\.venv\\Scripts\\python.exe foundation\\scripts\\run_viv_speak_session_v1.py
    L:\\Continue\\.venv\\Scripts\\python.exe foundation\\scripts\\run_viv_speak_session_v1.py --dry-run
    L:\\Continue\\.venv\\Scripts\\python.exe foundation\\scripts\\run_viv_speak_session_v1.py --live --text "hello Viv"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
VIV = FOUNDATION.parent
RECEIPTS_ROOT = FOUNDATION / "artifacts" / "auto" / "viv_speak_session"
SCHEMA_VERSION = "viv_speak_session_receipt_v1"
DEFAULT_TEXT = "hello Viv — one scripted turn"
PYTHON = Path(r"L:\Continue\.venv\Scripts\python.exe")

for _p in (str(FOUNDATION), str(VIV)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _utc_stamp() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond // 1000:03d}Z"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_receipt(stamp: str, payload: dict[str, Any]) -> Path:
    out_dir = RECEIPTS_ROOT / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "RECEIPT.json"
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    latest = {
        "schema_version": SCHEMA_VERSION,
        "stamp": stamp,
        "receipt": str(path).replace("\\", "/"),
        "mode": payload.get("mode"),
        "status": payload.get("status"),
        "ok": payload.get("ok"),
        "at": _utc_now(),
    }
    (RECEIPTS_ROOT / "LATEST.json").write_text(
        json.dumps(latest, indent=2) + "\n", encoding="utf-8"
    )
    return path


def _audio_stubs() -> dict[str, Any]:
    """Honest vacant slots — no mic listen / TTS audio path in tree yet."""
    return {
        "stt": {
            "status": "STUB",
            "wired": False,
            "note": "No microphone / Whisper / speech_recognition listen loop in Viv tree.",
        },
        "tts": {
            "status": "STUB",
            "wired": False,
            "note": "No pyttsx3 / SAPI / edge_tts audio render; mouth is text-out today.",
        },
        "listen_loop": {
            "status": "STUB",
            "wired": False,
            "note": "Operator talk path historically = CLI text via voice_main speak / model_main speak.",
        },
    }


def _dry_run(text: str) -> dict[str, Any]:
    from lib.cpu_mouth_contract import build_envelope_from_packet
    from voice_core.intent_packet import build_intent_packet, deterministic_speak
    from voice_core.runtime_contract import finalize_draft
    from voice_core.speak import speak_status

    steps: list[dict[str, Any]] = []
    t0 = time.perf_counter()

    status = speak_status()
    steps.append(
        {
            "id": "speak_status",
            "ok": bool(status.get("ok")),
            "reachable": bool(status.get("reachable")),
            "backend": status.get("backend"),
            "served_name": status.get("served_name"),
            "silent": status.get("silent"),
        }
    )

    packet = build_intent_packet(query=text, mode="converse", memory_top=1)
    steps.append(
        {
            "id": "intent_packet",
            "ok": True,
            "s_n": packet.get("s_n"),
            "mode": packet.get("mode"),
            "status": packet.get("status"),
            "facts_n": len(packet.get("facts") or []),
            "has_tagged_packet": bool(packet.get("tagged_packet")),
        }
    )

    envelope = build_envelope_from_packet(packet, query=text)
    steps.append(
        {
            "id": "mouth_envelope",
            "ok": True,
            "keys": sorted(list(envelope.keys()))[:12],
        }
    )

    raw = deterministic_speak(packet)
    finalized = finalize_draft(
        query=text,
        packet=packet,
        raw_text=raw,
        voice_source="deterministic_dry_run",
        cpu_fallback=deterministic_speak,
        renderer_retry=None,
    )
    accepted = bool((finalized.get("render_contract") or {}).get("accepted", True))
    out_text = str(finalized.get("text") or "")
    steps.append(
        {
            "id": "mouth_finalize_deterministic",
            "ok": bool(out_text.strip()),
            "accepted": accepted,
            "voice_source": finalized.get("voice_source"),
            "chars": len(out_text),
            "text_preview": out_text[:160],
            "security_out": "deferred_to_live_triad_emit",
            "note": "Dry-run skips triad emit / Security OUT network path; contracts only.",
        }
    )

    audio = _audio_stubs()
    steps.append({"id": "audio_stubs", "ok": True, **audio})

    elapsed = round(time.perf_counter() - t0, 3)
    mouth_ok = all(bool(s.get("ok")) for s in steps if s["id"] != "audio_stubs")
    ollama_up = bool(status.get("reachable")) and not bool(status.get("silent"))

    if mouth_ok and ollama_up:
        readiness = "TEXT_MOUTH_LIVE_READY"
        overall = "SKELETON_ONLY"
        detail = (
            "Text mouth endpoint reachable; dry-run contracts PASS. "
            "Audio STT/TTS listen loop still STUB — not LIVE_READY for speak/listen."
        )
    elif mouth_ok:
        readiness = "TEXT_MOUTH_OFFLINE_DETERMINISTIC"
        overall = "SKELETON_ONLY"
        detail = (
            "Contracts + deterministic CPU mouth PASS; Ollama/Qwen not reachable. "
            "Audio STT/TTS still STUB."
        )
    else:
        readiness = "BLOCKED_ON_MOUTH_CONTRACT"
        overall = "BLOCKED_ON_MOUTH_CONTRACT"
        detail = "Dry-run mouth/intent path failed — fix before --live."

    return {
        "ok": mouth_ok,
        "mode": "dry_run",
        "status": overall,
        "readiness": readiness,
        "detail": detail,
        "elapsed_s": elapsed,
        "query": text,
        "aios_started": False,
        "gpu_long": False,
        "steps": steps,
        "audio": audio,
        "speak_status": status,
        "text_preview": out_text[:240],
    }


def _live(text: str, max_tokens: int) -> dict[str, Any]:
    from voice_core.speak import speak, speak_status

    steps: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    status = speak_status()
    steps.append(
        {
            "id": "speak_status",
            "ok": bool(status.get("ok")),
            "reachable": bool(status.get("reachable")),
            "backend": status.get("backend"),
            "served_name": status.get("served_name"),
        }
    )

    out = speak(text, memory_top=1, max_tokens=max_tokens, mode="converse")
    steps.append(
        {
            "id": "live_speak_turn",
            "ok": bool(out.get("ok")) and not bool(out.get("blocked")),
            "silent": out.get("silent"),
            "blocked": out.get("blocked"),
            "voice_source": out.get("voice_source"),
            "chars": len(str(out.get("text") or "")),
            "text_preview": str(out.get("text") or "")[:160],
            "egress_allowed": bool((out.get("egress") or {}).get("allowed", True)),
        }
    )

    audio = _audio_stubs()
    steps.append({"id": "audio_stubs", "ok": True, **audio})
    elapsed = round(time.perf_counter() - t0, 3)
    turn_ok = bool(out.get("ok")) and not bool(out.get("blocked")) and bool(str(out.get("text") or "").strip())

    if turn_ok and bool(status.get("reachable")):
        readiness = "TEXT_MOUTH_LIVE"
        overall = "SKELETON_ONLY"
        detail = (
            "One live text speak turn completed (intent→mouth→Security OUT). "
            "STT/TTS audio still STUB — operator hear/speak loop not complete."
        )
    elif turn_ok:
        readiness = "TEXT_MOUTH_DETERMINISTIC_LIVE"
        overall = "SKELETON_ONLY"
        detail = "Speak returned deterministic/offline text through Security path; GPU mouth offline."
    else:
        readiness = "BLOCKED_ON_LIVE_SPEAK"
        overall = "BLOCKED_ON_LIVE_SPEAK"
        detail = "Live speak turn failed or blocked."

    return {
        "ok": turn_ok,
        "mode": "live",
        "status": overall,
        "readiness": readiness,
        "detail": detail,
        "elapsed_s": elapsed,
        "query": text,
        "aios_started": False,
        "gpu_long": False,
        "steps": steps,
        "audio": audio,
        "speak_status": status,
        "speak_result": {
            "ok": out.get("ok"),
            "silent": out.get("silent"),
            "blocked": out.get("blocked"),
            "voice_source": out.get("voice_source"),
            "text": out.get("text"),
            "events_path": out.get("events_path"),
        },
        "text_preview": str(out.get("text") or "")[:240],
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_viv_speak_session_v1",
        description="Bounded Viv speak session (dry-run default; --live explicit)",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Prove status+packet+mouth contracts without live GPU speak (default)",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Run one bounded live text speak turn (explicit)",
    )
    p.add_argument("--text", default=DEFAULT_TEXT, help="Scripted operator turn text")
    p.add_argument("--max-tokens", type=int, default=64, help="Live speak max tokens")
    p.add_argument(
        "--print-receipt",
        action="store_true",
        help="Also print full receipt JSON to stdout",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    stamp = _utc_stamp()
    live = bool(args.live)
    mode = "live" if live else "dry_run"

    try:
        body = _live(args.text, args.max_tokens) if live else _dry_run(args.text)
    except Exception as exc:  # noqa: BLE001 — always write failure receipt
        body = {
            "ok": False,
            "mode": mode,
            "status": "BLOCKED_ON_EXCEPTION",
            "readiness": "BLOCKED_ON_EXCEPTION",
            "detail": str(exc),
            "traceback": traceback.format_exc(limit=8),
            "aios_started": False,
            "gpu_long": False,
            "query": args.text,
            "audio": _audio_stubs(),
        }

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "stamp": stamp,
        "timestamp": _utc_now(),
        "workspace": str(VIV).replace("\\", "/"),
        "python": str(PYTHON if PYTHON.is_file() else sys.executable).replace("\\", "/"),
        "script": str(Path(__file__).resolve()).replace("\\", "/"),
        "goal": "Speak with Viv for real by end of 2026-08-08",
        "speak_tomorrow": str(
            (FOUNDATION / "artifacts" / "auto" / "wake_finish" / "SPEAK_TOMORROW.md")
        ).replace("\\", "/"),
        **body,
    }
    path = _write_receipt(stamp, receipt)
    summary = {
        "ok": receipt.get("ok"),
        "mode": receipt.get("mode"),
        "status": receipt.get("status"),
        "readiness": receipt.get("readiness"),
        "elapsed_s": receipt.get("elapsed_s"),
        "text_preview": receipt.get("text_preview"),
        "receipt": str(path).replace("\\", "/"),
        "detail": receipt.get("detail"),
    }
    print(json.dumps(summary, indent=2, default=str))
    if args.print_receipt:
        print(json.dumps(receipt, indent=2, default=str))
    return 0 if receipt.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
