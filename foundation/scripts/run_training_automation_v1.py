#!/usr/bin/env python3
"""Safe UML / Viv-SLM training control-plane orchestrator (receipt-producing).

Discovers and plans training/eval jobs under test_training + MASTER_TRAINING_PROGRAM.
Default actions are measurement-only or CPU-safe. Full heldout / blend / train loops
never auto-run without ``--i-understand-gpu-long``.

Does not start/stop AIOS, does not promote checkpoints, and does not launch
multi-hour trains.

---------------------------------------------------------------------------
AIOS core integration hook (docstring only — for future run_aios_core_automation_v1.py)
---------------------------------------------------------------------------
Invoke as a bounded child profile from the future AIOS core orchestrator:

  L:/Continue/.venv/Scripts/python.exe -B foundation/scripts/run_training_automation_v1.py --profile uml_status

Or import:

  from lib.training_automation_v1 import collect_uml_status, catalog_jobs, plan_job

AIOS core should call ``uml_status`` (and optionally ``uml_smoke``) on a schedule.
It must NEVER schedule ``GPU_LONG`` jobs unless the operator explicitly passes
``--i-understand-gpu-long`` and MASTER_TRAINING_PROGRAM authority is open.
Receipts: foundation/artifacts/auto/training_automation/<stamp>/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.training_automation_v1 import (  # noqa: E402
    AIOS_CORE_INTEGRATION_HOOK,
    RISK_GPU_LONG,
    SCHEMA_CATALOG,
    _utc_stamp,
    catalog_jobs,
    collect_uml_status,
    gate_gpu_long,
    get_job,
    plan_job,
    run_uml_smoke,
    write_receipt,
)


def _print(payload: dict) -> None:
    # Windows consoles are often cp1252; keep stdout ASCII-safe JSON.
    text = json.dumps(payload, indent=2, ensure_ascii=True)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        action="store_true",
        help="List runnable training/eval jobs with risk tags.",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Expand --job to exact commands + paths + expected receipts (no execute).",
    )
    parser.add_argument(
        "--job",
        default=None,
        help="Job id for --plan-only (or gated GPU_LONG execute planning).",
    )
    parser.add_argument(
        "--profile",
        choices=("uml_status", "uml_smoke"),
        default=None,
        help="uml_status=measurement-only; uml_smoke=short pre-existing selftest if <2m.",
    )
    parser.add_argument(
        "--i-understand-gpu-long",
        action="store_true",
        help=(
            "Operator gate required before any GPU_LONG job is allowed to execute. "
            "This orchestrator still refuses auto-launch of GPU_LONG from profiles; "
            "use --plan-only to inspect those jobs."
        ),
    )
    parser.add_argument(
        "--show-integration-hook",
        action="store_true",
        help="Print the AIOS core integration hook text and exit.",
    )
    args = parser.parse_args(argv)
    stamp = _utc_stamp()

    if args.show_integration_hook:
        print(AIOS_CORE_INTEGRATION_HOOK)
        return 0

    if args.catalog:
        jobs = catalog_jobs()
        receipt = {
            "ok": True,
            "mode": "catalog",
            "profile": None,
            "stamp": stamp,
            "schema_catalog": SCHEMA_CATALOG,
            "job_count": len(jobs),
            "jobs": [
                {
                    "id": j["id"],
                    "title": j["title"],
                    "risk": j["risk"],
                    "auto_execute": j.get("auto_execute"),
                    "requires_gpu_long_gate": j.get("requires_gpu_long_gate"),
                    "notes": j.get("notes"),
                }
                for j in jobs
            ],
            "smoke_ran": False,
            "gpu_train_launched": False,
            "risk_counts": {
                "GPU_LONG": sum(1 for j in jobs if j["risk"] == RISK_GPU_LONG),
                "CPU_SAFE": sum(1 for j in jobs if j["risk"] == "CPU_SAFE"),
                "MEASUREMENT_ONLY": sum(1 for j in jobs if j["risk"] == "MEASUREMENT_ONLY"),
            },
        }
        path = write_receipt(stamp, receipt)
        out = {
            "ok": True,
            "receipt": str(path).replace("\\", "/"),
            "job_count": receipt["job_count"],
            "risk_counts": receipt["risk_counts"],
            "jobs": receipt["jobs"],
        }
        _print(out)
        return 0

    if args.plan_only:
        if not args.job:
            parser.error("--plan-only requires --job <id>")
        try:
            plan = plan_job(args.job)
        except KeyError as exc:
            _print({"ok": False, "error": str(exc)})
            return 2
        gate = gate_gpu_long(args.job, i_understand_gpu_long=bool(args.i_understand_gpu_long))
        plan["gpu_long_gate"] = gate
        # plan-only never executes, even with the GPU gate.
        plan["execution_approved"] = False
        receipt = {
            "ok": True,
            "mode": "plan_only",
            "profile": None,
            "job_id": args.job,
            "stamp": stamp,
            "plan": plan,
            "smoke_ran": False,
            "gpu_train_launched": False,
        }
        path = write_receipt(stamp, receipt)
        _print({"ok": True, "receipt": str(path).replace("\\", "/"), "plan": plan})
        return 0

    if args.profile == "uml_status":
        status = collect_uml_status()
        receipt = {
            "ok": bool(status.get("ok")),
            "mode": "execute",
            "profile": "uml_status",
            "stamp": stamp,
            "status": status,
            "survivor_sha256": (status.get("survivor") or {}).get("sha256"),
            "thesis_ladder_tip": (status.get("thesis_ladder_tip") or {}).get("tip_line"),
            "smoke_ran": False,
            "gpu_train_launched": False,
        }
        path = write_receipt(stamp, receipt)
        _print(
            {
                "ok": receipt["ok"],
                "receipt": str(path).replace("\\", "/"),
                "profile": "uml_status",
                "survivor_sha256": receipt["survivor_sha256"],
                "thesis_ladder_tip": receipt["thesis_ladder_tip"],
                "last_evidence_snapshot": (status.get("last_evidence_snapshot") or {}).get(
                    "snapshot_id"
                ),
                "last_backup_receipt": (status.get("last_backup_receipt") or {}).get(
                    "receipt_path"
                ),
                "smoke_ran": False,
                "gpu_train_launched": False,
            }
        )
        return 0 if receipt["ok"] else 1

    if args.profile == "uml_smoke":
        # Never promote GPU_LONG via smoke profile, gate or not.
        result = run_uml_smoke()
        status = collect_uml_status()
        receipt = {
            "ok": bool(result.get("ok")),
            "mode": "execute",
            "profile": "uml_smoke",
            "stamp": stamp,
            "smoke": result,
            "smoke_ran": bool(result.get("smoke_ran")),
            "status_snapshot": {
                "survivor_sha256": (status.get("survivor") or {}).get("sha256"),
                "thesis_ladder_tip": (status.get("thesis_ladder_tip") or {}).get("tip_line"),
            },
            "gpu_train_launched": False,
            "skipped": bool(result.get("skipped")),
            "skip_reason": result.get("reason"),
        }
        path = write_receipt(stamp, receipt)
        _print(
            {
                "ok": receipt["ok"],
                "receipt": str(path).replace("\\", "/"),
                "profile": "uml_smoke",
                "smoke_ran": receipt["smoke_ran"],
                "skipped": receipt["skipped"],
                "skip_reason": receipt.get("skip_reason"),
                "elapsed_seconds": result.get("elapsed_seconds"),
                "gpu_train_launched": False,
            }
        )
        # Skipped-with-documentation is a successful safe outcome.
        if result.get("skipped") and result.get("reason"):
            return 0
        return 0 if receipt["ok"] else 1

    # Explicit job execute path: only CPU_SAFE / MEASUREMENT jobs without GPU gate.
    # GPU_LONG always blocked from auto-execute here (plan-only + gate for visibility).
    if args.job:
        try:
            job = get_job(args.job)
        except KeyError as exc:
            _print({"ok": False, "error": str(exc)})
            return 2
        if job.get("requires_gpu_long_gate") or job.get("risk") == RISK_GPU_LONG:
            gate = gate_gpu_long(args.job, i_understand_gpu_long=bool(args.i_understand_gpu_long))
            receipt = {
                "ok": False,
                "mode": "blocked",
                "profile": None,
                "job_id": args.job,
                "stamp": stamp,
                "gpu_long_gate": gate,
                "plan": plan_job(args.job),
                "smoke_ran": False,
                "gpu_train_launched": False,
                "error": (
                    "GPU_LONG jobs are never auto-executed by this orchestrator; "
                    "use --plan-only. Even with --i-understand-gpu-long, run the "
                    "underlying script manually after authority is open."
                ),
            }
            path = write_receipt(stamp, receipt)
            _print(
                {
                    "ok": False,
                    "receipt": str(path).replace("\\", "/"),
                    "error": receipt["error"],
                    "gpu_long_gate": gate,
                }
            )
            return 3
        if args.job == "uml_status":
            return main(["--profile", "uml_status"])
        if args.job == "uml_speak_cheap_census_selftest":
            return main(["--profile", "uml_smoke"])
        plan = plan_job(args.job)
        receipt = {
            "ok": True,
            "mode": "plan_only_fallback",
            "job_id": args.job,
            "stamp": stamp,
            "plan": plan,
            "smoke_ran": False,
            "gpu_train_launched": False,
            "notes": (
                "Non-profile jobs default to plan-only in this orchestrator; "
                "execute underlying scripts deliberately."
            ),
        }
        path = write_receipt(stamp, receipt)
        _print({"ok": True, "receipt": str(path).replace("\\", "/"), "plan": plan})
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
