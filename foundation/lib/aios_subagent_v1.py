"""AIOS skeleton subagent worker bus (v1).

Local process/task units with receipts — not Cursor IDE fanout.
Profiles map major AIOS slots to plan-only runners or SKIP stubs.
Compute-core ("brain") integration is a reserved hook only; v1 does not
dispatch deep cognition.

Authority: CPU-owned. Fail-closed on unknown profiles. Never starts AIOS,
never enables soft-0.99, never GPU-mints authority tags, never enables
bridge canary unless profile + operator flag both allow (v1: never).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import FOUNDATION_ROOT, VIV_ROOT

SCHEMA_VERSION = "viv_aios_subagent_receipt_v1"
MODULE_ID = "aios_subagent"
VERSION = "v1"
RECEIPTS_ROOT = FOUNDATION_ROOT / "artifacts" / "auto" / "aios_subagents"
SCRIPTS_DIR = FOUNDATION_ROOT / "scripts"
PYTHON = VIV_ROOT.parent / ".venv" / "Scripts" / "python.exe"

DEFAULT_FANOUT_CONCURRENCY = 3
MAX_FANOUT_CONCURRENCY = 3
DEFAULT_TIMEOUT_S = 60.0
DEFAULT_MAX_STEPS = 1

# Reserved seam for later compute-core job dispatch. v1 never invokes it.
COMPUTE_CORE_HOOK = {
    "slot": "compute_core",
    "status": "RESERVED",
    "version": "v1_skeleton",
    "dispatch": False,
    "note": (
        "Subagents execute skeleton jobs (plan/SKIP receipts) only. "
        "Future compute-core may enqueue typed jobs here; never mint authority."
    ),
}

_RECEIPT_RE = re.compile(
    r"(?im)^\s*(?:RECEIPT|receipt|receipt_path|json_path)\s*[:=]\s*(\S+)"
)


@dataclass(frozen=True)
class SubagentProfile:
    """Named skeleton slot on the worker bus."""

    profile_id: str
    system_id: str
    description: str
    kind: str  # runner | stub_skip | selftest
    script: str | None
    plan_args: tuple[str, ...]
    execute_args: tuple[str, ...]
    default_mode: str  # plan_only | execute
    execute_allowed: bool
    allows_aios_start: bool
    allows_soft_099: bool
    allows_bridge_canary_enable: bool
    default_timeout_s: float
    max_steps: int
    cold_start_phase: int | None
    constraints: tuple[str, ...]
    stub_reason: str = ""
    compute_core_ready: bool = False  # always False in v1


PROFILES: tuple[SubagentProfile, ...] = (
    SubagentProfile(
        "selftest_ping",
        "subagent_bus",
        "Tiny bus self-check (no sibling runner).",
        "selftest",
        None,
        (),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        5.0,
        1,
        0,
        ("cpu_owned", "no_aios_runtime", "skeleton_only"),
    ),
    SubagentProfile(
        "preflight",
        "systems_preflight",
        "AIOS systems preflight (quick, plan-only).",
        "runner",
        "run_aios_systems_preflight_v1.py",
        ("--profile", "quick", "--plan-only"),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        60.0,
        1,
        0,
        ("plan_only", "no_aios_runtime"),
    ),
    SubagentProfile(
        "rid_plant",
        "rid_core",
        "RID plant automation plan-only (no 120s stress).",
        "runner",
        "run_rid_plant_automation_v1.py",
        ("--plan-only",),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        30.0,
        1,
        1,
        ("plan_only", "no_120s_plant", "no_aios_runtime"),
    ),
    SubagentProfile(
        "voice_contracts",
        "voice_core",
        "Voice/mouth contract plan-only catalog.",
        "runner",
        "run_voice_contract_automation_v1.py",
        ("--profile", "contracts", "--plan-only"),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        60.0,
        1,
        3,
        ("plan_only", "no_voice_server", "no_aios_runtime"),
    ),
    SubagentProfile(
        "cognitive_plan",
        "cognitive_cores",
        "CARMA + consciousness fixture plan-only.",
        "runner",
        "run_cognitive_cores_automation_v1.py",
        ("--profile", "both", "--plan-only"),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        60.0,
        1,
        2,
        ("plan_only", "no_live_remember", "no_aios_runtime"),
    ),
    SubagentProfile(
        "service_plan",
        "service_cores",
        "Privacy/support/dream service plan-only.",
        "runner",
        "run_service_cores_automation_v1.py",
        ("--core", "all", "--plan-only"),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        60.0,
        1,
        2,
        ("plan_only", "no_dream_cycle", "no_aios_runtime"),
    ),
    SubagentProfile(
        "training_plan",
        "training",
        "Training automation catalog (no GPU_LONG).",
        "runner",
        "run_training_automation_v1.py",
        ("--catalog",),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        60.0,
        1,
        3,
        ("plan_only", "no_gpu_long", "no_aios_runtime"),
    ),
    SubagentProfile(
        "backup_plan",
        "backup_core",
        "Backup uml_lane plan-only (no vault copy).",
        "runner",
        "run_backup_core_automation_v1.py",
        ("--profile", "uml_lane", "--plan-only"),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        60.0,
        1,
        2,
        ("plan_only", "no_vault_copy", "no_aios_runtime"),
    ),
    SubagentProfile(
        "core_orchestrator",
        "aios_core_automation",
        "Core automation profile list (skeleton light touch).",
        "runner",
        "run_aios_core_automation_v1.py",
        ("--list",),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        45.0,
        1,
        0,
        ("plan_only", "list_only", "no_aios_runtime"),
    ),
    SubagentProfile(
        "bridge_canary",
        "uml_bridge",
        "Bridge canary rollback-check only (default OFF; no --enable-canary).",
        "runner",
        "run_field_scoped_bridge_canary_v1.py",
        ("--rollback-check",),
        (),
        "plan_only",
        False,
        False,
        False,
        False,  # v1 never allows enable
        60.0,
        1,
        3,
        ("canary_default_off", "no_enable_canary", "no_soft_099", "no_aios_runtime"),
    ),
    SubagentProfile(
        "security_gate",
        "security",
        "UML bridge Security IN/OUT gate selftest.",
        "runner",
        "test_uml_bridge_security_gate_v1.py",
        (),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        30.0,
        1,
        2,
        ("contract", "fail_closed", "no_aios_runtime"),
    ),
    # --- Broad skeleton stubs (major slots; SKIP until wired) ---
    SubagentProfile(
        "vision",
        "vision",
        "Vision perception slot (skeleton stub).",
        "stub_skip",
        None,
        (),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        5.0,
        1,
        5,
        ("stub", "no_aios_runtime"),
        stub_reason="vision not absorbed into Viv; SKIP stub",
    ),
    SubagentProfile(
        "hearing",
        "hearing",
        "Hearing/audio slot (skeleton stub).",
        "stub_skip",
        None,
        (),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        5.0,
        1,
        5,
        ("stub", "no_aios_runtime"),
        stub_reason="hearing pipeline NONE in Viv; SKIP stub",
    ),
    SubagentProfile(
        "knowledge",
        "knowledge",
        "Knowledge/Wikipedia absorption slot (skeleton stub).",
        "stub_skip",
        None,
        (),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        5.0,
        1,
        4,
        ("stub", "no_aios_runtime"),
        stub_reason="full corpus absorption not wired; SKIP stub",
    ),
    SubagentProfile(
        "federation",
        "federation",
        "Hive/federation slot (skeleton stub).",
        "stub_skip",
        None,
        (),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        5.0,
        1,
        8,
        ("stub", "no_network", "no_aios_runtime"),
        stub_reason="federation operator-gated; SKIP stub",
    ),
    SubagentProfile(
        "perception",
        "perception",
        "Perception multi-sense slot (skeleton stub; bus has perception_plan).",
        "stub_skip",
        None,
        (),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        5.0,
        1,
        5,
        ("stub", "no_capture", "no_aios_runtime"),
        stub_reason="perception plan via bus adapter; worker-bus SKIP stub",
    ),
    SubagentProfile(
        "ethics",
        "ethics",
        "Ethics/adaptive slot (skeleton stub; bus has ethics_plan).",
        "stub_skip",
        None,
        (),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        5.0,
        1,
        7,
        ("stub", "no_aios_runtime"),
        stub_reason="ethics loop not implemented; SKIP stub",
    ),
    SubagentProfile(
        "hardware",
        "hardware",
        "Hardware-agnostic / infra slot (skeleton stub; bus has hardware_plan).",
        "stub_skip",
        None,
        (),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        5.0,
        1,
        8,
        ("stub", "no_deploy", "no_aios_runtime"),
        stub_reason="hardware adaptive policy incomplete; SKIP stub",
    ),
    SubagentProfile(
        "dream_cycle",
        "dream_core",
        "Dream cycle execute slot (skeleton stub; plan via service_plan).",
        "stub_skip",
        None,
        (),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        5.0,
        1,
        7,
        ("stub", "no_dream_cycle_execute", "no_aios_runtime"),
        stub_reason="dream execute refused on skeleton bus; use service_plan",
    ),
    SubagentProfile(
        "gpu_train",
        "training",
        "GPU_LONG training slot (skeleton stub).",
        "stub_skip",
        None,
        (),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        5.0,
        1,
        3,
        ("stub", "no_gpu_long", "no_aios_runtime"),
        stub_reason="GPU_LONG never auto-run on skeleton bus; SKIP stub",
    ),
    SubagentProfile(
        "soft_099",
        "policy",
        "Soft-0.99 / rule-fade slot (skeleton stub; operator-gated forever here).",
        "stub_skip",
        None,
        (),
        (),
        "plan_only",
        False,
        False,
        False,  # never True in v1
        False,
        5.0,
        1,
        3,
        ("stub", "soft_099_blocked", "no_aios_runtime"),
        stub_reason="soft-0.99 remains operator-gated; subagent cannot enable",
    ),
    SubagentProfile(
        "aios_runtime",
        "runtime",
        "AIOS start/stop slot (skeleton stub; refused).",
        "stub_skip",
        None,
        (),
        (),
        "plan_only",
        False,
        False,  # never True in v1
        False,
        False,
        5.0,
        1,
        0,
        ("stub", "no_aios_start", "no_aios_stop"),
        stub_reason="AIOS start/stop refused on skeleton bus",
    ),
    SubagentProfile(
        "compute_core",
        "compute_core",
        "Compute-core integration hook (RESERVED; no dispatch).",
        "stub_skip",
        None,
        (),
        (),
        "plan_only",
        False,
        False,
        False,
        False,
        5.0,
        1,
        1,
        ("stub", "compute_core_reserved", "no_deep_cognition"),
        stub_reason="compute-core hook reserved; v1 does not dispatch cognition",
    ),
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _posix(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _python() -> str:
    if PYTHON.is_file():
        return str(PYTHON)
    return sys.executable


def list_profiles() -> list[dict[str, Any]]:
    rows = []
    for p in PROFILES:
        row = asdict(p)
        row["plan_args"] = list(p.plan_args)
        row["execute_args"] = list(p.execute_args)
        row["constraints"] = list(p.constraints)
        rows.append(row)
    return rows


def get_profile(profile_id: str) -> SubagentProfile | None:
    key = str(profile_id or "").strip().casefold()
    for p in PROFILES:
        if p.profile_id.casefold() == key:
            return p
    return None


def require_profile(profile_id: str) -> SubagentProfile:
    profile = get_profile(profile_id)
    if profile is None:
        known = ", ".join(p.profile_id for p in PROFILES)
        raise ValueError(f"unknown_subagent_profile:{profile_id!r}; known=[{known}]")
    return profile


def _authority_block(*, parent_turn_token_id: str) -> dict[str, Any]:
    return {
        "plane": "cpu",
        "source": "cpu",
        "minted_by": "cpu",
        "gpu_authority_mint": False,
        "parent_turn_token_id": parent_turn_token_id,
        "single_turn_authority": True,
    }


def _extract_child_receipts(text: str) -> list[str]:
    found: list[str] = []
    for match in _RECEIPT_RE.finditer(text or ""):
        path = match.group(1).strip().rstrip(",;")
        if path and path not in found:
            found.append(path)
    # Also scan JSON blobs for common receipt keys.
    for key in ("receipt", "receipt_path", "json_path"):
        for m in re.finditer(rf'"{key}"\s*:\s*"([^"]+)"', text or ""):
            path = m.group(1)
            if path and path not in found and ("/" in path or "\\" in path):
                found.append(path.replace("\\", "/"))
    return found


def write_receipt(payload: dict[str, Any], *, stamp: str | None = None) -> Path:
    stamp_value = stamp or _utc_stamp()
    folder = RECEIPTS_ROOT / stamp_value
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "RECEIPT.json"
    body = dict(payload)
    body.setdefault("stamp", stamp_value)
    body.setdefault("created_at", _utc())
    body.setdefault("schema_version", SCHEMA_VERSION)
    body.setdefault("module", MODULE_ID)
    body.setdefault("version", VERSION)
    body.setdefault("receipt_root", _posix(RECEIPTS_ROOT))
    body.setdefault("compute_core_hook", COMPUTE_CORE_HOOK)
    body.setdefault("aios_runtime_started", False)
    body.setdefault("soft_0_99", False)
    body.setdefault("gpu_long_launched", False)
    body.setdefault("bridge_canary_enabled", False)
    path.write_text(
        json.dumps(body, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    md = folder / "RECEIPT.md"
    md.write_text(
        "\n".join(
            [
                f"# AIOS subagent receipt `{stamp_value}`",
                "",
                f"- ok: `{body.get('ok')}`",
                f"- outcome: `{body.get('outcome')}`",
                f"- profile: `{body.get('profile')}`",
                f"- objective_id: `{body.get('objective_id')}`",
                f"- parent_turn_token_id: `{(body.get('authority') or {}).get('parent_turn_token_id')}`",
                f"- duration_s: `{body.get('duration_s')}`",
                f"- exit_code: `{body.get('exit_code')}`",
                f"- aios_runtime_started: `{body.get('aios_runtime_started')}`",
                f"- soft_0_99: `{body.get('soft_0_99')}`",
                f"- bridge_canary_enabled: `{body.get('bridge_canary_enabled')}`",
                f"- compute_core_dispatch: `{COMPUTE_CORE_HOOK.get('dispatch')}`",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    latest = RECEIPTS_ROOT / "LATEST.json"
    latest.write_text(
        json.dumps(body, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _refuse_forbidden_flags(
    profile: SubagentProfile,
    *,
    enable_aios_start: bool,
    enable_soft_099: bool,
    enable_bridge_canary: bool,
) -> dict[str, Any] | None:
    if enable_aios_start and not profile.allows_aios_start:
        return {
            "ok": False,
            "outcome": "REFUSED",
            "reason": "aios_start_not_allowed_on_profile",
            "profile": profile.profile_id,
        }
    if enable_soft_099 and not profile.allows_soft_099:
        return {
            "ok": False,
            "outcome": "REFUSED",
            "reason": "soft_099_not_allowed_on_profile",
            "profile": profile.profile_id,
        }
    if enable_bridge_canary and not profile.allows_bridge_canary_enable:
        return {
            "ok": False,
            "outcome": "REFUSED",
            "reason": "bridge_canary_enable_not_allowed_on_profile",
            "profile": profile.profile_id,
        }
    # Global v1 hard denials even if a profile ever flips flags.
    if enable_aios_start:
        return {
            "ok": False,
            "outcome": "REFUSED",
            "reason": "aios_start_blocked_skeleton_v1",
            "profile": profile.profile_id,
        }
    if enable_soft_099:
        return {
            "ok": False,
            "outcome": "REFUSED",
            "reason": "soft_099_blocked_skeleton_v1",
            "profile": profile.profile_id,
        }
    if enable_bridge_canary:
        return {
            "ok": False,
            "outcome": "REFUSED",
            "reason": "bridge_canary_enable_blocked_skeleton_v1",
            "profile": profile.profile_id,
        }
    return None


def run_subagent(
    profile_id: str,
    *,
    objective_id: str | None = None,
    parent_turn_token_id: str | None = None,
    extra_args: list[str] | None = None,
    timeout_s: float | None = None,
    max_steps: int | None = None,
    plan_only: bool = True,
    execute: bool = False,
    enable_aios_start: bool = False,
    enable_soft_099: bool = False,
    enable_bridge_canary: bool = False,
    write: bool = True,
    stamp: str | None = None,
) -> dict[str, Any]:
    """Spawn/run one skeleton subagent job; always produce a receipt dict."""
    try:
        profile = require_profile(profile_id)
    except ValueError as exc:
        payload = {
            "ok": False,
            "outcome": "FAIL_CLOSED",
            "reason": str(exc),
            "profile": profile_id,
            "objective_id": objective_id or f"obj_{uuid.uuid4().hex[:12]}",
            "authority": _authority_block(
                parent_turn_token_id=parent_turn_token_id or f"turn_{uuid.uuid4().hex[:12]}"
            ),
            "aios_runtime_started": False,
            "soft_0_99": False,
            "bridge_canary_enabled": False,
            "gpu_long_launched": False,
            "compute_core_hook": COMPUTE_CORE_HOOK,
        }
        if write:
            path = write_receipt(payload, stamp=stamp or f"{_utc_stamp()}_unknown")
            payload["receipt"] = _posix(path)
        return payload

    obj_id = objective_id or f"obj_{uuid.uuid4().hex[:12]}"
    turn_id = parent_turn_token_id or f"turn_{uuid.uuid4().hex[:12]}"
    budget_timeout = float(timeout_s if timeout_s is not None else profile.default_timeout_s)
    budget_steps = int(max_steps if max_steps is not None else profile.max_steps)
    mode = "execute" if (execute and not plan_only and profile.execute_allowed) else "plan_only"

    refused = _refuse_forbidden_flags(
        profile,
        enable_aios_start=enable_aios_start,
        enable_soft_099=enable_soft_099,
        enable_bridge_canary=enable_bridge_canary,
    )
    if refused is not None:
        refused.update(
            {
                "objective_id": obj_id,
                "authority": _authority_block(parent_turn_token_id=turn_id),
                "mode": mode,
                "budget": {"timeout_s": budget_timeout, "max_steps": budget_steps},
                "aios_runtime_started": False,
                "soft_0_99": False,
                "bridge_canary_enabled": False,
                "gpu_long_launched": False,
                "compute_core_hook": COMPUTE_CORE_HOOK,
            }
        )
        if write:
            path = write_receipt(refused, stamp=stamp or f"{_utc_stamp()}_{profile.profile_id}_refused")
            refused["receipt"] = _posix(path)
        return refused

    if execute and not profile.execute_allowed:
        mode = "plan_only"

    started = time.perf_counter()
    started_at = _utc()
    base: dict[str, Any] = {
        "ok": False,
        "outcome": "PENDING",
        "profile": profile.profile_id,
        "system_id": profile.system_id,
        "kind": profile.kind,
        "description": profile.description,
        "objective_id": obj_id,
        "authority": _authority_block(parent_turn_token_id=turn_id),
        "mode": mode,
        "budget": {"timeout_s": budget_timeout, "max_steps": budget_steps},
        "constraints": list(profile.constraints),
        "cold_start_phase": profile.cold_start_phase,
        "started_at": started_at,
        "aios_runtime_started": False,
        "soft_0_99": False,
        "bridge_canary_enabled": False,
        "gpu_long_launched": False,
        "compute_core_hook": COMPUTE_CORE_HOOK,
        "compute_core_ready": False,
        "child_receipt_paths": [],
        "command": [],
        "exit_code": None,
        "stdout_tail": "",
        "stderr_tail": "",
    }

    if profile.kind in ("stub_skip",) or profile.kind == "stub_skip":
        base.update(
            {
                "ok": True,
                "outcome": "SKIP",
                "reason": profile.stub_reason or "skeleton_stub",
                "ended_at": _utc(),
                "duration_s": round(time.perf_counter() - started, 4),
                "exit_code": 0,
            }
        )
        if write:
            path = write_receipt(base, stamp=stamp or f"{_utc_stamp()}_{profile.profile_id}")
            base["receipt"] = _posix(path)
        return base

    if profile.kind == "selftest":
        base.update(
            {
                "ok": True,
                "outcome": "PASS",
                "reason": "selftest_ping",
                "ended_at": _utc(),
                "duration_s": round(time.perf_counter() - started, 4),
                "exit_code": 0,
                "selftest": {
                    "profile_count": len(PROFILES),
                    "fanout_cap": MAX_FANOUT_CONCURRENCY,
                    "compute_core_dispatch": False,
                },
            }
        )
        if write:
            path = write_receipt(base, stamp=stamp or f"{_utc_stamp()}_{profile.profile_id}")
            base["receipt"] = _posix(path)
        return base

    # runner
    script_name = profile.script or ""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.is_file():
        base.update(
            {
                "ok": False,
                "outcome": "SKIP",
                "reason": f"script_missing:{script_name}",
                "ended_at": _utc(),
                "duration_s": round(time.perf_counter() - started, 4),
                "exit_code": None,
            }
        )
        if write:
            path = write_receipt(base, stamp=stamp or f"{_utc_stamp()}_{profile.profile_id}_missing")
            base["receipt"] = _posix(path)
        return base

    if budget_steps < 1:
        base.update(
            {
                "ok": False,
                "outcome": "REFUSED",
                "reason": "max_steps_budget_exhausted",
                "ended_at": _utc(),
                "duration_s": round(time.perf_counter() - started, 4),
            }
        )
        if write:
            path = write_receipt(base, stamp=stamp or f"{_utc_stamp()}_{profile.profile_id}_budget")
            base["receipt"] = _posix(path)
        return base

    args = list(profile.plan_args if mode == "plan_only" else (profile.execute_args or profile.plan_args))
    if extra_args:
        args.extend(extra_args)
    cmd = [_python(), str(script_path), *args]
    base["command"] = [_posix(c) if isinstance(c, str) and ("/" in c or "\\" in c) else c for c in cmd]
    base["command"][0] = _posix(cmd[0]) or cmd[0]
    base["command"][1] = _posix(script_path) or script_name

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=budget_timeout,
            cwd=str(FOUNDATION_ROOT),
            check=False,
        )
        duration = round(time.perf_counter() - started, 4)
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        children = _extract_child_receipts(stdout + "\n" + stderr)
        ok = proc.returncode == 0
        base.update(
            {
                "ok": ok,
                "outcome": "PASS" if ok else "FAIL",
                "ended_at": _utc(),
                "duration_s": duration,
                "exit_code": proc.returncode,
                "stdout_tail": stdout[-2000:],
                "stderr_tail": stderr[-2000:],
                "child_receipt_paths": children,
            }
        )
    except subprocess.TimeoutExpired as exc:
        duration = round(time.perf_counter() - started, 4)
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        err = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        base.update(
            {
                "ok": False,
                "outcome": "TIMEOUT",
                "reason": f"timeout_s={budget_timeout}",
                "ended_at": _utc(),
                "duration_s": duration,
                "exit_code": None,
                "stdout_tail": out[-2000:],
                "stderr_tail": err[-2000:],
                "child_receipt_paths": _extract_child_receipts(out + "\n" + err),
            }
        )
    except OSError as exc:
        base.update(
            {
                "ok": False,
                "outcome": "FAIL",
                "reason": f"os_error:{exc}",
                "ended_at": _utc(),
                "duration_s": round(time.perf_counter() - started, 4),
            }
        )

    if write:
        path = write_receipt(base, stamp=stamp or f"{_utc_stamp()}_{profile.profile_id}")
        base["receipt"] = _posix(path)
    return base


def fanout_subagents(
    profile_ids: list[str],
    *,
    concurrency: int = DEFAULT_FANOUT_CONCURRENCY,
    objective_id: str | None = None,
    parent_turn_token_id: str | None = None,
    timeout_s: float | None = None,
    plan_only: bool = True,
    write: bool = True,
) -> dict[str, Any]:
    """Bounded parallel local subprocesses (cap concurrency)."""
    cap = max(1, min(int(concurrency), MAX_FANOUT_CONCURRENCY))
    ids = [p.strip() for p in profile_ids if str(p).strip()]
    obj_id = objective_id or f"fanout_{uuid.uuid4().hex[:12]}"
    turn_id = parent_turn_token_id or f"turn_{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    started_at = _utc()
    results: list[dict[str, Any]] = []

    def _one(pid: str) -> dict[str, Any]:
        return run_subagent(
            pid,
            objective_id=f"{obj_id}:{pid}",
            parent_turn_token_id=turn_id,
            timeout_s=timeout_s,
            plan_only=plan_only,
            write=write,
        )

    if not ids:
        payload = {
            "ok": False,
            "outcome": "FAIL_CLOSED",
            "reason": "empty_fanout",
            "objective_id": obj_id,
            "authority": _authority_block(parent_turn_token_id=turn_id),
            "concurrency": cap,
            "jobs": [],
            "aios_runtime_started": False,
            "soft_0_99": False,
            "bridge_canary_enabled": False,
            "gpu_long_launched": False,
            "compute_core_hook": COMPUTE_CORE_HOOK,
        }
        if write:
            path = write_receipt(payload, stamp=f"{_utc_stamp()}_fanout_empty")
            payload["receipt"] = _posix(path)
        return payload

    with ThreadPoolExecutor(max_workers=cap) as pool:
        futures = {pool.submit(_one, pid): pid for pid in ids}
        for fut in as_completed(futures):
            results.append(fut.result())

    # Stable order by requested profile list.
    ordered: list[dict[str, Any]] = []
    used: set[int] = set()
    for pid in ids:
        for i, r in enumerate(results):
            if i in used:
                continue
            if r.get("profile") == pid:
                ordered.append(r)
                used.add(i)
                break
    for i, r in enumerate(results):
        if i not in used:
            ordered.append(r)

    all_ok = all(bool(r.get("ok")) for r in ordered)
    payload = {
        "ok": all_ok,
        "outcome": "PASS" if all_ok else "FAIL",
        "mode": "fanout",
        "objective_id": obj_id,
        "authority": _authority_block(parent_turn_token_id=turn_id),
        "concurrency": cap,
        "fanout_cap": MAX_FANOUT_CONCURRENCY,
        "profiles": ids,
        "started_at": started_at,
        "ended_at": _utc(),
        "duration_s": round(time.perf_counter() - started, 4),
        "jobs": ordered,
        "child_receipt_paths": [r.get("receipt") for r in ordered if r.get("receipt")],
        "aios_runtime_started": False,
        "soft_0_99": False,
        "bridge_canary_enabled": False,
        "gpu_long_launched": False,
        "compute_core_hook": COMPUTE_CORE_HOOK,
    }
    if write:
        path = write_receipt(payload, stamp=f"{_utc_stamp()}_fanout")
        payload["receipt"] = _posix(path)
    return payload
