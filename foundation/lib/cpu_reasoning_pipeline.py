"""Autonomous CPU decision pipeline before any voice renderer.

Pipeline:
  ingress normalization -> deterministic Luna plan -> verified retrieval ->
  CPU steel evaluation -> renderer-ready packet.

The pipeline never asks an LLM to decide facts, never treats a specialist or
adapter response as authority, and abstains when verified context is absent.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from lib.aios_adapter_input import normalize
from lib.aios_adapter_knowledge import query_manual_packet, query_packet
from lib.aios_adapter_steel import judge
from lib.cpu_claim_policy import verify_packet
from lib.knowledge_external_adapters import query_legacy_wikipedia
from lib.knowledge_source_contract import packet_from_retrieval
from lib.luna_core import assess_rendered_response, build_response_plan


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hits_text(hits: list[dict[str, Any]]) -> str:
    return "\n\n".join(str(hit.get("text") or "").strip() for hit in hits if str(hit.get("text") or "").strip())


def reason(
    value: Any,
    *,
    s_n: float | None = None,
    manual_only: bool = False,
    local_wikipedia: bool = True,
    top_k: int = 5,
) -> dict[str, Any]:
    """Produce a CPU-owned reasoning packet; no durable writes are performed."""
    ingress = normalize(value, s_n=s_n)
    iev = ingress.get("evidence") or {}
    if not ingress.get("ok"):
        return {"ok": False, "state": "DENIED", "stage": "ingress", "ingress": ingress, "at": _utc()}
    text = str(iev.get("plain_text") or "").strip()
    plan = build_response_plan(text, grounded=False)
    retrieval = query_manual_packet(text, k=top_k) if manual_only else query_packet(text, k=top_k)
    if not manual_only and local_wikipedia and not (retrieval.get("hits") or []):
        local = query_legacy_wikipedia(text, limit=top_k, max_chars=12000, resolve_redirects=False)
        local_facts = local.get("facts") or []
        local_hits = [
            {
                "source": "wikipedia_local",
                "doc": (fact.get("source") or {}).get("path"),
                "score": 1,
                "text": fact.get("value"),
                "claim": fact.get("claim"),
                "source_ref": fact.get("source"),
            }
            for fact in local_facts
        ]
        retrieval = {
            **local,
            "hits": local_hits,
            "packet": packet_from_retrieval(text, local_hits),
            "mode": "wikipedia_local_read_only",
        }
    hits = retrieval.get("hits") or []
    packet_state = str((retrieval.get("packet") or {}).get("state") or retrieval.get("state") or "")
    grounded = bool(hits) and packet_state in {"VERIFIED", "PARTIAL"}
    plan = build_response_plan(text, grounded=grounded, health_mode=False)
    if not hits or not grounded:
        return {
            "ok": True,
            "state": "ABSTAIN",
            "reason": "no_verified_context",
            "ingress": ingress,
            "plan": plan,
            "retrieval": retrieval,
            "renderer_packet": None,
            "llm_authority": False,
            "at": _utc(),
        }
    fact_text = _hits_text(hits)
    if not fact_text:
        return {"ok": True, "state": "ABSTAIN", "reason": "verified_hits_without_text", "ingress": ingress, "plan": plan, "retrieval": retrieval, "renderer_packet": None, "llm_authority": False, "at": _utc()}
    judged = judge(fact_text, previous="", persist=False, master_s_n=s_n)
    je = judged.get("evidence") or {}
    verdict = je.get("verdict") or {}
    if not judged.get("ok") or verdict.get("passed") is not True:
        return {"ok": True, "state": "ABSTAIN", "reason": "cpu_judge_rejected_context", "ingress": ingress, "plan": plan, "retrieval": retrieval, "judge": judged, "renderer_packet": None, "llm_authority": False, "at": _utc()}
    containment = assess_rendered_response(fact_text, grounded=True)
    if not containment.get("ok"):
        return {"ok": True, "state": "ABSTAIN", "reason": "containment_rejected_context", "ingress": ingress, "plan": plan, "retrieval": retrieval, "judge": judged, "containment": containment, "renderer_packet": None, "llm_authority": False, "at": _utc()}
    policy = verify_packet(retrieval.get("packet") or {})
    if not policy.get("ok"):
        return {"ok": True, "state": "ABSTAIN", "reason": "claim_policy_rejected_context", "ingress": ingress, "plan": plan, "retrieval": retrieval, "judge": judged, "containment": containment, "policy": policy, "renderer_packet": None, "llm_authority": False, "at": _utc()}
    renderer_packet = {
        "instruction": "Render only the supplied verified facts. Do not add unsupported claims or internal telemetry.",
        "question": text,
        "facts": fact_text,
        "source_packet": policy.get("packet"),
        "response_plan": plan,
        "cpu_judge": {"passed": verdict.get("passed"), "structural_rsr": verdict.get("structural_rsr"), "token_overlap": verdict.get("token_overlap")},
        "telemetry_allowed": False,
        "llm_authority": False,
    }
    return {
        "ok": True,
        "state": "VERIFIED",
        "ingress": ingress,
        "plan": plan,
        "retrieval": retrieval,
        "judge": judged,
        "containment": containment,
        "policy": policy,
        "renderer_packet": renderer_packet,
        "llm_authority": False,
        "writes_performed": False,
        "at": _utc(),
    }


def compact(result: dict[str, Any]) -> str:
    """Stable JSON summary for an autonomous task receipt."""
    return json.dumps({"ok": result.get("ok"), "state": result.get("state"), "reason": result.get("reason"), "llm_authority": result.get("llm_authority"), "writes_performed": result.get("writes_performed")}, sort_keys=True)
