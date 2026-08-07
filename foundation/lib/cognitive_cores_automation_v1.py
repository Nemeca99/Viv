"""CARMA + consciousness core automation (plan-first, receipt-producing).

Mirrors the backup_core automation posture: cpu_plan first, receipts under
``artifacts/auto/cognitive_cores_automation/``, no AIOS start, no durable
memory commit, no live remember unless a separately governed executor is used.

Profiles: ``carma``, ``consciousness``, ``both``.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
RECEIPTS_ROOT = FOUNDATION / "artifacts" / "auto" / "cognitive_cores_automation"
SCHEMA_VERSION = "viv_cognitive_cores_automation_receipt_v1"
MODULE_ID = "cognitive_cores_automation"
VERSION = "v1"

PROFILES = ("carma", "consciousness", "both")

# Fixture prompts / fragments for effect-closed planning (no live memory I/O).
_CARMA_FIXTURES = (
    "RID stability channels are continuous values in [0,1]",
    "UML Nested PEMDAS is deterministic structure for compute",
    "CARMA retrieval is lexical provenance, not semantic authority",
)
_CONSCIOUSNESS_PROMPT = "truthful system documentation"
_CONSCIOUSNESS_EXPERIENCE = {
    "nodes": {"truth": {"weight": 1.0}, "evidence": {"weight": 1.0}},
    "edges": [
        ("evidence", "CAUSES", "truth"),
        ("evidence", "MECHANISM", "truth"),
    ],
}

EXECUTE_MEANING = {
    "carma": (
        "Safe execute is not enabled here. Live remember()/recall() and durable "
        "STM->LTM commit require a separately authorized memory executor with its "
        "own membrane gate and receipt. Plan-only reuses cpu_plan on fixtures."
    ),
    "consciousness": (
        "Safe execute is not enabled here. Durable consolidation and V2 biological "
        "loops remain out of scope. consciousness_cycle / cpu_plan already run "
        "in-memory with commit HOLD; plan-only is the automation surface."
    ),
    "both": (
        "Safe execute is not enabled for either core. Use --plan-only. Status "
        "observe can be done via adapter status() outside this automation."
    ),
}


def _posix(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _utc_stamp() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond // 1000:03d}Z"


def list_profiles() -> list[dict[str, Any]]:
    return [
        {
            "profile_id": "carma",
            "core_id": "carma_core",
            "default_mode": "plan_only",
            "execute_allowed": False,
            "planner": "lib.aios_adapter_carma.cpu_plan",
            "constraints": (
                "no_live_memory_write",
                "no_durable_commit",
                "no_aios_runtime",
            ),
        },
        {
            "profile_id": "consciousness",
            "core_id": "consciousness_core",
            "default_mode": "plan_only",
            "execute_allowed": False,
            "planner": "lib.aios_adapter_consciousness.cpu_plan",
            "constraints": (
                "no_durable_commit",
                "no_v2_biological",
                "no_aios_runtime",
            ),
        },
        {
            "profile_id": "both",
            "core_id": "cognitive_cores",
            "default_mode": "plan_only",
            "execute_allowed": False,
            "planner": "carma+consciousness",
            "constraints": (
                "no_live_memory_write",
                "no_durable_commit",
                "no_aios_runtime",
            ),
        },
    ]


def plan_carma(*, query: str = "RID stability", top: int = 2, explicit_commit: bool = False) -> dict[str, Any]:
    """Effect-closed CARMA cpu_plan on fixture fragments."""
    from lib.aios_adapter_carma import cpu_plan
    from lib.carma_core import make_fragment

    fragments = [
        make_fragment(text, provenance="fixture", source="cognitive_cores_automation")
        for text in _CARMA_FIXTURES
    ]
    plan = cpu_plan(fragments, query=query, top=top, explicit_commit=explicit_commit)
    ok = bool(plan.get("ok")) and plan.get("writes_performed") is False
    return {
        "ok": ok,
        "core_id": "carma_core",
        "profile": "carma",
        "mode": "plan_only",
        "plan": plan,
        "fixture_fragment_count": len(fragments),
        "writes_performed": False,
        "durable_commit_performed": False,
        "aios_runtime_started": False,
        "llm_authority": False,
        "execution_approved": False,
    }


def plan_consciousness(
    *,
    prompt: str = _CONSCIOUSNESS_PROMPT,
    explicit_commit: bool = False,
) -> dict[str, Any]:
    """Effect-closed consciousness cpu_plan (in-memory cycle + commit hold)."""
    from lib.aios_adapter_consciousness import cpu_plan

    plan = cpu_plan(
        prompt=prompt,
        experience=dict(_CONSCIOUSNESS_EXPERIENCE),
        explicit_commit=explicit_commit,
    )
    ok = bool(plan.get("ok")) and plan.get("writes_performed") is False
    return {
        "ok": ok,
        "core_id": "consciousness_core",
        "profile": "consciousness",
        "mode": "plan_only",
        "plan": plan,
        "writes_performed": False,
        "durable_commit_performed": False,
        "aios_runtime_started": False,
        "llm_authority": False,
        "viv_executes_v2": False,
        "execution_approved": False,
    }


def plan_profile(profile: str, *, explicit_commit: bool = False) -> dict[str, Any]:
    key = str(profile or "").strip().casefold()
    if key not in PROFILES:
        return {
            "ok": False,
            "error": "unknown_profile",
            "profile": profile,
            "available": list(PROFILES),
            "aios_runtime_started": False,
            "execution_approved": False,
        }
    if key == "carma":
        return plan_carma(explicit_commit=explicit_commit)
    if key == "consciousness":
        return plan_consciousness(explicit_commit=explicit_commit)
    carma = plan_carma(explicit_commit=explicit_commit)
    consciousness = plan_consciousness(explicit_commit=explicit_commit)
    ok = bool(carma.get("ok")) and bool(consciousness.get("ok"))
    return {
        "ok": ok,
        "core_id": "cognitive_cores",
        "profile": "both",
        "mode": "plan_only",
        "carma": carma,
        "consciousness": consciousness,
        "writes_performed": False,
        "durable_commit_performed": False,
        "aios_runtime_started": False,
        "llm_authority": False,
        "execution_approved": False,
    }


def refuse_execute(profile: str) -> dict[str, Any]:
    """Document why execute is refused; never starts AIOS or writes memory."""
    key = str(profile or "").strip().casefold()
    meaning = EXECUTE_MEANING.get(key) or EXECUTE_MEANING["both"]
    return {
        "ok": False,
        "error": "execute_not_allowed",
        "profile": key if key in PROFILES else profile,
        "mode": "execute_refused",
        "execute_allowed": False,
        "execute_meaning": meaning,
        "hint": "pass --plan-only (default) for fixture cpu_plan receipts",
        "aios_runtime_started": False,
        "writes_performed": False,
        "durable_commit_performed": False,
        "execution_approved": False,
    }


def write_receipt(payload: dict[str, Any], *, stamp: str | None = None) -> Path:
    stamp_value = stamp or _utc_stamp()
    folder = RECEIPTS_ROOT / stamp_value
    folder.mkdir(parents=True, exist_ok=True)
    body = dict(payload)
    body.setdefault("schema_version", SCHEMA_VERSION)
    body.setdefault("module_id", MODULE_ID)
    body.setdefault("version", VERSION)
    body.setdefault("stamp", stamp_value)
    body.setdefault("created_at", _utc())
    body.setdefault("receipt_root", _posix(RECEIPTS_ROOT))
    body.setdefault("aios_runtime_started", False)
    body.setdefault("deny_weight_packs", True)
    path = folder / "RECEIPT.json"
    path.write_text(
        json.dumps(body, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    md_lines = [
        f"# cognitive cores automation receipt `{stamp_value}`",
        "",
        f"- ok: `{body.get('ok')}`",
        f"- profile: `{body.get('profile')}`",
        f"- core_id: `{body.get('core_id')}`",
        f"- mode: `{body.get('mode')}`",
        f"- aios_runtime_started: `{body.get('aios_runtime_started')}`",
        f"- writes_performed: `{body.get('writes_performed')}`",
        f"- durable_commit_performed: `{body.get('durable_commit_performed')}`",
        f"- execution_approved: `{body.get('execution_approved')}`",
        "",
    ]
    if body.get("error"):
        md_lines.extend([f"- error: `{body.get('error')}`", ""])
    (folder / "RECEIPT.md").write_text("\n".join(md_lines), encoding="utf-8", newline="\n")
    return path
