"""Speak path: intent packet → GPU/stub render → Security OUT → event log."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

_VIV = Path(__file__).resolve().parents[1]
_FOUNDATION = _VIV / "foundation"
for _p in (_VIV, _FOUNDATION):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.triad_kernel import (  # noqa: E402
    TriadContext,
    TriadDenied,
    TriadEnvelope,
    authorize_operation,
    emit,
    open_context,
)
from voice_core.client import (  # noqa: E402
    clean_base_output,
    server_reachable,
    speak_completion,
    speak_generate,
    voice_endpoint,
)
from voice_core.hf_lora import adapter_ready, generate as hf_lora_generate  # noqa: E402
from voice_core.intent_packet import (  # noqa: E402
    build_intent_packet,
    deterministic_speak,
    is_health_query,
    looks_like_speech,
)
from lib.aios_tagged_packet import verify_gpu_draft  # noqa: E402
from lib.cpu_mouth_contract import (  # noqa: E402
    build_envelope_from_packet,
    envelope_to_completion_prompt,
    envelope_to_messages,
)
from voice_core.acronym_registry import (  # noqa: E402
    validate_acronym_usage,
)
from voice_core.runtime_contract import finalize_draft  # noqa: E402
from lib.model_config import load_config  # noqa: E402

VOICE_EVENTS_PATH = AUTO_ARTIFACTS / "voice_events.jsonl"


def _log_voice_event(row: dict[str, Any]) -> Path:
    VOICE_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with VOICE_EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return VOICE_EVENTS_PATH


def _optional_carma_spoke_note(chars: int, silent: bool) -> None:
    """Append a short live note — never dump full blocked egress."""
    if silent or chars <= 0:
        return
    try:
        from memory_core.semantic_memory import append_live_note

        append_live_note(f"[live] spoke {chars} chars")
    except Exception:  # noqa: BLE001 — voice must not fail on memory soft note
        return


def speak_status() -> dict[str, Any]:
    ep = voice_endpoint()
    reach = server_reachable()
    lora = adapter_ready()
    cfg = load_config()
    voice = dict(cfg.get("voice") or {})
    gguf_st: dict[str, Any] = {}
    try:
        from voice_core.gguf_voice import status as gguf_status

        gguf_st = gguf_status(cfg)
    except Exception as exc:  # noqa: BLE001
        gguf_st = {"error": str(exc)}
    prefer_qwen = bool(voice.get("prefer_over_lora", True)) and str(voice.get("backend") or "").lower() in {
        "ollama",
        "llama_cpp",
        "gguf",
    }
    served_present = bool(reach.get("served_present"))
    return {
        "ok": True,
        "gpu_optional": True,
        "backend": voice.get("backend"),
        "served_name": voice.get("served_name") or ep.get("model"),
        "served_present": served_present,
        "prefer_over_lora": prefer_qwen,
        "lora_ready": lora,
        "gguf": gguf_st,
        "silent": (not prefer_qwen and not lora) and (not reach.get("reachable")),
        "reachable": bool(reach.get("reachable")) or lora or bool(gguf_st.get("gguf_ready")),
        "endpoint": ep,
        "events_path": str(VOICE_EVENTS_PATH).replace("\\", "/"),
        "detail": reach,
        "converse_gate": (
            "CONVERSE_MODEL_OK"
            if served_present
            else ("OLLAMA_UP_MODEL_MISSING" if reach.get("reachable") else "OLLAMA_DOWN")
        ),
    }


def _finalize_spoken(
    *,
    query: str,
    packet: dict[str, Any],
    raw_text: str,
    voice_source: str,
    model: str | None,
    s_n: float,
    triad_context: TriadContext,
    renderer_retry: Callable[[Mapping[str, Any]], str] | None = None,
) -> dict[str, Any]:
    finalized = finalize_draft(
        query=query,
        packet=packet,
        raw_text=raw_text,
        voice_source=voice_source,
        cpu_fallback=deterministic_speak,
        renderer_retry=renderer_retry,
    )
    raw_text = str(finalized["text"])
    voice_source = str(finalized["voice_source"])
    acronym_repair = dict(finalized["acronym_repair"])
    acronym_violations = validate_acronym_usage(raw_text)
    entity_decision = dict(finalized["entity_decision"])
    regenerated_for_acronym = bool(finalized["acronym_regenerated"])
    regenerated_for_entity = bool(finalized["entity_regenerated"])
    draft_verification = verify_gpu_draft(packet["tagged_packet"], raw_text) if packet.get("tagged_packet") else None
    if draft_verification is not None and draft_verification.status != "PASS":
        # Re-enter the strict CPU mouth contract after the legacy tagged
        # packet verifier rejects a draft.  The old path could otherwise
        # replace text with deterministic_speak and bypass the new envelope
        # validator on the way to triad egress.
        rechecked = finalize_draft(
            query=query,
            packet=packet,
            raw_text=deterministic_speak(packet),
            voice_source=f"{voice_source}_cpu_verified_fallback",
            cpu_fallback=deterministic_speak,
            renderer_retry=renderer_retry,
        )
        raw_text = str(rechecked["text"])
        voice_source = str(rechecked["voice_source"])
        acronym_repair = dict(rechecked["acronym_repair"])
        entity_decision = dict(rechecked["entity_decision"])
        regenerated_for_acronym = bool(rechecked["acronym_regenerated"])
        regenerated_for_entity = bool(rechecked["entity_regenerated"])
        finalized = rechecked
        draft_verification = verify_gpu_draft(packet["tagged_packet"], raw_text)
    contract_blocked = bool(
        finalized.get("render_contract")
        and not bool(finalized["render_contract"].get("accepted"))
    )
    if draft_verification is not None and draft_verification.status != "PASS":
        contract_blocked = True
    try:
        if contract_blocked:
            egress = {
                "allowed": False,
                "reason": "cpu_mouth_contract_or_tagged_packet_rejected",
                "evidence": {
                    "render_contract": finalized.get("render_contract"),
                    "tagged_packet_verification": draft_verification.to_dict() if draft_verification else None,
                },
            }
            blocked = True
            out_text = ""
        else:
            spoken, triad_receipt = emit(triad_context, raw_text)
            egress = triad_receipt.to_dict()
            blocked = not triad_receipt.allowed
            out_text = str(spoken or "")
    except TriadDenied as exc:
        egress = {"allowed": False, "reason": exc.reason, "evidence": exc.evidence}
        blocked = True
        out_text = ""
    chars = len(out_text) if not blocked else 0
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": "speak",
        "ok": True,
        "silent": False,
        "s_n": s_n,
        "query": query,
        "chars": len(out_text),
        "blocked": blocked,
        "model": model,
        "voice_source": voice_source,
        "acronym_contract": {
            "pass": not validate_acronym_usage(out_text if not blocked else raw_text),
            "violations": validate_acronym_usage(out_text if not blocked else raw_text),
            "regenerated": regenerated_for_acronym,
            "repair": acronym_repair,
            "entity_decision": entity_decision,
            "entity_regenerated": regenerated_for_entity,
        },
        "tagged_packet_verification": draft_verification.to_dict() if draft_verification else None,
        "render_contract": finalized.get("render_contract"),
        "text_preview": (out_text[:160] if not blocked else "[blocked]"),
    }
    _log_voice_event(row)
    if not blocked:
        _optional_carma_spoke_note(chars, silent=False)
        try:
            from lib.voice_gold import append_gold_speak

            append_gold_speak(
                query=query,
                text=out_text,
                s_n=s_n,
                status=str(packet.get("status") or ""),
                voice_source=voice_source,
                packet=packet,
            )
        except Exception:  # noqa: BLE001
            pass
    return {
        "ok": True,
        "silent": False,
        "text": out_text,
        "blocked": blocked,
        "voice_source": voice_source,
        "packet": packet,
        "egress": egress,
        "render_contract": finalized.get("render_contract"),
        "events_path": str(VOICE_EVENTS_PATH).replace("\\", "/"),
    }


def _stamp_measured_s_n(text: str, s_n: float, *, require: bool = True) -> str:
    """CPU stamp for status/report mode. Converse mode skips forced append."""
    import re

    t = (text or "").strip()
    if not require:
        # If model mentioned a wrong S_n, correct it; otherwise leave personal prose alone
        low = t.lower()
        target = f"{s_n:.4f}"
        if re.search(r"(?:master\s+)?s_n", low):
            t2 = re.sub(
                r"((?:Master\s+)?S_n\s*(?:is|=|:)?\s*)(0?\.\d{2,4}|[01]\.\d{2,4})",
                rf"\g<1>{target}",
                t,
                count=1,
                flags=re.I,
            )
            return t2
        return t
    low = t.lower()
    target = f"{s_n:.4f}"
    if re.search(r"(?:master\s+)?s_n", low) and target in t:
        return t
    if re.search(r"(?:master\s+)?s_n", low):
        t2 = re.sub(
            r"((?:Master\s+)?S_n\s*(?:is|=|:)?\s*)(0?\.\d{2,4}|[01]\.\d{2,4})",
            rf"\g<1>{target}",
            t,
            count=1,
            flags=re.I,
        )
        if t2 != t:
            return t2
    return f"{t} Master S_n is {target}.".strip()


def _try_ollama_or_gguf(
    packet: dict[str, Any],
    *,
    query: str,
    render_envelope: dict[str, Any],
    max_tokens: int,
    cfg: dict[str, Any],
    triad_context: TriadContext,
) -> dict[str, Any] | None:
    """Prefer Qwen GGUF via Ollama (or llama.cpp) for speak-only. Returns None to fall through."""
    voice = dict(cfg.get("voice") or {})
    backend = str(voice.get("backend") or "").lower()
    s_n = float(packet.get("s_n") or 0.0)
    mode = str(packet.get("mode") or "translate").lower()
    converse = mode in {"converse", "talk", "ide"}
    require_sn = not converse

    if backend in {"llama_cpp", "gguf"}:
        from voice_core.gguf_voice import chat as gguf_chat

        messages = envelope_to_messages(render_envelope)
        completion = gguf_chat(messages, max_tokens=max_tokens, temperature=0.35, cfg=cfg)
        raw_text = str(completion.get("text") or "")
        if completion.get("silent") or len(raw_text.strip()) < 12:
            return None
        raw_text = _stamp_measured_s_n(clean_base_output(raw_text), s_n, require=require_sn)
        if not looks_like_speech(raw_text, measured_s_n=s_n, require_s_n=require_sn):
            return None

        def retry_renderer(envelope: Mapping[str, Any]) -> str:
            retry = gguf_chat(
                envelope_to_messages(envelope),
                max_tokens=max_tokens,
                temperature=0.20,
                cfg=cfg,
            )
            if retry.get("silent"):
                return ""
            return clean_base_output(str(retry.get("text") or ""))

        return _finalize_spoken(
            query=query,
            packet=packet,
            raw_text=raw_text,
            voice_source="llama_cpp",
            model=completion.get("model"),
            s_n=s_n,
            triad_context=triad_context,
            renderer_retry=retry_renderer,
        )

    if backend != "ollama":
        return None

    reach = server_reachable(cfg)
    if not reach.get("reachable"):
        return None

    raw_base = bool(voice.get("raw_base")) or str(voice.get("prompt_mode") or "").lower() == "completion"
    if raw_base:
        # Raw base models: completion only — no chat/Instruct template
        prompt = envelope_to_completion_prompt(render_envelope)
        completion = speak_generate(
            prompt, cfg=cfg, max_tokens=max_tokens, temperature=0.5 if converse else 0.35
        )
        raw_text = str(completion.get("text") or "")
        voice_source = "ollama_raw_base"

        def retry_renderer(envelope: Mapping[str, Any]) -> str:
            retry = speak_generate(
                envelope_to_completion_prompt(envelope),
                cfg=cfg,
                max_tokens=max_tokens,
                temperature=0.35 if converse else 0.25,
            )
            if retry.get("silent"):
                return ""
            return clean_base_output(str(retry.get("text") or ""))

    else:
        messages = envelope_to_messages(render_envelope)
        completion = speak_completion(
            messages, max_tokens=max_tokens, cfg=cfg, temperature=0.45 if converse else 0.35
        )
        raw_text = str(completion.get("text") or "")
        if completion.get("silent") or len(raw_text.strip()) < 12:
            prompt = envelope_to_completion_prompt(render_envelope)
            completion = speak_generate(
                prompt, cfg=cfg, max_tokens=max_tokens, temperature=0.45 if converse else 0.35
            )
            raw_text = str(completion.get("text") or "")
        voice_source = "ollama_qwen"

        def retry_renderer(envelope: Mapping[str, Any]) -> str:
            retry = speak_completion(
                envelope_to_messages(envelope),
                max_tokens=max_tokens,
                cfg=cfg,
                temperature=0.30 if converse else 0.25,
            )
            if retry.get("silent"):
                return ""
            return clean_base_output(str(retry.get("text") or ""))
    raw_text = clean_base_output(raw_text)
    if len(raw_text.strip()) < 12:
        return None
    raw_text = _stamp_measured_s_n(raw_text, s_n, require=require_sn)
    if not looks_like_speech(raw_text, measured_s_n=s_n, require_s_n=require_sn):
        return None
    return _finalize_spoken(
        query=query,
        packet=packet,
        raw_text=raw_text,
        voice_source=voice_source,
        model=completion.get("model") or voice.get("served_name"),
        s_n=s_n,
        triad_context=triad_context,
        renderer_retry=retry_renderer,
    )


def speak(
    query: str = "state summary",
    *,
    mode: str | None = None,
    facts: list[str] | None = None,
    knowledge_query: str | None = None,
    knowledge_mode: str = "local",
    wikipedia_title: str | None = None,
    include_legacy_wikipedia: bool = False,
    resolve_legacy_redirects: bool = False,
    memory_top: int = 3,
    max_tokens: int = 128,
    force_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Full speak path.
    Prefer configured Qwen GGUF (Ollama/llama.cpp) for voice.
    Offline → deterministic CPU template (not an error).
    """
    requested_mode = mode
    if requested_mode is None and not force_packet:
        normalized_query = (query or "").strip().lower()
        requested_mode = (
            "health"
            if is_health_query(query)
            else "translate"
            if normalized_query in {"state summary", "status summary", "status report"}
            else "converse"
        )
    enriched_facts = list(facts) if facts is not None else None
    qfold = (query or "").casefold()
    if force_packet is None and any(
        term in qfold
        for term in (
            "active",
            "running",
            "systems",
            "uml",
            "prove",
            "current state",
            "doing right now",
        )
    ):
        try:
            from lib.aios_skeleton_bus import default_bus

            wire = default_bus().wire_status()
            enriched_facts = list(enriched_facts or [])
            pct = wire.get("pct_filled")
            vacant = list(wire.get("vacant_for_compute_core") or [])
            bound = [
                str(r.get("slot"))
                for r in (wire.get("rows") or [])
                if str(r.get("fill") or "") in {"BOUND", "PARTIAL"}
            ]
            if pct is not None:
                enriched_facts.append(f"skeleton_bus_filled_pct={pct}")
            if bound:
                enriched_facts.append(
                    "skeleton_bus_bound=" + ",".join(bound[:12])
                )
            if vacant:
                enriched_facts.append(
                    "skeleton_bus_vacant=" + ",".join(str(x) for x in vacant[:8])
                )
        except Exception:  # noqa: BLE001 — speak must not die on bus probe
            pass
    packet = force_packet or build_intent_packet(
        query=query,
        facts=enriched_facts,
        knowledge_query=knowledge_query,
        knowledge_mode=knowledge_mode,
        wikipedia_title=wikipedia_title,
        include_legacy_wikipedia=include_legacy_wikipedia,
        resolve_legacy_redirects=resolve_legacy_redirects,
        memory_top=memory_top,
        mode=requested_mode or "converse",
    )
    # The live renderer sees this data-only contract projection.  The legacy
    # intent/tagged packet remains available to CPU verification and training
    # tooling, but it is no longer the mouth's primary ingress payload.
    render_envelope = build_envelope_from_packet(packet, query=query)
    s_n = float(packet.get("s_n") or 0.0)
    cfg = load_config()
    voice = dict(cfg.get("voice") or {})
    prefer_qwen = bool(voice.get("prefer_over_lora", True))
    try:
        triad_context = open_context(
            TriadEnvelope.build(
                actor="architect",
                source="voice_request",
                target="gpu_mouth",
                action="SPEAK",
                payload={"query": query, "packet": packet, "max_tokens": max_tokens},
                s_n=s_n,
            )
        )
        authorize_operation(
            triad_context,
            operation="voice.generate",
            params={
                "backend": voice.get("backend"),
                "served_name": voice.get("served_name"),
                "max_tokens": max_tokens,
            },
            tool_name="voice_generate",
        )
    except TriadDenied as exc:
        return {
            "ok": False,
            "silent": True,
            "blocked": True,
            "text": "",
            "voice_source": "triad_denied",
            "packet": packet,
            "egress": {
                "allowed": False,
                "reason": exc.reason,
                "evidence": exc.evidence,
            },
            "events_path": str(VOICE_EVENTS_PATH).replace("\\", "/"),
        }

    if prefer_qwen:
        hit = _try_ollama_or_gguf(
            packet,
            query=query,
            render_envelope=render_envelope,
            max_tokens=max_tokens,
            cfg=cfg,
            triad_context=triad_context,
        )
        if hit is not None:
            return hit
        # Qwen preferred but draft failed/offline — CPU template (do not fall into base-generate mush)
        reach = server_reachable(cfg)
        raw_text = deterministic_speak(packet)
        return _finalize_spoken(
            query=query,
            packet=packet,
            raw_text=raw_text,
            voice_source=(
                "deterministic_after_qwen_fail"
                if reach.get("reachable")
                else "deterministic_offline"
            ),
            model="deterministic",
            s_n=s_n,
            triad_context=triad_context,
        )

    # Prefer local LoRA only when Qwen path not preferred
    if adapter_ready():
        prompt = envelope_to_completion_prompt(render_envelope)
        completion = hf_lora_generate(prompt, max_new_tokens=min(max_tokens, 64), temperature=0.15)
        if completion.get("text"):
            completion["text"] = clean_base_output(str(completion["text"]))
        raw_text = str(completion.get("text") or "")
        if looks_like_speech(raw_text, measured_s_n=s_n):
            voice_source = "hf_lora"

            def retry_renderer(envelope: Mapping[str, Any]) -> str:
                retry = hf_lora_generate(
                    envelope_to_completion_prompt(envelope),
                    max_new_tokens=min(max_tokens, 64),
                    temperature=0.10,
                )
                if retry.get("silent"):
                    return ""
                return clean_base_output(str(retry.get("text") or ""))

        else:
            raw_text = deterministic_speak(packet)
            voice_source = "deterministic_after_lora_fail"
            completion = {"ok": True, "silent": False, "text": raw_text, "model": "deterministic", "mode": "deterministic"}
            retry_renderer = None
        return _finalize_spoken(
            query=query,
            packet=packet,
            raw_text=raw_text,
            voice_source=voice_source,
            model=completion.get("model"),
            s_n=s_n,
            triad_context=triad_context,
            renderer_retry=retry_renderer,
        )

    reach = server_reachable(cfg)
    if not reach.get("reachable"):
        raw_text = deterministic_speak(packet)
        return _finalize_spoken(
            query=query,
            packet=packet,
            raw_text=raw_text,
            voice_source="deterministic_offline",
            model="deterministic",
            s_n=s_n,
            triad_context=triad_context,
        )

    # Legacy fallbacks (non-prefer Qwen configs)
    messages = envelope_to_messages(render_envelope)
    backend = str(voice.get("backend") or "").lower()
    if backend == "ollama":
        prompt = envelope_to_completion_prompt(render_envelope)
        completion = speak_generate(prompt, cfg=cfg, max_tokens=max_tokens)
        if completion.get("text"):
            completion["text"] = clean_base_output(str(completion["text"]))

        def retry_renderer(envelope: Mapping[str, Any]) -> str:
            retry = speak_generate(
                envelope_to_completion_prompt(envelope),
                cfg=cfg,
                max_tokens=max_tokens,
                temperature=0.25,
            )
            if retry.get("silent"):
                return ""
            return clean_base_output(str(retry.get("text") or ""))

    else:
        completion = speak_completion(messages, max_tokens=max_tokens)

        def retry_renderer(envelope: Mapping[str, Any]) -> str:
            retry = speak_completion(
                envelope_to_messages(envelope),
                max_tokens=max_tokens,
                cfg=cfg,
                temperature=0.25,
            )
            if retry.get("silent"):
                return ""
            return clean_base_output(str(retry.get("text") or ""))

    raw_text = str(completion.get("text") or "")
    if completion.get("silent") or not looks_like_speech(raw_text, measured_s_n=s_n):
        raw_text = deterministic_speak(packet)
        voice_source = "deterministic_until_sft"
        completion = {
            "ok": True,
            "silent": False,
            "text": raw_text,
            "model": completion.get("model") or "deterministic",
            "mode": "deterministic",
            "base_rejected": True,
        }
    else:
        voice_source = completion.get("mode") or "gpu"
    return _finalize_spoken(
        query=query,
        packet=packet,
        raw_text=raw_text,
        voice_source=voice_source,
        model=completion.get("model"),
        s_n=s_n,
        triad_context=triad_context,
        renderer_retry=retry_renderer,
    )
