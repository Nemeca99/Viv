"""Bounded RID / plant foundation automation (plan-first, RID-first).

Aligns with COLD_START Phase 1 and FOUNDATION_ROADMAP: RID owns plant math
and captures. This control plane never starts AIOS, never runs 120s stress
captures automatically, and never mutates plant_runtime torch globals.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
PYTHON = FOUNDATION.parent.parent / ".venv" / "Scripts" / "python.exe"
RID_MAIN = FOUNDATION / "rid_main.py"
RECEIPTS_ROOT = FOUNDATION / "artifacts" / "auto" / "rid_plant_automation"

VIV_SLM_MODEL = (
    FOUNDATION
    / "models"
    / "Training"
    / "current"
    / "viv_slm"
    / "model"
)
PLANT_RUNTIME_PATH = VIV_SLM_MODEL / "plant_runtime.py"
RID_PID_PATH = VIV_SLM_MODEL / "rid_pid.py"

SCHEMA_RECEIPT = "viv_rid_plant_automation_receipt_v1"
SCHEMA_PLAN = "viv_rid_plant_automation_plan_v1"

PROFILE_HEALTH_QUICK = "health_quick"
PROFILES = (PROFILE_HEALTH_QUICK,)

HEALTH_QUICK_BUDGET_S = 60.0
LONG_PLANT_SECONDS = 120

# Documented only — never auto-executed by this orchestrator.
LONG_PLANT_COMMAND = [
    str(PYTHON).replace("\\", "/"),
    "-B",
    str(RID_MAIN).replace("\\", "/"),
    "stability",
    "--stress",
    "--seconds",
    str(LONG_PLANT_SECONDS),
]


def _posix(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_stamp() -> str:
    now = _utc_now()
    return now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond // 1000:03d}Z"


def _utc_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def list_profiles() -> list[dict[str, Any]]:
    return [
        {
            "profile_id": PROFILE_HEALTH_QUICK,
            "title": "Short non-stress foundation / RID status (<60s)",
            "default_mode": "plan_only",
            "execute_allowed": True,
            "include_stress": False,
            "long_plant_auto": False,
            "budget_s": HEALTH_QUICK_BUDGET_S,
            "notes": (
                "Runs evaluate_foundation_gate(stress=off), rid adapter status, "
                "plant S_n gate, rid_feed meta, and path/import probes for "
                "plant_runtime + rid_pid. Never starts 120s stability."
            ),
        }
    ]


def long_plant_gate(*, i_understand_long_plant: bool) -> dict[str, Any]:
    """120s stress is never auto-run; flag only unlocks documented command."""
    if not i_understand_long_plant:
        return {
            "ok": True,
            "allowed_to_document": False,
            "auto_execute": False,
            "status": "SKIP",
            "reason": "missing --i-understand-long-plant",
            "command": None,
            "seconds": LONG_PLANT_SECONDS,
            "note": (
                "Foundation proof captures remain operator-owned. "
                "See COLD_START.md safe plant proof section."
            ),
        }
    return {
        "ok": True,
        "allowed_to_document": True,
        "auto_execute": False,
        "status": "DOCUMENTED",
        "reason": (
            "Operator acknowledged long plant; command documented only "
            "(orchestrator refuses auto-run of 120s stress)."
        ),
        "command": list(LONG_PLANT_COMMAND),
        "seconds": LONG_PLANT_SECONDS,
        "note": (
            "Run manually when ready; verify stress alive + poll sidecar "
            "before promoting verdict."
        ),
    }


def plan_health_quick(*, i_understand_long_plant: bool = False) -> dict[str, Any]:
    """Expand exact checks/commands without executing."""
    long_gate = long_plant_gate(i_understand_long_plant=i_understand_long_plant)
    checks = [
        {
            "id": "foundation_health_gate",
            "kind": "lib",
            "call": "lib.foundation_health.evaluate_foundation_gate(include_stress=False)",
            "include_stress": False,
            "expected_wall_s": 5,
        },
        {
            "id": "rid_adapter_status",
            "kind": "lib",
            "call": "lib.aios_adapter_rid.status()",
            "expected_wall_s": 2,
        },
        {
            "id": "rid_adapter_snapshot",
            "kind": "lib",
            "call": "lib.aios_adapter_rid.snapshot()",
            "expected_wall_s": 5,
            "optional": True,
        },
        {
            "id": "uml_plant_sn_gate",
            "kind": "lib",
            "call": "lib.uml_plant_sn_gate.read_plant_sn + dose_decision",
            "expected_wall_s": 2,
        },
        {
            "id": "rid_feed_meta",
            "kind": "lib",
            "call": "lib.rid_feed.feed_meta()",
            "expected_wall_s": 1,
        },
        {
            "id": "plant_runtime_probe",
            "kind": "path",
            "path": _posix(PLANT_RUNTIME_PATH),
            "note": "path/import presence only; no configure_plant_runtime()",
            "expected_wall_s": 5,
        },
        {
            "id": "rid_pid_probe",
            "kind": "path",
            "path": _posix(RID_PID_PATH),
            "note": "import rid_fold smoke; no training loop",
            "expected_wall_s": 5,
        },
        {
            "id": "rid_main_status_cmd",
            "kind": "documented_command",
            "command": [
                _posix(PYTHON),
                "-B",
                _posix(RID_MAIN),
                "status",
                "--json",
            ],
            "auto_execute": False,
            "expected_wall_s": 5,
        },
    ]
    return {
        "schema_version": SCHEMA_PLAN,
        "ok": True,
        "profile": PROFILE_HEALTH_QUICK,
        "mode": "plan_only",
        "execution_approved": False,
        "budget_s": HEALTH_QUICK_BUDGET_S,
        "include_stress": False,
        "aios_runtime_started": False,
        "long_plant_started": False,
        "checks": checks,
        "long_plant": long_gate,
        "documented_commands": {
            "rid_status": [
                _posix(PYTHON),
                "-B",
                _posix(RID_MAIN),
                "status",
                "--json",
            ],
            "rid_health_no_stress": [
                _posix(PYTHON),
                "-B",
                _posix(RID_MAIN),
                "health",
                "--json",
            ],
            "foundation_health_script_note": (
                "scripts/foundation_health.py defaults include_stress=True; "
                "prefer lib evaluate_foundation_gate(include_stress=False) "
                "or rid_main.py health without --stress for quick gates."
            ),
            "long_plant_120s": long_gate.get("command"),
        },
        "constraints": [
            "no_aios_start_stop",
            "no_120s_stress_auto",
            "no_plant_runtime_configure",
            "rid_first_cold_start",
        ],
    }


def _ensure_viv_slm_model_path() -> None:
    root = str(VIV_SLM_MODEL)
    if root not in sys.path:
        sys.path.insert(0, root)


def _probe_plant_runtime() -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": "plant_runtime_probe",
        "path": _posix(PLANT_RUNTIME_PATH),
        "exists": PLANT_RUNTIME_PATH.is_file(),
        "configured": False,
        "ok": False,
        "status": "SKIP",
    }
    if not out["exists"]:
        out["reason"] = "plant_runtime.py missing under viv_slm/model"
        return out
    try:
        import importlib

        _ensure_viv_slm_model_path()
        # Loading may pull torch; keep bounded — do not call configure_plant_runtime.
        mod = importlib.import_module("plant_runtime")
        has_detect = callable(getattr(mod, "detect_hardware", None))
        has_configure = callable(getattr(mod, "configure_plant_runtime", None))
        out["has_detect_hardware"] = has_detect
        out["has_configure_plant_runtime"] = has_configure
        out["ok"] = bool(has_detect and has_configure)
        out["status"] = "PASS" if out["ok"] else "FAIL"
        out["reason"] = "import ok; configure_plant_runtime not invoked"
    except Exception as exc:  # noqa: BLE001
        out["status"] = "SKIP"
        out["reason"] = f"import skipped/failed: {exc}"
        out["ok"] = False
    return out


def _probe_rid_pid() -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": "rid_pid_probe",
        "path": _posix(RID_PID_PATH),
        "exists": RID_PID_PATH.is_file(),
        "ok": False,
        "status": "SKIP",
    }
    if not out["exists"]:
        out["reason"] = "rid_pid.py missing under viv_slm/model"
        return out
    try:
        import importlib

        _ensure_viv_slm_model_path()
        mod = importlib.import_module("rid_pid")
        fold = getattr(mod, "rid_fold", None)
        if not callable(fold):
            out["status"] = "FAIL"
            out["reason"] = "rid_fold missing"
            return out
        val = float(fold(1.0, 1.0, 1.0))
        out["rid_fold_111"] = val
        out["ok"] = abs(val - 1.0) < 1e-12
        out["status"] = "PASS" if out["ok"] else "FAIL"
        out["reason"] = "rid_fold(1,1,1) smoke"
    except Exception as exc:  # noqa: BLE001
        out["status"] = "SKIP"
        out["reason"] = f"import skipped/failed: {exc}"
        out["ok"] = False
    return out


def run_health_quick(*, i_understand_long_plant: bool = False) -> dict[str, Any]:
    """Execute short non-stress RID/plant checks under a 60s wall budget."""
    t0 = time.perf_counter()
    results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[str] = []
    budget = HEALTH_QUICK_BUDGET_S

    def remaining() -> float:
        return budget - (time.perf_counter() - t0)

    def record(row: dict[str, Any]) -> None:
        results.append(row)
        st = str(row.get("status") or "")
        if st == "SKIP":
            skipped.append(row)
        elif st == "FAIL" or row.get("ok") is False:
            failed.append(str(row.get("id") or "unknown"))

    # 1) Foundation gate (stress off)
    if remaining() <= 0:
        record(
            {
                "id": "foundation_health_gate",
                "ok": False,
                "status": "SKIP",
                "reason": "budget_exhausted_before_start",
            }
        )
    else:
        try:
            from lib.foundation_health import evaluate_foundation_gate

            gate = evaluate_foundation_gate(include_stress=False)
            record(
                {
                    "id": "foundation_health_gate",
                    "ok": bool(gate.get("allow")),
                    "status": "PASS" if gate.get("allow") else "FAIL",
                    "include_stress": False,
                    "failed": gate.get("failed") or [],
                    "checks": gate.get("checks") or [],
                }
            )
        except Exception as exc:  # noqa: BLE001
            record(
                {
                    "id": "foundation_health_gate",
                    "ok": False,
                    "status": "SKIP",
                    "reason": f"unavailable: {exc}",
                    "traceback": traceback.format_exc()[-1500:],
                }
            )

    # 2) RID adapter status (paths / presence)
    if remaining() <= 0:
        record(
            {
                "id": "rid_adapter_status",
                "ok": False,
                "status": "SKIP",
                "reason": "budget_exhausted",
            }
        )
    else:
        try:
            from lib.aios_adapter_rid import status as rid_status

            st = rid_status()
            evidence = st.get("evidence") or {}
            record(
                {
                    "id": "rid_adapter_status",
                    "ok": bool(st.get("ok")),
                    "status": "PASS" if st.get("ok") else "FAIL",
                    "master_s_n": evidence.get("master_s_n"),
                    "master_status": evidence.get("master_status"),
                    "last_stability_exists": evidence.get("last_stability_exists"),
                    "plant_dir_exists": evidence.get("plant_dir_exists"),
                    "read_only": evidence.get("read_only"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            record(
                {
                    "id": "rid_adapter_status",
                    "ok": False,
                    "status": "SKIP",
                    "reason": f"unavailable: {exc}",
                }
            )

    # 3) Optional live snapshot (sensors) if budget allows
    if remaining() < 2.0:
        record(
            {
                "id": "rid_adapter_snapshot",
                "ok": False,
                "status": "SKIP",
                "reason": "budget_low_skip_snapshot",
            }
        )
    else:
        try:
            from lib.aios_adapter_rid import snapshot as rid_snapshot

            snap = rid_snapshot()
            evidence = snap.get("evidence") or {}
            record(
                {
                    "id": "rid_adapter_snapshot",
                    "ok": bool(snap.get("ok")),
                    "status": "PASS" if snap.get("ok") else "FAIL",
                    "master_s_n": evidence.get("master_s_n"),
                    "status_label": evidence.get("status"),
                    "source": evidence.get("source"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            record(
                {
                    "id": "rid_adapter_snapshot",
                    "ok": False,
                    "status": "SKIP",
                    "reason": f"unavailable: {exc}",
                }
            )

    # 4) Plant S_n dose gate (read-only)
    if remaining() <= 0:
        record(
            {
                "id": "uml_plant_sn_gate",
                "ok": False,
                "status": "SKIP",
                "reason": "budget_exhausted",
            }
        )
    else:
        try:
            from lib.uml_plant_sn_gate import dose_decision, read_plant_sn

            plant = read_plant_sn()
            dose = dose_decision(base_mix=0.5, plant=plant)
            record(
                {
                    "id": "uml_plant_sn_gate",
                    "ok": True,
                    "status": "PASS",
                    "plant_available": plant.available,
                    "plant_source": plant.source,
                    "master_s_n": plant.master_s_n,
                    "dose_action": dose.get("action"),
                    "effective_mix": dose.get("effective_mix"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            record(
                {
                    "id": "uml_plant_sn_gate",
                    "ok": False,
                    "status": "SKIP",
                    "reason": f"unavailable: {exc}",
                }
            )

    # 5) RID feed meta (no pulse)
    if remaining() <= 0:
        record(
            {
                "id": "rid_feed_meta",
                "ok": False,
                "status": "SKIP",
                "reason": "budget_exhausted",
            }
        )
    else:
        try:
            from lib.rid_feed import LIVE_SAMPLE_PATH, feed_meta

            meta = feed_meta()
            record(
                {
                    "id": "rid_feed_meta",
                    "ok": True,
                    "status": "PASS",
                    "path": _posix(meta.path),
                    "age_s": meta.age_s,
                    "fresh": meta.fresh,
                    "live_sample_default": _posix(LIVE_SAMPLE_PATH),
                    "note": "meta only; pulse_once not called",
                }
            )
        except Exception as exc:  # noqa: BLE001
            record(
                {
                    "id": "rid_feed_meta",
                    "ok": False,
                    "status": "SKIP",
                    "reason": f"unavailable: {exc}",
                }
            )

    # 6–7) viv_slm plant_runtime / rid_pid probes
    if remaining() < 1.0:
        record(
            {
                "id": "plant_runtime_probe",
                "ok": False,
                "status": "SKIP",
                "reason": "budget_exhausted",
            }
        )
        record(
            {
                "id": "rid_pid_probe",
                "ok": False,
                "status": "SKIP",
                "reason": "budget_exhausted",
            }
        )
    else:
        record(_probe_plant_runtime())
        if remaining() >= 1.0:
            record(_probe_rid_pid())
        else:
            record(
                {
                    "id": "rid_pid_probe",
                    "ok": False,
                    "status": "SKIP",
                    "reason": "budget_exhausted",
                }
            )

    elapsed = time.perf_counter() - t0
    long_gate = long_plant_gate(i_understand_long_plant=i_understand_long_plant)

    # ok: ran within budget; hard FAIL on foundation/rid status only.
    hard_fail = any(
        r.get("id") in ("foundation_health_gate", "rid_adapter_status")
        and r.get("status") == "FAIL"
        for r in results
    )
    budget_ok = elapsed <= budget + 1.0  # 1s grace for scheduling jitter
    ok = (not hard_fail) and budget_ok

    return {
        "ok": ok,
        "profile": PROFILE_HEALTH_QUICK,
        "mode": "execute",
        "elapsed_s": round(elapsed, 3),
        "budget_s": budget,
        "budget_ok": budget_ok,
        "include_stress": False,
        "aios_runtime_started": False,
        "long_plant_started": False,
        "long_plant": long_gate,
        "checks": results,
        "skipped": [{"id": s.get("id"), "reason": s.get("reason")} for s in skipped],
        "failed": failed,
        "hard_fail": hard_fail,
    }


def write_receipt(payload: dict[str, Any], *, stamp: str | None = None) -> Path:
    stamp = stamp or str(payload.get("stamp") or _utc_stamp())
    folder = RECEIPTS_ROOT / stamp
    folder.mkdir(parents=True, exist_ok=True)
    body = dict(payload)
    body.setdefault("schema_version", SCHEMA_RECEIPT)
    body.setdefault("created_at", _utc_iso())
    body.setdefault("stamp", stamp)
    body.setdefault("aios_runtime_started", False)
    body.setdefault("long_plant_started", False)
    path = folder / "RECEIPT.json"
    path.write_text(
        json.dumps(body, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    md_lines = [
        f"# RID / plant automation receipt `{stamp}`",
        "",
        f"- ok: `{body.get('ok')}`",
        f"- mode: `{body.get('mode')}`",
        f"- profile: `{body.get('profile')}`",
        f"- aios_runtime_started: `{body.get('aios_runtime_started')}`",
        f"- long_plant_started: `{body.get('long_plant_started')}`",
        f"- include_stress: `{body.get('include_stress')}`",
        "",
    ]
    long_plant = body.get("long_plant") or {}
    if long_plant:
        md_lines.extend(
            [
                "## Long plant (120s)",
                "",
                f"- status: `{long_plant.get('status')}`",
                f"- auto_execute: `{long_plant.get('auto_execute')}`",
                f"- reason: {long_plant.get('reason')}",
                "",
            ]
        )
        if long_plant.get("command"):
            md_lines.append("```")
            md_lines.append(" ".join(str(c) for c in long_plant["command"]))
            md_lines.append("```")
            md_lines.append("")
    (folder / "RECEIPT.md").write_text("\n".join(md_lines), encoding="utf-8", newline="\n")
    latest = RECEIPTS_ROOT / "LATEST.json"
    latest.write_text(
        json.dumps(
            {
                "stamp": stamp,
                "receipt": _posix(path),
                "ok": body.get("ok"),
                "mode": body.get("mode"),
                "profile": body.get("profile"),
                "updated_at": _utc_iso(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def build_plan_receipt(*, i_understand_long_plant: bool = False, stamp: str | None = None) -> dict[str, Any]:
    stamp = stamp or _utc_stamp()
    plan = plan_health_quick(i_understand_long_plant=i_understand_long_plant)
    return {
        "schema_version": SCHEMA_RECEIPT,
        "created_at": _utc_iso(),
        "stamp": stamp,
        "ok": True,
        "mode": "plan_only",
        "profile": PROFILE_HEALTH_QUICK,
        "include_stress": False,
        "aios_runtime_started": False,
        "long_plant_started": False,
        "plan": plan,
        "long_plant": plan.get("long_plant"),
    }


def build_execute_receipt(
    *,
    i_understand_long_plant: bool = False,
    stamp: str | None = None,
) -> dict[str, Any]:
    stamp = stamp or _utc_stamp()
    result = run_health_quick(i_understand_long_plant=i_understand_long_plant)
    return {
        "schema_version": SCHEMA_RECEIPT,
        "created_at": _utc_iso(),
        "stamp": stamp,
        **result,
    }


__all__ = [
    "FOUNDATION",
    "HEALTH_QUICK_BUDGET_S",
    "LONG_PLANT_COMMAND",
    "LONG_PLANT_SECONDS",
    "PROFILE_HEALTH_QUICK",
    "PROFILES",
    "PYTHON",
    "RECEIPTS_ROOT",
    "SCHEMA_RECEIPT",
    "build_execute_receipt",
    "build_plan_receipt",
    "list_profiles",
    "long_plant_gate",
    "plan_health_quick",
    "run_health_quick",
    "write_receipt",
]
