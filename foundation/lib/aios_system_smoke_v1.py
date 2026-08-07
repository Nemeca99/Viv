"""AIOS / Viv system skeleton smoke (CPU-safe, plan-first).

Proves the **skeleton walks**: orchestration + safe surfaces respond
(plan-only / catalog / contracts / canary / security gate). Does **not**
claim every core is finished. Vacant/missing slots are SKIP labeled
``SKELETON``.

Never starts/stops AIOS, never GPU_LONG, never 120s plant stress, never
copies large backup vaults (backup step is ``--plan-only`` only).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import FOUNDATION_ROOT, VIV_ROOT

SCHEMA_VERSION = "viv_aios_system_smoke_receipt_v1"
MODULE_ID = "aios_system_smoke"
VERSION = "v1"
SMOKE_KIND = "skeleton"
RECEIPTS_ROOT = FOUNDATION_ROOT / "artifacts" / "auto" / "system_smoke"
SCRIPTS_DIR = FOUNDATION_ROOT / "scripts"
PYTHON = VIV_ROOT.parent / ".venv" / "Scripts" / "python.exe"

COLD_START_PHASES: dict[int, str] = {
    0: "documentation_and_inventory",
    1: "finish_foundation_spine",
    2: "consolidate_security_and_memory",
    3: "finish_voice_contract_and_training",
    4: "migrate_knowledge_and_ingestion",
    5: "restore_perception",
    6: "identity_sovereignty_transparency",
    7: "dream_ethics_adaptive_behavior",
    8: "hardware_agnosticism_and_distributed",
}

# Soft wall-time budget for the whole smoke (seconds). Individual step
# timeouts are tighter; overshoot is recorded but does not invent new work.
TARGET_WALL_S = 300

_RECEIPT_RE = re.compile(
    r"(?im)^\s*(?:RECEIPT|receipt|receipt_path|json_path)\s*(?:[:=]\s*|\s+)(\S+)"
)


@dataclass(frozen=True)
class SmokeStep:
    """One delegated surface in the system smoke catalog."""

    step_id: str
    name: str
    script: str
    args: tuple[str, ...]
    cold_start_phase: int | None
    timeout_s: float
    risk: str  # CPU_SAFE | MEASUREMENT_ONLY | PLAN_ONLY | CONTRACT
    notes: str = ""
    # If False, missing script → SKIP (not FAIL). All catalog steps are soft-missing.
    required_if_present: bool = True


@dataclass
class StepResult:
    step_id: str
    name: str
    status: str  # PASS | FAIL | SKIP | INCONCLUSIVE
    seconds: float
    cold_start_phase: int | None
    cold_start_phase_name: str | None
    command: list[str]
    returncode: int | None
    receipt: str | None
    note: str
    risk: str
    stdout_tail: str = ""
    stderr_tail: str = ""


SMOKE_CATALOG: tuple[SmokeStep, ...] = (
    SmokeStep(
        "systems_preflight",
        "AIOS systems preflight (quick)",
        "run_aios_systems_preflight_v1.py",
        ("--profile", "quick", "--plan-only"),
        0,
        60.0,
        "PLAN_ONLY",
        "Phase 0 inventory; no runtime start",
    ),
    SmokeStep(
        "core_automation_plan",
        "AIOS core automation (plan-only)",
        "run_aios_core_automation_v1.py",
        ("--plan-only", "--preflight-profile", "quick"),
        0,
        90.0,
        "PLAN_ONLY",
        "Integrated preflight+training catalog+backup plan; "
        "execute-safe excluded (would copy backup uml_lane)",
    ),
    SmokeStep(
        "training_uml_status",
        "Training automation (uml_status)",
        "run_training_automation_v1.py",
        ("--profile", "uml_status"),
        3,
        60.0,
        "MEASUREMENT_ONLY",
        "Measurement only; no GPU_LONG",
    ),
    SmokeStep(
        "rid_plant_plan",
        "RID plant automation (plan-only)",
        "run_rid_plant_automation_v1.py",
        ("--plan-only",),
        1,
        30.0,
        "PLAN_ONLY",
        "RID-first; no 120s stress",
    ),
    SmokeStep(
        "rid_plant_health_quick",
        "RID plant health_quick (execute)",
        "run_rid_plant_automation_v1.py",
        ("--profile", "health_quick", "--execute"),
        1,
        15.0,
        "CPU_SAFE",
        "Non-stress foundation health; expected <10s",
    ),
    SmokeStep(
        "voice_contracts",
        "Voice contract automation (contracts)",
        "run_voice_contract_automation_v1.py",
        ("--profile", "contracts"),
        3,
        90.0,
        "CONTRACT",
        "CPU-owned speak-path contracts; no voice server start",
    ),
    SmokeStep(
        "cognitive_cores",
        "Cognitive cores (both, plan-only)",
        "run_cognitive_cores_automation_v1.py",
        ("--profile", "both", "--plan-only"),
        2,
        60.0,
        "PLAN_ONLY",
        "CARMA + consciousness fixture cpu_plan",
    ),
    SmokeStep(
        "service_cores",
        "Service cores (all, plan-only)",
        "run_service_cores_automation_v1.py",
        ("--core", "all", "--plan-only"),
        2,
        60.0,
        "PLAN_ONLY",
        "privacy/support/dream plan; no dream cycles",
    ),
    SmokeStep(
        "backup_uml_lane_plan",
        "Backup core (uml_lane, plan-only)",
        "run_backup_core_automation_v1.py",
        ("--profile", "uml_lane", "--plan-only"),
        2,
        60.0,
        "PLAN_ONLY",
        "Plan/inventory only — no vault copy in smoke",
    ),
    SmokeStep(
        "uml_bridge_security_gate",
        "UML bridge security gate selftest",
        "test_uml_bridge_security_gate_v1.py",
        (),
        2,
        30.0,
        "CONTRACT",
        "Security IN/OUT fail-closed gate",
    ),
    SmokeStep(
        "field_scoped_bridge_canary",
        "Field-scoped bridge canary",
        "run_field_scoped_bridge_canary_v1.py",
        ("--enable-canary", "--no-append-thesis"),
        3,
        60.0,
        "CONTRACT",
        "Flag: --enable-canary (default OFF); --no-append-thesis for smoke; "
        "restored CANARY_PASS 64/64 (20260807T092420Z); bounded; no soft-0.99",
    ),
    SmokeStep(
        "intent_uml_request_ingress",
        "Intent UML request ingress selftest",
        "test_intent_uml_request_ingress_v1.py",
        (),
        3,
        30.0,
        "CONTRACT",
        "Identity-side uml_request ingress contracts",
    ),
    SmokeStep(
        "aios_subagent_list",
        "AIOS subagent worker bus (--list)",
        "run_aios_subagent_v1.py",
        ("--list",),
        0,
        30.0,
        "PLAN_ONLY",
        "Skeleton worker bus profile catalog; no AIOS start",
    ),
    SmokeStep(
        "aios_subagent_selftest",
        "AIOS subagent worker bus selftest",
        "test_aios_subagent_v1.py",
        (),
        0,
        60.0,
        "CPU_SAFE",
        "Fail-closed + ping + stub fanout; no heavy runners",
    ),
)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _posix(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _python() -> str:
    if PYTHON.is_file():
        return str(PYTHON)
    return sys.executable


def plan_catalog() -> dict[str, Any]:
    """Machine-readable plan of smoke steps (no execute)."""
    steps = []
    for step in SMOKE_CATALOG:
        script_path = SCRIPTS_DIR / step.script
        steps.append(
            {
                "step_id": step.step_id,
                "name": step.name,
                "script": step.script,
                "script_path": _posix(script_path),
                "script_present": script_path.is_file(),
                "args": list(step.args),
                "command": [_python(), _posix(script_path) or step.script, *step.args],
                "cold_start_phase": step.cold_start_phase,
                "cold_start_phase_name": (
                    COLD_START_PHASES.get(step.cold_start_phase)
                    if step.cold_start_phase is not None
                    else None
                ),
                "timeout_s": step.timeout_s,
                "risk": step.risk,
                "notes": step.notes,
                "required_if_present": step.required_if_present,
            }
        )
    present = sum(1 for s in steps if s["script_present"])
    vacant = [s["step_id"] for s in steps if not s["script_present"]]
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "module": MODULE_ID,
        "version": VERSION,
        "smoke_kind": SMOKE_KIND,
        "mode": "plan_only",
        "purpose": (
            "Prove skeleton orchestration + safe surfaces respond; "
            "not a claim that every core is finished"
        ),
        "target_wall_s": TARGET_WALL_S,
        "receipts_root": _posix(RECEIPTS_ROOT),
        "constraints": [
            "no_aios_start_stop",
            "no_gpu_long",
            "no_120s_plant_stress",
            "no_backup_vault_copy",
            "fail_closed_on_hard_fail",
            "skeleton_skip_ok",
        ],
        "cold_start_phases": COLD_START_PHASES,
        "step_count": len(steps),
        "scripts_present": present,
        "vacant_skeleton_slots": vacant,
        "steps": steps,
        "excluded": [
            {
                "surface": "run_aios_core_automation_v1.py --execute-safe",
                "reason": "execute-safe runs backup uml_lane copy; skeleton smoke keeps backup plan-only",
            },
            {
                "surface": "120s rid plant stress / GPU_LONG / weight training",
                "reason": "hard smoke constraints",
            },
            {
                "surface": "soft-0.99 / bridge default promotion",
                "reason": "canary remains default OFF; smoke uses --enable-canary only",
            },
        ],
        "aios_runtime_started": False,
        "gpu_long_launched": False,
    }


def _extract_receipt(stdout: str, stderr: str) -> str | None:
    for blob in (stdout, stderr):
        for match in _RECEIPT_RE.finditer(blob or ""):
            candidate = match.group(1).strip().strip('"').strip("'")
            if candidate and candidate not in ("null", "None"):
                return candidate.replace("\\", "/")
        # Prefer last JSON object with a receipt field.
        text = (blob or "").strip()
        if not text:
            continue
        # Try whole stdout as JSON first.
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                for key in ("receipt", "receipt_path", "json_path", "latest"):
                    val = parsed.get(key)
                    if isinstance(val, str) and val:
                        return val.replace("\\", "/")
                arts = parsed.get("artifacts")
                if isinstance(arts, dict):
                    for key in ("json", "receipt", "receipt_path"):
                        val = arts.get(key)
                        if isinstance(val, str) and val:
                            return val.replace("\\", "/")
        except json.JSONDecodeError:
            pass
        # Scan lines for JSON dicts.
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                for key in ("receipt", "receipt_path", "json_path"):
                    val = parsed.get(key)
                    if isinstance(val, str) and val:
                        return val.replace("\\", "/")
    return None


def _classify_status(
    *,
    returncode: int,
    stdout: str,
    step: SmokeStep,
) -> tuple[str, str]:
    """Map subprocess outcome → PASS/FAIL/INCONCLUSIVE + note."""
    combined = f"{stdout or ''}"
    upper = combined.upper()
    if returncode == 0:
        if "INCONCLUSIVE" in upper and "PASS" not in upper and "CANARY_PASS" not in upper:
            return "INCONCLUSIVE", "child reported INCONCLUSIVE with exit 0"
        return "PASS", "exit 0"
    if "INCONCLUSIVE" in upper:
        return "INCONCLUSIVE", f"exit {returncode}; child marked INCONCLUSIVE"
    if "SKIP" in upper and returncode in (0, 2):
        return "SKIP", f"SKELETON: exit {returncode}; child marked SKIP"
    # Plan-only surfaces that refuse unfinished execute paths are skeleton-vacant.
    if step.risk == "PLAN_ONLY" and returncode in (2, 3) and (
        "REFUS" in upper or "NOT ALLOWED" in upper or "NOT IMPLEMENTED" in upper
    ):
        return "SKIP", f"SKELETON: vacant/unfinished surface (exit {returncode})"
    return "FAIL", f"exit {returncode}"


def run_step(step: SmokeStep) -> StepResult:
    script_path = SCRIPTS_DIR / step.script
    phase_name = (
        COLD_START_PHASES.get(step.cold_start_phase)
        if step.cold_start_phase is not None
        else None
    )
    cmd = [_python(), str(script_path), *step.args]
    if not script_path.is_file():
        return StepResult(
            step_id=step.step_id,
            name=step.name,
            status="SKIP",
            seconds=0.0,
            cold_start_phase=step.cold_start_phase,
            cold_start_phase_name=phase_name,
            command=cmd,
            returncode=None,
            receipt=None,
            note=f"SKELETON: script missing: {_posix(script_path)}",
            risk=step.risk,
        )

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(VIV_ROOT),
            timeout=step.timeout_s,
            check=False,
        )
        elapsed = time.perf_counter() - t0
        status, note = _classify_status(
            returncode=proc.returncode, stdout=proc.stdout or "", step=step
        )
        if step.notes:
            note = f"{note}; {step.notes}" if note else step.notes
        receipt = _extract_receipt(proc.stdout or "", proc.stderr or "")
        return StepResult(
            step_id=step.step_id,
            name=step.name,
            status=status,
            seconds=round(elapsed, 3),
            cold_start_phase=step.cold_start_phase,
            cold_start_phase_name=phase_name,
            command=cmd,
            returncode=proc.returncode,
            receipt=receipt,
            note=note,
            risk=step.risk,
            stdout_tail=(proc.stdout or "")[-1200:],
            stderr_tail=(proc.stderr or "")[-1200:],
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - t0
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        err = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        return StepResult(
            step_id=step.step_id,
            name=step.name,
            status="FAIL",
            seconds=round(elapsed, 3),
            cold_start_phase=step.cold_start_phase,
            cold_start_phase_name=phase_name,
            command=cmd,
            returncode=None,
            receipt=_extract_receipt(out, err),
            note=f"timeout after {step.timeout_s:.0f}s (fail-closed)",
            risk=step.risk,
            stdout_tail=out[-1200:],
            stderr_tail=err[-1200:],
        )
    except OSError as exc:
        elapsed = time.perf_counter() - t0
        return StepResult(
            step_id=step.step_id,
            name=step.name,
            status="FAIL",
            seconds=round(elapsed, 3),
            cold_start_phase=step.cold_start_phase,
            cold_start_phase_name=phase_name,
            command=cmd,
            returncode=None,
            receipt=None,
            note=f"OSError: {exc}",
            risk=step.risk,
        )


def aggregate_verdict(results: list[StepResult]) -> str:
    """Skeleton aggregation.

    - Any hard FAIL → FAIL (present surface did not respond safely).
    - SKIP (including SKELETON vacant slots) allowed alongside PASS.
    - Overall PASS = at least one PASS and no FAIL/INCONCLUSIVE.
    - All-SKIP or empty → INCONCLUSIVE (skeleton did not walk).
    """
    statuses = {r.status for r in results}
    if "FAIL" in statuses:
        return "FAIL"
    if not results:
        return "INCONCLUSIVE"
    if "INCONCLUSIVE" in statuses:
        return "INCONCLUSIVE"
    if "PASS" in statuses and statuses <= {"PASS", "SKIP"}:
        return "PASS"
    if statuses <= {"SKIP"}:
        return "INCONCLUSIVE"
    return "INCONCLUSIVE"


def run_smoke(*, stamp: str | None = None) -> dict[str, Any]:
    stamp = stamp or _utc_stamp()
    started = _utc_iso()
    t0 = time.perf_counter()
    results: list[StepResult] = []
    for step in SMOKE_CATALOG:
        # Soft budget: if already past target and remaining steps are optional
        # contract extras, still run them — catalog is sized for ~3–5 min.
        result = run_step(step)
        results.append(result)
    wall_s = round(time.perf_counter() - t0, 3)
    verdict = aggregate_verdict(results)
    counts = {
        "PASS": sum(1 for r in results if r.status == "PASS"),
        "FAIL": sum(1 for r in results if r.status == "FAIL"),
        "SKIP": sum(1 for r in results if r.status == "SKIP"),
        "INCONCLUSIVE": sum(1 for r in results if r.status == "INCONCLUSIVE"),
    }
    skeleton_skips = [
        r.step_id for r in results if r.status == "SKIP" and "SKELETON" in (r.note or "")
    ]
    payload: dict[str, Any] = {
        "ok": verdict == "PASS",
        "verdict": verdict,
        "schema_version": SCHEMA_VERSION,
        "module": MODULE_ID,
        "version": VERSION,
        "smoke_kind": SMOKE_KIND,
        "purpose": (
            "Prove skeleton orchestration + safe surfaces respond; "
            "not a claim that every core is finished"
        ),
        "stamp": stamp,
        "started_at": started,
        "finished_at": _utc_iso(),
        "wall_seconds": wall_s,
        "target_wall_s": TARGET_WALL_S,
        "within_target_wall": wall_s <= TARGET_WALL_S,
        "counts": counts,
        "skeleton_skips": skeleton_skips,
        "steps": [asdict(r) for r in results],
        "constraints": {
            "aios_runtime_started": False,
            "gpu_long_launched": False,
            "plant_stress_120s": False,
            "backup_vault_copy": False,
            "soft_0_99": False,
            "fail_closed_on_hard_fail": True,
            "skeleton_skip_ok": True,
        },
        "canary_flags": {
            "field_scoped_bridge_canary": "--enable-canary --no-append-thesis",
            "default": "OFF",
            "reference_pass": (
                "L:/Continue/Viv/foundation/artifacts/auto/field_scoped_bridge_canary/"
                "20260807T092420Z/field_scoped_bridge_canary_v1_20260807T092420Z.json"
            ),
            "note": "bounded canary included (restored CANARY_PASS 64/64); no soft-0.99",
        },
        "receipts_root": _posix(RECEIPTS_ROOT),
        "cold_start_phases": COLD_START_PHASES,
        "plan": {
            "step_ids": [s.step_id for s in SMOKE_CATALOG],
            "excluded_execute_safe": True,
        },
    }
    return payload


def write_receipt(payload: dict[str, Any], *, stamp: str | None = None) -> Path:
    stamp = stamp or str(payload.get("stamp") or _utc_stamp())
    folder = RECEIPTS_ROOT / stamp
    folder.mkdir(parents=True, exist_ok=True)
    body = dict(payload)
    body["stamp"] = stamp
    body.setdefault("receipt_root", _posix(RECEIPTS_ROOT))
    json_path = folder / f"system_smoke_v1_{stamp}.json"
    md_path = folder / f"system_smoke_v1_{stamp}.md"
    json_path.write_text(
        json.dumps(body, indent=2, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_render_md(body), encoding="utf-8")
    latest = RECEIPTS_ROOT / "LATEST.json"
    latest.write_text(
        json.dumps(body, indent=2, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )
    body["receipt"] = _posix(json_path)
    body["receipt_md"] = _posix(md_path)
    body["latest"] = _posix(latest)
    # Rewrite with receipt paths embedded.
    json_path.write_text(
        json.dumps(body, indent=2, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )
    latest.write_text(
        json.dumps(body, indent=2, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )
    return json_path


def _render_md(body: dict[str, Any]) -> str:
    lines = [
        f"# AIOS system skeleton smoke `{body.get('stamp')}`",
        "",
        f"- Kind: `{body.get('smoke_kind', SMOKE_KIND)}`",
        f"- Verdict: **{body.get('verdict')}**",
        f"- Purpose: {body.get('purpose') or 'skeleton walks'}",
        f"- Wall seconds: `{body.get('wall_seconds')}` (target ≤ `{body.get('target_wall_s')}`)",
        f"- Counts: `{json.dumps(body.get('counts') or {})}`",
        f"- SKELETON skips: `{body.get('skeleton_skips') or []}`",
        f"- AIOS started: `{((body.get('constraints') or {}).get('aios_runtime_started'))}`",
        f"- GPU_LONG: `{((body.get('constraints') or {}).get('gpu_long_launched'))}`",
        f"- soft-0.99: `{((body.get('constraints') or {}).get('soft_0_99'))}`",
        "",
        "## Steps",
        "",
        "| Step | Phase | Status | Seconds | Receipt / note |",
        "|---|---:|---|---:|---|",
    ]
    for step in body.get("steps") or []:
        phase = step.get("cold_start_phase")
        phase_s = "" if phase is None else str(phase)
        note = step.get("receipt") or step.get("note") or ""
        note = str(note).replace("|", "\\|")[:160]
        lines.append(
            f"| `{step.get('step_id')}` | {phase_s} | {step.get('status')} | "
            f"{step.get('seconds')} | {note} |"
        )
    lines.extend(["", "## Re-run", "", "```powershell",
                  r'$py = "L:\Continue\.venv\Scripts\python.exe"',
                  r"& $py foundation\scripts\run_aios_system_smoke_v1.py",
                  "```", ""])
    return "\n".join(lines)


def format_human_table(results: list[dict[str, Any]] | list[StepResult]) -> str:
    rows = []
    for r in results:
        if isinstance(r, StepResult):
            d = asdict(r)
        else:
            d = r
        rows.append(
            f"{d.get('status', '?'):<12} {float(d.get('seconds') or 0):7.3f}s  "
            f"P{d.get('cold_start_phase') if d.get('cold_start_phase') is not None else '-'}  "
            f"{d.get('step_id')}  "
            f"{(d.get('receipt') or d.get('note') or '')[:100]}"
        )
    header = f"{'STATUS':<12} {'SECONDS':>8}  PHASE  STEP"
    return header + "\n" + "-" * 72 + "\n" + "\n".join(rows)


__all__ = [
    "COLD_START_PHASES",
    "PYTHON",
    "RECEIPTS_ROOT",
    "SCHEMA_VERSION",
    "SMOKE_CATALOG",
    "SMOKE_KIND",
    "SmokeStep",
    "StepResult",
    "TARGET_WALL_S",
    "aggregate_verdict",
    "format_human_table",
    "plan_catalog",
    "run_smoke",
    "run_step",
    "write_receipt",
]
