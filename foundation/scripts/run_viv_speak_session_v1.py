#!/usr/bin/env python3
"""Bounded Viv speak session — skeleton→live bridge (text mouth first).

Default is --dry-run: prove status + intent packet + mouth envelope +
deterministic CPU render + security observe + honest STT/TTS stubs +
uml_invoke HOLD. Never starts full AIOS. Offline dry-run must finish <60s.

--live requires an explicit flag and runs one bounded voice_core.speak turn
(text mouth via Ollama/Qwen or deterministic fallback). Mic listen / TTS
audio remain stubbed (BLOCKED) — text mouth is the 2026-08-08 milestone.

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
DRY_RUN_BUDGET_S = 60.0

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
    """Honest vacant slots — audio listen/hear still BLOCKED; text mouth is the milestone."""
    return {
        "stt": {
            "status": "BLOCKED_ON_STT",
            "wired": False,
            "note": "No microphone / Whisper / speech_recognition listen loop in Viv tree.",
        },
        "tts": {
            "status": "BLOCKED_ON_TTS",
            "wired": False,
            "note": "No pyttsx3 / SAPI / edge_tts audio render wired in session; mouth is text-out.",
        },
        "listen_loop": {
            "status": "STUB",
            "wired": False,
            "note": "Operator talk path = CLI text via voice_main / session --live (not mic).",
        },
    }


def _uml_invoke_hold() -> dict[str, Any]:
    """Vacant bus slot — never fake Nested-PEMDAS / UML authority."""
    return {
        "id": "uml_invoke",
        "ok": True,
        "status": "HOLD",
        "wired": False,
        "fill": "VACANT",
        "authority": False,
        "note": (
            "Bus slot uml_invoke deliberately vacant. "
            "Speak session does not call uml_engine / Nested-PEMDAS. "
            "Do not invent UML results here."
        ),
    }


def _security_observe() -> dict[str, Any]:
    """Cheap security IN/OUT observe if adapter present; never mutate."""
    try:
        from lib.aios_adapter_security import cpu_plan

        plan = cpu_plan()
        return {
            "id": "security_observe",
            "ok": True,
            "wired": True,
            "build_state": (plan or {}).get("build_state")
            or ((plan or {}).get("extra") or {}).get("status", {}).get("build_state"),
            "note": "Plan-only security adapter observe; dry-run does not triad-emit.",
        }
    except Exception as exc:  # noqa: BLE001 — soft path
        return {
            "id": "security_observe",
            "ok": True,
            "wired": False,
            "status": "UNAVAILABLE",
            "note": f"Security adapter not imported: {type(exc).__name__}",
        }


def _operator_verdict(*, mouth_ok: bool, ollama_up: bool) -> dict[str, str]:
    """ALMOST = text mouth path; BLOCKED = audio listen/hear; LIVE_READY reserved for both."""
    if not mouth_ok:
        return {
            "operator_verdict": "BLOCKED",
            "text_verdict": "BLOCKED",
            "audio_verdict": "BLOCKED",
        }
    text = "ALMOST" if ollama_up else "ALMOST_OFFLINE"
    return {
        "operator_verdict": "ALMOST",
        "text_verdict": text,
        "audio_verdict": "BLOCKED",
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
            "uml_request": "absent",
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

    steps.append(_security_observe())
    steps.append(_uml_invoke_hold())

    audio = _audio_stubs()
    steps.append({"id": "audio_stubs", "ok": True, **audio})

    elapsed = round(time.perf_counter() - t0, 3)
    budget_ok = elapsed < DRY_RUN_BUDGET_S
    core_ids = {
        "speak_status",
        "intent_packet",
        "mouth_envelope",
        "mouth_finalize_deterministic",
    }
    mouth_ok = all(bool(s.get("ok")) for s in steps if s.get("id") in core_ids) and budget_ok
    ollama_up = bool(status.get("reachable")) and not bool(status.get("silent"))
    verdicts = _operator_verdict(mouth_ok=mouth_ok, ollama_up=ollama_up)

    if not budget_ok:
        readiness = "BLOCKED_ON_TIMEOUT"
        overall = "BLOCKED_ON_TIMEOUT"
        detail = f"Dry-run exceeded {DRY_RUN_BUDGET_S:.0f}s budget ({elapsed}s) — fail closed."
    elif mouth_ok and ollama_up:
        readiness = "TEXT_MOUTH_LIVE_READY"
        overall = "SKELETON_ONLY"
        detail = (
            "ALMOST (text): mouth endpoint reachable; dry-run contracts PASS. "
            "BLOCKED (audio): STT/TTS still vacant — not LIVE_READY for speak/listen."
        )
    elif mouth_ok:
        readiness = "TEXT_MOUTH_OFFLINE_DETERMINISTIC"
        overall = "SKELETON_ONLY"
        detail = (
            "ALMOST_OFFLINE (text): contracts + deterministic CPU mouth PASS; Ollama down. "
            "BLOCKED (audio): STT/TTS still vacant."
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
        **verdicts,
        "detail": detail,
        "elapsed_s": elapsed,
        "budget_s": DRY_RUN_BUDGET_S,
        "budget_ok": budget_ok,
        "query": text,
        "aios_started": False,
        "gpu_long": False,
        "leftover_servers": False,
        "vacant_bus": ["uml_invoke"],
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

    steps.append(_uml_invoke_hold())
    audio = _audio_stubs()
    steps.append({"id": "audio_stubs", "ok": True, **audio})
    elapsed = round(time.perf_counter() - t0, 3)
    turn_ok = (
        bool(out.get("ok"))
        and not bool(out.get("blocked"))
        and bool(str(out.get("text") or "").strip())
    )
    ollama_up = bool(status.get("reachable")) and not bool(status.get("silent"))
    verdicts = _operator_verdict(mouth_ok=turn_ok, ollama_up=ollama_up)

    if turn_ok and ollama_up:
        readiness = "TEXT_MOUTH_LIVE"
        overall = "SKELETON_ONLY"
        detail = (
            "ALMOST (text): one live speak turn via intent→mouth→Security OUT. "
            "BLOCKED (audio): STT/TTS vacant — hear/listen loop not complete."
        )
    elif turn_ok:
        readiness = "TEXT_MOUTH_DETERMINISTIC_LIVE"
        overall = "SKELETON_ONLY"
        detail = (
            "ALMOST_OFFLINE (text): deterministic/offline speak through Security path. "
            "BLOCKED (audio): STT/TTS vacant."
        )
    else:
        readiness = "BLOCKED_ON_LIVE_SPEAK"
        overall = "BLOCKED_ON_LIVE_SPEAK"
        detail = "Live speak turn failed or blocked."
        verdicts = {
            "operator_verdict": "BLOCKED",
            "text_verdict": "BLOCKED",
            "audio_verdict": "BLOCKED",
        }

    return {
        "ok": turn_ok,
        "mode": "live",
        "status": overall,
        "readiness": readiness,
        **verdicts,
        "detail": detail,
        "elapsed_s": elapsed,
        "query": text,
        "aios_started": False,
        "gpu_long": False,
        "leftover_servers": False,
        "vacant_bus": ["uml_invoke"],
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
