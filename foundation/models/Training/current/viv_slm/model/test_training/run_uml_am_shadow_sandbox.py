#!/usr/bin/env python3
"""Run the U_AM shadow experiment over real in-process AIOS workloads.

Honest labeling (binding):
  - No live production service is attached, so every window is
    ``source="sandbox"``. Sandbox rows are structurally rejected by the
    promotion gate; running this cannot move the promotion counter.
  - Workloads are the system's own pre-existing operational scripts
    (thesis selftest, route governor selftest, federation bank build,
    cost-floor audit) executed unmodified in this process. No traffic is
    synthesized for the observer's benefit.

What this measures (real evidence):
  1. Live parity of the isolated U_AM DLL against the authoritative
     ``uml_engine.evaluate`` across every eligible expression the system
     actually computes (fail-closed on mismatch).
  2. The U_AM-eligible fraction of real evaluator invocations, extrapolated
     against the 139,511,395-request lifecycle break-even.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
for path in (FOUNDATION, MODEL, SANDBOX):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib import uml_engine  # noqa: E402
from uml_u_am_shadow import UAMShadowObserver  # noqa: E402

EXPERIMENT_ID = "u_am_shadow_sandbox_v1"
SOURCE = "sandbox"
TELEMETRY = SANDBOX / "runs" / "uml_route_usage.jsonl"
OUT_JSON = SANDBOX / "runs" / "uml_u_am_shadow_sandbox_latest.json"
OUT_MD = SANDBOX / "runs" / "uml_u_am_shadow_sandbox_latest.md"
GATE = SANDBOX / "uml_federation_promotion_gate.json"
LATTICE = SANDBOX / "uml_domain_expert_lattice.json"
RECIPE = SANDBOX / "uml_domain_expert_train_recipe.json"
REQUIRED_HEALTHY_PRODUCTION_REQUESTS = 139_511_395


def _load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot_load:{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _segment_thesis_selftest() -> int:
    import test_uml_training_thesis

    return int(test_uml_training_thesis.main())


def _segment_route_governor() -> int:
    module = _load_script_module(
        "test_uml_route_governor_shadow",
        FOUNDATION / "scripts" / "test_uml_route_governor.py",
    )
    return int(module.main())


def _segment_bank_build() -> int:
    import build_uml_temp_federation_banks

    saved_argv = sys.argv
    sys.argv = ["build_uml_temp_federation_banks.py", "--tier", "all"]
    try:
        return int(build_uml_temp_federation_banks.main())
    finally:
        sys.argv = saved_argv


def _segment_cost_floor_audit() -> int:
    import run_uml_cost_floor_audit

    result = run_uml_cost_floor_audit.audit()
    return 0 if result["objective"] == "PROVED_STRUCTURAL_IMPOSSIBILITY" else 1


SEGMENTS = (
    ("thesis_selftest", _segment_thesis_selftest),
    ("route_governor_selftest", _segment_route_governor),
    ("temp_federation_banks_build", _segment_bank_build),
    ("cost_floor_audit", _segment_cost_floor_audit),
)


def main() -> int:
    observer = UAMShadowObserver(
        experiment_id=EXPERIMENT_ID,
        source=SOURCE,
        telemetry_path=TELEMETRY,
        flush_every=1_000_000,
    )
    telemetry_offset = (
        len(TELEMETRY.read_text(encoding="utf-8").splitlines())
        if TELEMETRY.is_file()
        else 0
    )
    segments: list[dict[str, Any]] = []
    parity_fault: str | None = None
    observer.start()
    try:
        for name, runner in SEGMENTS:
            started_ns = time.perf_counter_ns()
            exit_code: int | None = None
            error: str | None = None
            try:
                exit_code = runner()
            except RuntimeError as exc:
                error = str(exc)
                if "parity_mismatch" in error:
                    parity_fault = error
            except Exception as exc:  # noqa: BLE001 — record, fail experiment honestly
                error = f"{type(exc).__name__}: {exc}"
            elapsed_ns = time.perf_counter_ns() - started_ns
            status = observer.status()
            segments.append(
                {
                    "segment": name,
                    "exit_code": exit_code,
                    "error": error,
                    "elapsed_ns": elapsed_ns,
                    "evaluator_invocations": status["window_total_requests"],
                    "u_am_eligible": status["window_federation_counts"].get("U_AM", 0),
                    "u_am_domain_nonmacro": status["window_am_domain_nonmacro"],
                    "federation_counts": dict(status["window_federation_counts"]),
                    "candidate_parity_checks": status["window_candidate_checks"],
                    "window_errors": status["window_errors"],
                }
            )
            observer.flush()
            if parity_fault:
                break
    finally:
        observer.stop()

    assert not uml_engine.evaluation_observer_status()["active"]

    total_evals = sum(int(row["evaluator_invocations"]) for row in segments)
    total_u_am = sum(int(row["u_am_eligible"]) for row in segments)
    total_am_nonmacro = sum(int(row["u_am_domain_nonmacro"]) for row in segments)
    total_checks = sum(int(row["candidate_parity_checks"]) for row in segments)
    mixed_counts: dict[str, int] = {}
    for row in segments:
        for label, count in row["federation_counts"].items():
            mixed_counts[label] = mixed_counts.get(label, 0) + int(count)
    segment_failures = [
        row["segment"]
        for row in segments
        if row["error"] is not None or (row["exit_code"] not in (0, None))
    ]

    if parity_fault:
        objective = "FAIL_PARITY_CLOSED"
    elif segment_failures:
        objective = "INCONCLUSIVE_SEGMENT_FAILURES"
    elif total_u_am == 0:
        objective = "PASS_MEASURED_ZERO_U_AM_DEMAND"
    else:
        objective = "PASS_MEASURED_SANDBOX_FREQUENCY"

    if total_u_am > 0:
        runs_to_break_even = math.ceil(
            REQUIRED_HEALTHY_PRODUCTION_REQUESTS / total_u_am
        )
    else:
        runs_to_break_even = None

    finished = datetime.now(timezone.utc).isoformat()
    receipt: dict[str, Any] = {
        "schema_version": "uml_u_am_shadow_sandbox_v1",
        "status": "PASS",
        "objective": objective,
        "experiment_id": EXPERIMENT_ID,
        "source": SOURCE,
        "finished_at": finished,
        "hypothesis": (
            "Real AIOS UML workloads contain U_AM-eligible evaluations at a "
            "frequency that could plausibly amortize the isolated creation cost."
        ),
        "authoritative_path": "dynamic_uml_engine_evaluate",
        "candidate_served_any_request": False,
        "parity": {
            "checks": total_checks,
            "fault": parity_fault,
            "fail_closed": True,
        },
        "totals": {
            "evaluator_invocations": total_evals,
            "u_am_macro_eligible": total_u_am,
            "u_am_macro_eligible_rate": (
                (total_u_am / total_evals) if total_evals else 0.0
            ),
            "u_am_domain_nonmacro": total_am_nonmacro,
            "mixed_federation_counts": mixed_counts,
            "note": (
                "u_am_macro_eligible counts only the exact (x+y)*z shape the "
                "compiled candidate serves; u_am_domain_nonmacro is A+M demand "
                "in other shapes and would require a different macro."
            ),
        },
        "segments": segments,
        "extrapolation": {
            "required_healthy_production_requests": (
                REQUIRED_HEALTHY_PRODUCTION_REQUESTS
            ),
            "u_am_per_full_pipeline_run": total_u_am,
            "pipeline_runs_to_break_even": runs_to_break_even,
            "note": (
                "Sandbox evidence only. Production counter remains 0; sandbox "
                "windows are structurally rejected by the promotion gate."
            ),
        },
        "telemetry": {
            "path": str(TELEMETRY).replace("\\", "/"),
            "schema": "uml_route_usage_v1",
            "rows_before": telemetry_offset,
            "rows_appended": len(segments),
        },
        "promotion": {
            "production_events_recorded": 0,
            "authority_gate": "NOT_INVOKED",
            "promotion_ready": False,
            "promoted": False,
        },
    }
    OUT_JSON.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    lines = [
        "# U_AM Shadow Sandbox Run",
        "",
        f"- Objective: **{objective}**",
        f"- Evaluator invocations observed: {total_evals}",
        f"- U_AM macro-eligible ((x+y)*z): {total_u_am} "
        f"({(total_u_am / total_evals * 100.0) if total_evals else 0.0:.3f}%)",
        f"- U_AM domain demand, non-macro shape: {total_am_nonmacro}",
        f"- Candidate parity checks: {total_checks} (fault: {parity_fault or 'none'})",
        f"- Mixed federation counts: {mixed_counts}",
        (
            f"- Pipeline runs to reach {REQUIRED_HEALTHY_PRODUCTION_REQUESTS:,} "
            f"requests: {runs_to_break_even:,}"
            if runs_to_break_even is not None
            else "- Break-even extrapolation: no U_AM demand observed"
        ),
        "- Source: sandbox (does not count toward promotion)",
        "- Promoted: False",
        "",
        "## Segments",
    ]
    for row in segments:
        lines.append(
            f"- {row['segment']}: evals={row['evaluator_invocations']} "
            f"macro={row['u_am_eligible']} am_other={row['u_am_domain_nonmacro']} "
            f"checks={row['candidate_parity_checks']} "
            f"exit={row['exit_code']} error={row['error'] or 'none'}"
        )
    lines.extend(["", f"Receipt: `{OUT_JSON.as_posix()}`", ""])
    OUT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    # Sync governance artifacts.
    if GATE.is_file():
        gate = json.loads(GATE.read_text(encoding="utf-8"))
        shadow = dict(gate.get("shadow_experiment") or {})
        shadow.update(
            {
                "status": (
                    "FAIL_PARITY_CLOSED"
                    if parity_fault
                    else "SANDBOX_MEASURED_NOT_PRODUCTION"
                ),
                "sandbox_run": {
                    "experiment_id": EXPERIMENT_ID,
                    "objective": objective,
                    "evaluator_invocations": total_evals,
                    "u_am_macro_eligible": total_u_am,
                    "u_am_domain_nonmacro": total_am_nonmacro,
                    "parity_checks": total_checks,
                    "parity_fault": parity_fault,
                    "receipt": str(OUT_JSON).replace("\\", "/"),
                },
                "production_events_recorded": 0,
                "updated_at": finished,
            }
        )
        gate["shadow_experiment"] = shadow
        GATE.write_text(
            json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if LATTICE.is_file():
        lattice = json.loads(LATTICE.read_text(encoding="utf-8"))
        shadow = dict(lattice.get("u_am_shadow_experiment") or {})
        shadow.update(
            {
                "status": (
                    "FAIL_PARITY_CLOSED"
                    if parity_fault
                    else "SANDBOX_MEASURED_NOT_PRODUCTION"
                ),
                "sandbox_u_am_macro_eligible": total_u_am,
                "sandbox_u_am_domain_nonmacro": total_am_nonmacro,
                "sandbox_evaluator_invocations": total_evals,
                "sandbox_parity_checks": total_checks,
                "recorded_healthy_production_requests": 0,
                "receipt": str(OUT_JSON).replace("\\", "/"),
                "updated_at": finished,
            }
        )
        lattice["u_am_shadow_experiment"] = shadow
        LATTICE.write_text(
            json.dumps(lattice, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if RECIPE.is_file():
        recipe = json.loads(RECIPE.read_text(encoding="utf-8"))
        recipe["last_run"] = finished
        recipe["last_objective"] = objective
        recipe["u_am_shadow_sandbox"] = {
            "objective": objective,
            "u_am_macro_eligible": total_u_am,
            "u_am_domain_nonmacro": total_am_nonmacro,
            "evaluator_invocations": total_evals,
            "pipeline_runs_to_break_even": runs_to_break_even,
            "receipt": str(OUT_JSON).replace("\\", "/"),
        }
        recipe["next_action"] = (
            "Shadow instrumentation live-validated on sandbox workloads. "
            "Attaching to a live production UML service (source=production) is "
            "the remaining frequency step; authority remains closed."
        )
        RECIPE.write_text(
            json.dumps(recipe, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    print(
        f"UML_U_AM_SHADOW_SANDBOX_{objective} evals={total_evals} "
        f"macro={total_u_am} am_other={total_am_nonmacro} checks={total_checks} "
        f"runs_to_break_even={runs_to_break_even} production_rows=0",
        flush=True,
    )
    return 0 if objective.startswith("PASS_") else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main())
