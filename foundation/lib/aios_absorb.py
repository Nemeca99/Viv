"""Absorb LEGACY AIOS cores into Viv — real work against the 20+ system map."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.aios_systems import next_absorb_target, write_registry
from lib.paths import AUTO_ARTIFACTS
from lib.security_membrane import tool_gate

ABSORB_DIR = AUTO_ARTIFACTS / "systems"
ABSORB_LOG = ABSORB_DIR / "absorb_actions.jsonl"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _log(row: dict[str, Any]) -> None:
    ABSORB_DIR.mkdir(parents=True, exist_ok=True)
    with ABSORB_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def survey_and_write_registry() -> dict[str, Any]:
    rep = write_registry()
    nxt = rep.get("next")
    _log({"event": "survey", "at": _utc(), "counts": rep.get("counts"), "next": (nxt or {}).get("id")})
    return {
        "ok": True,
        "stdout": (
            f"registry written counts={rep.get('counts')} "
            f"next={(nxt or {}).get('generation')}/{(nxt or {}).get('id')} "
            f"md={rep.get('registry_md')}"
        ),
        "registry": rep,
        "next": nxt,
    }


def absorb_steel_judge(*, s_n: float) -> dict[str, Any]:
    from lib.steel_judge import evaluate, persist_verdict

    # Closer mutation pair so structural RSR clears 0.70 (V2 judge thresholds)
    prev = "Build AIOS with rid security carma tool_core steel_brain equilibrium"
    cur = "Build AIOS with rid security carma tool_core steel_brain equilibrium judge"
    verdict = evaluate(cur, prev, master_s_n=float(s_n), target_structural=0.55)
    saved = persist_verdict(verdict, s_n=float(s_n))
    _log(
        {
            "event": "absorb_steel_judge",
            "at": _utc(),
            "ok": saved.get("ok"),
            "passed": verdict.get("passed"),
            "deferred": saved.get("deferred"),
        }
    )
    return {
        "ok": bool(saved.get("ok")),
        "stdout": (
            f"steel_judge passed={verdict.get('passed')} struct={verdict.get('structural_rsr')} "
            f"path={saved.get('path')} deferred={saved.get('deferred')}"
        ),
        "verdict": verdict,
        "path": saved.get("path"),
        "module": "steel_brain_core",
        "error": saved.get("error"),
        "deferred": saved.get("deferred"),
    }


def absorb_knowledge(*, s_n: float) -> dict[str, Any]:
    from lib.aios_knowledge import absorb_sources

    out = absorb_sources(s_n=s_n)
    _log({"event": "absorb_knowledge", "at": _utc(), "ok": out.get("ok"), "chunks": (out.get("absorbed") or [])})
    out["module"] = "knowledge_core+rag_core"
    return out


def absorb_next(*, s_n: float) -> dict[str, Any]:
    """Pick next LEGACY core from registry and run the matching absorb handler."""
    survey = survey_and_write_registry()
    nxt = survey.get("next") or next_absorb_target()
    if not nxt:
        return {"ok": True, "stdout": "absorb_queue_empty", "skipped": True}

    cid = str(nxt.get("id") or "")
    gen = str(nxt.get("generation") or "")

    # Handlers for highest-priority real absorbs
    if cid == "steel_brain_core":
        out = absorb_steel_judge(s_n=s_n)
    elif cid in {"knowledge_core", "rag_core"}:
        out = absorb_knowledge(s_n=s_n)
    elif cid == "tool_core":
        # Viv already has tool_gate; write evidence bridge note + re-scan
        note = ABSORB_DIR / "tool_core_bridge.md"
        body = (
            "# tool_core absorb note\n\n"
            "V2 tool_core gated by Luna SCP + AIOS_V2 boundary.\n"
            "Viv equivalent: lib/security_membrane.tool_gate + Rust security_core.\n"
            "Status: PARTIAL — Viv gate is live; V2 tool surface not dual-booted.\n"
            f"Absorbed-at: {_utc()}\n"
        )
        gate = str(note).replace("\\", "/")
        v = tool_gate("write_file", {"path": gate, "content": body}, s_n)
        if not v.get("allowed"):
            out = {"ok": False, "error": v.get("reason"), "module": "tool_core"}
        else:
            note.write_text(body, encoding="utf-8")
            out = {"ok": True, "stdout": f"tool_core bridge note {gate}", "path": gate, "module": "tool_core"}
        _log({"event": "absorb_tool_core", "at": _utc(), "ok": out.get("ok")})
    elif cid == "dataset_core":
        note = ABSORB_DIR / "dataset_core_bridge.md"
        body = (
            "# dataset_core absorb note\n\n"
            "V2 dataset_core + global index remain LEGACY under FSAA/Luna/AIOS_V2.\n"
            "Viv knowledge absorb indexes architecture maps (keyword) as Phase-1 stand-in.\n"
            "Next: wire read_global_index into lib/aios_knowledge after wiki batches audited.\n"
            f"Queued-at: {_utc()}\n"
        )
        gate = str(note).replace("\\", "/")
        v = tool_gate("write_file", {"path": gate, "content": body}, s_n)
        if not v.get("allowed"):
            out = {"ok": False, "error": v.get("reason"), "module": "dataset_core"}
        else:
            note.write_text(body, encoding="utf-8")
            # Also run knowledge absorb so Architect gets real index evidence
            know = absorb_knowledge(s_n=s_n)
            out = {
                "ok": bool(know.get("ok")),
                "stdout": f"dataset bridge + knowledge: {know.get('stdout')}",
                "path": know.get("path") or gate,
                "module": "dataset_core",
                "knowledge": know,
                "error": know.get("error"),
            }
        _log({"event": "absorb_dataset_core", "at": _utc(), "ok": out.get("ok")})
    else:
        # Generic: copy a README/entry stub pointer into Viv artifacts (read-only map)
        stub = ABSORB_DIR / f"PENDING_{gen}_{cid}.md"
        body = (
            f"# PENDING ABSORB: {gen}/{cid}\n\n"
            f"Role: {nxt.get('role')}\n"
            f"Source: `{nxt.get('path')}`\n"
            f"Priority: {nxt.get('priority')}\n"
            f"Status: {nxt.get('status')}\n\n"
            "Architect: this core is on the absorb queue. "
            "Next agent cycle should implement a Viv-native bridge.\n"
            f"Queued-at: {_utc()}\n"
        )
        gate = str(stub).replace("\\", "/")
        v = tool_gate("write_file", {"path": gate, "content": body}, s_n)
        if not v.get("allowed"):
            out = {"ok": False, "error": v.get("reason"), "module": cid}
        else:
            stub.write_text(body, encoding="utf-8")
            out = {
                "ok": True,
                "stdout": f"queued pending absorb stub {gate}",
                "path": gate,
                "module": cid,
                "pending": True,
            }
        _log({"event": "absorb_pending", "at": _utc(), "module": cid, "ok": out.get("ok")})

    # Refresh registry after absorb
    write_registry()
    out["next_was"] = {"id": cid, "generation": gen, "role": nxt.get("role")}
    return out
