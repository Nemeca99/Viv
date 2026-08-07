#!/usr/bin/env python3
"""Bounded Viv speak session — text-first skeleton→live bridge.

Default --dry-run: status + intent + mouth envelope + deterministic CPU
render + security observe + uml_invoke HOLD. No audio write. <60s. No AIOS.

--live --text: one voice_core.speak turn (Ollama/Qwen or deterministic).
Primary success = non-empty reply text in receipt. MP3 = optional SKIP
(no TTS deps required). No mic / camera / STT.

Examples:

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
    """Mic/camera out of scope; MP3 optional SKIP — text is the milestone."""
    return {
        "stt": {
            "status": "OUT_OF_SCOPE",
            "wired": False,
            "note": "Operator has mic but STT is not tomorrow's path. Input = --text only.",
        },
        "tts_mp3": {
            "status": "SKIP",
            "wired": False,
            "note": "MP3-to-file is optional TODO; do not block text LIVE on TTS deps.",
        },
        "camera": {
            "status": "OUT_OF_SCOPE",
            "wired": False,
            "note": "Camera exists but vision is not part of speak prove-out.",
        },
        "input": {
            "status": "TEXT_ONLY",
            "wired": True,
            "note": "--text \"...\" is the only operator input for this session.",
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
    """Text is primary. TEXT_LIVE_READY when a real reply exists; MP3 stays SKIP."""
    if not mouth_ok:
        return {
            "operator_verdict": "BLOCKED",
            "text_verdict": "BLOCKED",
            "mp3_verdict": "SKIP",
        }
    if ollama_up:
        return {
            "operator_verdict": "TEXT_LIVE_READY",
            "text_verdict": "TEXT_LIVE_READY",
            "mp3_verdict": "SKIP",
        }
    return {
        "operator_verdict": "TEXT_LIVE_READY",
        "text_verdict": "TEXT_LIVE_READY_DETERMINISTIC",
        "mp3_verdict": "SKIP",
        "note": "Deterministic/offline mouth still counts as text prove-out; start Ollama for GPU quality.",
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
        overall = "TEXT_PATH_READY"
        detail = (
            "Dry-run PASS; Ollama reachable. Next: --live --text for TEXT_LIVE_READY. "
            "MP3 SKIP. Mic/camera OUT_OF_SCOPE."
        )
    elif mouth_ok:
        readiness = "TEXT_MOUTH_OFFLINE_DETERMINISTIC"
        overall = "TEXT_PATH_READY"
        detail = (
            "Dry-run PASS offline (deterministic). Start Ollama for GPU mouth quality; "
            "still ready for --live text prove-out. MP3 SKIP."
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
        "mp3_path": None,
        "mp3_status": "SKIP",
        "aios_started": False,
        "gpu_long": False,
        "leftover_servers": False,
        "vacant_bus": ["uml_invoke"],
        "steps": steps,
        "audio": audio,
        "speak_status": status,
        "text_preview": out_text[:240],
    }


def _preflight() -> dict[str, Any]:
    """Check model presence + identity router + finalize path BEFORE live converse."""
    from lib.cpu_identity_router import route_identity_query
    from voice_core.intent_packet import build_intent_packet, deterministic_speak
    from voice_core.runtime_contract import finalize_draft
    from voice_core.speak import speak_status

    steps: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    status = speak_status()
    served_present = bool(status.get("served_present"))
    steps.append(
        {
            "id": "speak_status",
            "ok": bool(status.get("ok")),
            "reachable": bool(status.get("reachable")),
            "served_name": status.get("served_name"),
            "served_present": served_present,
            "converse_gate": status.get("converse_gate"),
            "model_ids": (status.get("detail") or {}).get("model_ids"),
        }
    )

    probes = (
        "Who are you?",
        "What is your tone?",
        "hello Viv",
        "What is UML responsible for?",
        "What are you doing right now?",
    )
    router_ok = True
    finalize_ok = True
    probe_rows: list[dict[str, Any]] = []
    for q in probes:
        routed = route_identity_query(q)
        auth = ""
        routed_ok = (
            isinstance(routed, dict)
            and routed.get("ok")
            and str(routed.get("state") or "") == "ROUTED"
        )
        if routed_ok:
            auth = str(routed.get("authorized_text") or "").strip()
        else:
            router_ok = False
        packet = build_intent_packet(query=q, mode="converse", memory_top=1)
        det = deterministic_speak(packet)
        finalized = finalize_draft(
            query=q,
            packet=packet,
            raw_text=det,
            voice_source="preflight_deterministic",
            cpu_fallback=deterministic_speak,
            renderer_retry=None,
        )
        out = str(finalized.get("text") or "").strip()
        evidence_collapse = "cannot verify an answer from the current verified evidence" in out.casefold()
        soft_template = out.casefold().startswith("i'm here with you")
        # Exact match preferred; accept non-empty routed doctrine that survived finalize
        # without evidence collapse / soft template (acronym repair may lightly rewrite).
        match = bool(auth) and out == auth
        doctrine_ok = (
            routed_ok
            and bool(out)
            and not evidence_collapse
            and not soft_template
            and (match or (auth[:48].casefold() in out.casefold()))
        )
        if not doctrine_ok:
            finalize_ok = False
        probe_rows.append(
            {
                "query": q,
                "router_ok": routed_ok,
                "intent_id": (routed or {}).get("intent_id") if isinstance(routed, dict) else None,
                "authorized_text": auth[:160],
                "deterministic_text": det[:160],
                "finalized_text": out[:160],
                "voice_source": finalized.get("voice_source"),
                "match_authorized": match,
                "doctrine_ok": doctrine_ok,
                "evidence_collapse": evidence_collapse,
            }
        )
    steps.append({"id": "identity_router_probes", "ok": router_ok, "probes": probe_rows})
    steps.append(
        {
            "id": "finalize_identity_path",
            "ok": finalize_ok,
            "note": "Authorized identity text must survive finalize_draft (no evidence collapse).",
        }
    )

    converse_ready = bool(served_present and router_ok and finalize_ok)
    pipe_only = bool(router_ok and finalize_ok and not served_present)
    if converse_ready:
        readiness = "CONVERSE_READY"
        detail = "Model present + identity anchors finalize clean. Safe for controlled --live probes."
    elif pipe_only:
        readiness = "PIPE_ONLY_IDENTITY_CPU"
        detail = (
            "Identity CPU path OK but configured Ollama model missing/mismatched. "
            "Do not claim GPU converse-ready."
        )
    else:
        readiness = "NOT_CONVERSE_READY"
        detail = "Preflight failed — fix model name and/or identity finalize before --live converse."

    elapsed = round(time.perf_counter() - t0, 3)
    return {
        "ok": converse_ready or pipe_only,
        "mode": "preflight",
        "status": readiness,
        "readiness": readiness,
        "operator_verdict": readiness,
        "text_verdict": readiness,
        "mp3_verdict": "SKIP",
        "detail": detail,
        "elapsed_s": elapsed,
        "served_present": served_present,
        "router_ok": router_ok,
        "finalize_ok": finalize_ok,
        "converse_ready": converse_ready,
        "query": None,
        "mp3_path": None,
        "mp3_status": "SKIP",
        "aios_started": False,
        "gpu_long": False,
        "leftover_servers": False,
        "vacant_bus": ["uml_invoke"],
        "steps": steps,
        "probes": probe_rows,
        "speak_status": status,
        "text_preview": (probe_rows[0]["finalized_text"] if probe_rows else ""),
    }


def _live(text: str, max_tokens: int, *, stamp: str) -> dict[str, Any]:
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
            "served_present": status.get("served_present"),
            "converse_gate": status.get("converse_gate"),
        }
    )

    out = speak(text, memory_top=1, max_tokens=max_tokens, mode="converse")
    spoken = str(out.get("text") or "").strip()
    steps.append(
        {
            "id": "live_speak_turn",
            "ok": bool(out.get("ok")) and not bool(out.get("blocked")) and bool(spoken),
            "silent": out.get("silent"),
            "blocked": out.get("blocked"),
            "voice_source": out.get("voice_source"),
            "chars": len(spoken),
            "text_preview": spoken[:160],
            "egress_allowed": bool((out.get("egress") or {}).get("allowed", True)),
        }
    )

    steps.append(_security_observe())
    steps.append(_uml_invoke_hold())
    # MP3 is optional — never fail the text path for missing TTS deps.
    steps.append(
        {
            "id": "mp3_write",
            "ok": True,
            "status": "SKIP",
            "path": None,
            "note": "MP3 deferred; text reply is primary success. No TTS install required.",
        }
    )
    audio = _audio_stubs()
    steps.append({"id": "audio_policy", "ok": True, **audio})
    elapsed = round(time.perf_counter() - t0, 3)
    turn_ok = (
        bool(out.get("ok"))
        and not bool(out.get("blocked"))
        and bool(spoken)
    )
    ollama_up = bool(status.get("reachable")) and not bool(status.get("silent"))
    verdicts = _operator_verdict(mouth_ok=turn_ok, ollama_up=ollama_up)

    if turn_ok and ollama_up:
        readiness = "TEXT_LIVE_READY"
        overall = "TEXT_LIVE_READY"
        detail = (
            "TEXT_LIVE_READY: one live text speak turn (intent→mouth→Security OUT). "
            "MP3 SKIP. Mic/camera OUT_OF_SCOPE."
        )
    elif turn_ok:
        readiness = "TEXT_LIVE_READY_DETERMINISTIC"
        overall = "TEXT_LIVE_READY"
        detail = (
            "TEXT_LIVE_READY (deterministic): speak returned text through Security path; "
            "Ollama offline. MP3 SKIP."
        )
    else:
        readiness = "BLOCKED_ON_LIVE_SPEAK"
        overall = "BLOCKED_ON_LIVE_SPEAK"
        detail = "Live speak turn failed or blocked."
        verdicts = {
            "operator_verdict": "BLOCKED",
            "text_verdict": "BLOCKED",
            "mp3_verdict": "SKIP",
        }

    out_dir = RECEIPTS_ROOT / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    return {
        "ok": turn_ok,
        "mode": "live",
        "status": overall,
        "readiness": readiness,
        **verdicts,
        "detail": detail,
        "elapsed_s": elapsed,
        "query": text,
        "mp3_path": None,
        "mp3_status": "SKIP",
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
            "text": spoken,
            "events_path": out.get("events_path"),
        },
        "text_preview": spoken[:240],
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
        help="Prove status+packet+mouth contracts without live GPU speak (default if no mode flag)",
    )
    mode.add_argument(
        "--preflight",
        action="store_true",
        help="Gate check: Ollama model present + identity router/finalize (no casual converse)",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="One bounded live text speak turn; writes receipt (MP3 optional SKIP)",
    )
    p.add_argument(
        "--text",
        default=DEFAULT_TEXT,
        help="Operator input text (only input; no mic)",
    )
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
    preflight = bool(args.preflight)
    if live:
        mode = "live"
    elif preflight:
        mode = "preflight"
    else:
        mode = "dry_run"

    try:
        if live:
            body = _live(args.text, args.max_tokens, stamp=stamp)
        elif preflight:
            body = _preflight()
        else:
            body = _dry_run(args.text)
    except Exception as exc:  # noqa: BLE001 — always write failure receipt
        body = {
            "ok": False,
            "mode": mode,
            "status": "BLOCKED_ON_EXCEPTION",
            "readiness": "BLOCKED_ON_EXCEPTION",
            "operator_verdict": "BLOCKED",
            "detail": str(exc),
            "traceback": traceback.format_exc(limit=8),
            "aios_started": False,
            "gpu_long": False,
            "leftover_servers": False,
            "mp3_status": "SKIP",
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
        "goal": "Speak with Viv for real by end of 2026-08-08 (text-first)",
        "happy_path": str(
            (FOUNDATION / "artifacts" / "auto" / "wake_finish" / "OPERATOR_HAPPY_PATH.md")
        ).replace("\\", "/"),
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
        "operator_verdict": receipt.get("operator_verdict"),
        "text_verdict": receipt.get("text_verdict"),
        "mp3_status": receipt.get("mp3_status"),
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
