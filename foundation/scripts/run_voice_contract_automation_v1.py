#!/usr/bin/env python3
"""Voice/mouth contract verification automation (CPU-owned speak path).

Measurement/plan surface for Phase-3 voice contract checks. Runs existing fast
unit/contract selftests via subprocess and aggregates a pass/fail receipt.

Never starts the live voice server, never starts AIOS, never launches GPU
training, and never starts ``voice_core.stub_server`` (long-lived). OpenAster
parity stays offline soft-fail only.

Examples:

    L:\\Continue\\.venv\\Scripts\\python.exe foundation\\scripts\\run_voice_contract_automation_v1.py --profile contracts --plan-only
    L:\\Continue\\.venv\\Scripts\\python.exe foundation\\scripts\\run_voice_contract_automation_v1.py --profile contracts
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
VIV = FOUNDATION.parent
SCRIPTS = FOUNDATION / "scripts"
RECEIPTS_ROOT = FOUNDATION / "artifacts" / "auto" / "voice_contract_automation"
PYTHON = Path(r"L:\Continue\.venv\Scripts\python.exe")
SCHEMA_VERSION = "viv_voice_contract_automation_receipt_v1"
DEFAULT_TIMEOUT_S = 120

# Fast CPU-owned speak-path / mouth contract selftests only.
# Do not add GPU training, live mouth eval, or long-running stub servers here.
CONTRACT_TESTS: tuple[dict[str, Any], ...] = (
    {
        "id": "cpu_mouth_render_contract_v1",
        "script": "test_cpu_mouth_render_contract_v1.py",
        "surface": "lib.cpu_mouth_contract + voice_core.speak finalize seam",
        "timeout_s": 90,
    },
    {
        "id": "openaster_parity_contracts",
        "script": "test_openaster_parity_contracts.py",
        "surface": "OpenAster train/runtime parity (offline soft-fail speak)",
        "timeout_s": 120,
    },
    {
        "id": "mouth_contract_fallback_v1",
        "script": "test_mouth_contract_fallback_v1.py",
        "surface": "deterministic_speak query-conditioned fallback",
        "timeout_s": 60,
    },
    {
        "id": "runtime_contract_v1",
        "script": "test_runtime_contract_v1.py",
        "surface": "voice_core.runtime_contract query gates",
        "timeout_s": 60,
    },
    {
        "id": "runtime_semantic_leakage_v1",
        "script": "test_runtime_semantic_leakage_v1.py",
        "surface": "ordinary-mode telemetry disclosure containment",
        "timeout_s": 60,
    },
    {
        "id": "acronym_registry_contract_v1",
        "script": "test_acronym_registry_contract_v1.py",
        "surface": "CPU-owned acronym repair/validate",
        "timeout_s": 60,
    },
    {
        "id": "mouth_acronym_contract_v1",
        "script": "test_mouth_acronym_contract_v1.py",
        "surface": "acronym/identity presentation contract",
        "timeout_s": 90,
    },
    {
        "id": "mouth_security_out_acronym_contract_v1",
        "script": "test_mouth_security_out_acronym_contract_v1.py",
        "surface": "Security OUT acronym withhold path",
        "timeout_s": 60,
    },
)

PROFILES = {
    "contracts": {
        "description": "Fast CPU unit/contract tests for the owned speak/mouth path.",
        "tests": tuple(row["id"] for row in CONTRACT_TESTS),
        "starts_voice_server": False,
        "starts_aios": False,
        "starts_stub_server": False,
        "gpu_training": False,
    }
}


def _utc_stamp() -> str:
    # Millisecond suffix avoids collisions when plan+execute run in the same second.
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond // 1000:03d}Z"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _python() -> str:
    return str(PYTHON if PYTHON.is_file() else sys.executable)


def _child_env() -> dict[str, str]:
    """Ensure foundation/lib and Viv imports resolve without starting any servers."""
    env = dict(os.environ)
    path_parts = [str(FOUNDATION), str(VIV), str(SCRIPTS)]
    existing = env.get("PYTHONPATH", "")
    if existing:
        path_parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(path_parts)
    return env


def _print(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=True, default=str)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def _test_by_id(test_id: str) -> dict[str, Any]:
    for row in CONTRACT_TESTS:
        if row["id"] == test_id:
            return row
    raise KeyError(test_id)


def _command_for(test: dict[str, Any]) -> list[str]:
    return [_python(), "-B", str(SCRIPTS / test["script"])]


def plan_profile(profile_id: str) -> dict[str, Any]:
    profile = PROFILES[profile_id]
    planned = []
    missing = []
    for test_id in profile["tests"]:
        test = _test_by_id(test_id)
        script_path = SCRIPTS / test["script"]
        cmd = _command_for(test)
        row = {
            "id": test["id"],
            "script": test["script"],
            "script_path": str(script_path).replace("\\", "/"),
            "exists": script_path.is_file(),
            "surface": test["surface"],
            "timeout_s": int(test.get("timeout_s") or DEFAULT_TIMEOUT_S),
            "command": cmd,
        }
        planned.append(row)
        if not row["exists"]:
            missing.append(test["script"])
    return {
        "ok": not missing,
        "profile": profile_id,
        "description": profile["description"],
        "test_count": len(planned),
        "tests": planned,
        "missing_scripts": missing,
        "starts_voice_server": False,
        "starts_aios": False,
        "starts_stub_server": False,
        "gpu_training": False,
        "notes": [
            "Subprocess unit/contract selftests only.",
            "OpenAster parity uses offline soft-fail speak_completion (port unreachable).",
            "voice_core.stub_server is intentionally not started.",
        ],
    }


def _run_one(test: dict[str, Any]) -> dict[str, Any]:
    script_path = SCRIPTS / test["script"]
    cmd = _command_for(test)
    timeout_s = int(test.get("timeout_s") or DEFAULT_TIMEOUT_S)
    if not script_path.is_file():
        return {
            "id": test["id"],
            "ok": False,
            "skipped": True,
            "reason": "script_missing",
            "script": test["script"],
            "command": cmd,
            "returncode": None,
            "elapsed_seconds": 0.0,
            "stdout_tail": "",
            "stderr_tail": "",
        }
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(FOUNDATION),
            env=_child_env(),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        elapsed = round(time.perf_counter() - started, 3)
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        return {
            "id": test["id"],
            "ok": proc.returncode == 0,
            "skipped": False,
            "script": test["script"],
            "surface": test["surface"],
            "command": cmd,
            "returncode": proc.returncode,
            "elapsed_seconds": elapsed,
            "timeout_s": timeout_s,
            "stdout_tail": stdout[-2000:],
            "stderr_tail": stderr[-1000:],
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = round(time.perf_counter() - started, 3)
        return {
            "id": test["id"],
            "ok": False,
            "skipped": False,
            "reason": "timeout",
            "script": test["script"],
            "command": cmd,
            "returncode": None,
            "elapsed_seconds": elapsed,
            "timeout_s": timeout_s,
            "stdout_tail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-1000:] if isinstance(exc.stderr, str) else "",
        }


def run_contracts() -> dict[str, Any]:
    plan = plan_profile("contracts")
    results = [_run_one(_test_by_id(test_id)) for test_id in PROFILES["contracts"]["tests"]]
    passed = sum(1 for row in results if row.get("ok"))
    failed = [row["id"] for row in results if not row.get("ok")]
    return {
        "ok": plan["ok"] and not failed,
        "profile": "contracts",
        "plan": plan,
        "results": results,
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": len(failed),
            "failed_ids": failed,
            "elapsed_seconds_total": round(sum(float(r.get("elapsed_seconds") or 0) for r in results), 3),
        },
        "starts_voice_server": False,
        "starts_aios": False,
        "starts_stub_server": False,
        "gpu_training": False,
    }


def write_receipt(stamp: str, payload: dict[str, Any]) -> Path:
    folder = RECEIPTS_ROOT / stamp
    folder.mkdir(parents=True, exist_ok=True)
    body = dict(payload)
    body.setdefault("schema_version", SCHEMA_VERSION)
    body.setdefault("created_at", _utc_now().isoformat())
    body.setdefault("stamp", stamp)
    body.setdefault("module", "voice_contract_automation_v1")
    body.setdefault("aios_runtime_started", False)
    body.setdefault("voice_server_started", False)
    body.setdefault("stub_server_started", False)
    body.setdefault("gpu_training", False)
    path = folder / "RECEIPT.json"
    path.write_text(
        json.dumps(body, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    summary = body.get("summary") or {}
    md_lines = [
        f"# voice contract automation receipt `{stamp}`",
        "",
        f"- ok: `{body.get('ok')}`",
        f"- mode: `{body.get('mode')}`",
        f"- profile: `{body.get('profile')}`",
        f"- passed: `{summary.get('passed')}` / `{summary.get('total')}`",
        f"- failed_ids: `{summary.get('failed_ids')}`",
        f"- aios_runtime_started: `{body.get('aios_runtime_started')}`",
        f"- voice_server_started: `{body.get('voice_server_started')}`",
        f"- stub_server_started: `{body.get('stub_server_started')}`",
        f"- gpu_training: `{body.get('gpu_training')}`",
        "",
        "## Summary JSON",
        "",
        "```json",
        json.dumps(
            {
                "ok": body.get("ok"),
                "mode": body.get("mode"),
                "profile": body.get("profile"),
                "summary": summary,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        "```",
        "",
    ]
    results = body.get("results") or []
    if results:
        md_lines.extend(["## Test results", ""])
        for row in results:
            md_lines.append(
                f"- `{row.get('id')}`: ok=`{row.get('ok')}` "
                f"rc=`{row.get('returncode')}` elapsed_s=`{row.get('elapsed_seconds')}`"
            )
        md_lines.append("")
    (folder / "RECEIPT.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8", newline="\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES.keys()),
        default="contracts",
        help="Automation profile (default: contracts).",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="List tests/commands for the profile; do not execute.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List profiles and exit.",
    )
    args = parser.parse_args(argv)
    stamp = _utc_stamp()

    if args.list:
        payload = {
            "ok": True,
            "receipts_root": str(RECEIPTS_ROOT).replace("\\", "/"),
            "profiles": [
                {
                    "profile_id": pid,
                    "description": meta["description"],
                    "test_count": len(meta["tests"]),
                    "tests": list(meta["tests"]),
                    "starts_voice_server": False,
                    "starts_aios": False,
                    "gpu_training": False,
                }
                for pid, meta in PROFILES.items()
            ],
        }
        _print(payload)
        return 0

    if args.plan_only:
        plan = plan_profile(args.profile)
        receipt = {
            "ok": bool(plan.get("ok")),
            "mode": "plan_only",
            "profile": args.profile,
            "stamp": stamp,
            "plan": plan,
            "summary": {
                "total": plan.get("test_count"),
                "passed": None,
                "failed": None,
                "failed_ids": [],
            },
            "results": [],
            "aios_runtime_started": False,
            "voice_server_started": False,
            "stub_server_started": False,
            "gpu_training": False,
        }
        path = write_receipt(stamp, receipt)
        _print(
            {
                "ok": receipt["ok"],
                "receipt": str(path).replace("\\", "/"),
                "mode": "plan_only",
                "profile": args.profile,
                "test_count": plan.get("test_count"),
                "tests": [
                    {
                        "id": t["id"],
                        "exists": t["exists"],
                        "command": t["command"],
                        "timeout_s": t["timeout_s"],
                    }
                    for t in plan.get("tests") or []
                ],
                "missing_scripts": plan.get("missing_scripts"),
                "aios_runtime_started": False,
                "voice_server_started": False,
                "gpu_training": False,
            }
        )
        return 0 if receipt["ok"] else 1

    if args.profile != "contracts":
        _print({"ok": False, "error": "unknown_or_unsupported_profile", "profile": args.profile})
        return 2

    result = run_contracts()
    receipt = {
        "ok": bool(result.get("ok")),
        "mode": "execute",
        "profile": "contracts",
        "stamp": stamp,
        "plan": result.get("plan"),
        "results": result.get("results"),
        "summary": result.get("summary"),
        "aios_runtime_started": False,
        "voice_server_started": False,
        "stub_server_started": False,
        "gpu_training": False,
    }
    path = write_receipt(stamp, receipt)
    summary = result.get("summary") or {}
    _print(
        {
            "ok": receipt["ok"],
            "receipt": str(path).replace("\\", "/"),
            "mode": "execute",
            "profile": "contracts",
            "summary": summary,
            "failed_ids": summary.get("failed_ids") or [],
            "aios_runtime_started": False,
            "voice_server_started": False,
            "stub_server_started": False,
            "gpu_training": False,
        }
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
