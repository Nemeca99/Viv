#!/usr/bin/env python3
"""U_MD shape census over real evaluator traffic — no U_MD compile.

Order (operator doctrine):
  shape census → guarded U simplifier A/B → only then U_MD service candidate

This script is step 1 only. It measures exact normalized MD shapes and whether
guarded structural reduction in U can eliminate the federation.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
FOUNDATION = HERE.parents[5]
RUNS = HERE / "runs"
sys.path.insert(0, str(FOUNDATION))
sys.path.insert(0, str(HERE))

from uml_md_shape_census import MDShapeCensusObserver  # noqa: E402

EXPERIMENT_ID = "uml_md_shape_census_v1"
SOURCE = "sandbox"


def _load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _segment_thesis_selftest() -> int:
    import test_uml_training_thesis

    return int(test_uml_training_thesis.main())


def _segment_route_governor() -> int:
    module = _load_script_module(
        "test_uml_route_governor_md_census",
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


SEGMENTS: tuple[tuple[str, Callable[[], int]], ...] = (
    ("thesis_selftest", _segment_thesis_selftest),
    ("route_governor_selftest", _segment_route_governor),
    ("temp_federation_banks_build", _segment_bank_build),
    ("cost_floor_audit", _segment_cost_floor_audit),
)


def _gate(census: dict[str, Any]) -> dict[str, Any]:
    md = int(census["md_invocations"])
    reducible = int(census["reducible_invocations"])
    share = float(census["reducible_share_of_md"])
    top = census["shapes"][:5] if census["shapes"] else []

    if md == 0:
        objective = "INCONCLUSIVE_NO_MD_TRAFFIC"
        next_step = "expand_workload_or_keep_waiting"
    elif share >= 0.50:
        objective = "PASS_MD_MOSTLY_CANONICALIZATION_DEFECT"
        next_step = "guarded_u_simplifier_ab_before_any_u_md_compile"
    elif share >= 0.10:
        objective = "PASS_MD_MIXED_REDUCIBLE_AND_IRREDUCIBLE"
        next_step = "per_shape_cost_routes_then_selective_u_md_only_if_irreducible_wins"
    else:
        objective = "PASS_MD_MOSTLY_IRREDUCIBLE"
        next_step = "isolated_u_md_service_candidate_for_top_irreducible_shapes_only"

    return {
        "objective": objective,
        "next_step": next_step,
        "md_invocations": md,
        "reducible_invocations": reducible,
        "reducible_share_of_md": share,
        "compile_u_md_now": False,
        "doctrine": (
            "Do not compile U_MD until guarded U simplification is A/B'd "
            "against dynamic U+M+D and any compiled candidate."
        ),
        "top_shapes": [
            {
                "shape": row["shape"],
                "count": row["count"],
                "class": row["class"],
                "reduction_description": row.get("reduction_description"),
            }
            for row in top
        ],
    }


def main() -> int:
    RUNS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt_path = RUNS / f"uml_md_shape_census_{stamp}.json"
    latest_path = RUNS / "uml_md_shape_census_latest.json"

    observer = MDShapeCensusObserver(experiment_id=EXPERIMENT_ID)
    observer.start()
    t0 = time.perf_counter()
    segment_results: list[dict[str, Any]] = []
    try:
        for name, fn in SEGMENTS:
            started = time.perf_counter()
            try:
                code = int(fn())
            except Exception as exc:  # noqa: BLE001
                code = 1
                err = f"{type(exc).__name__}: {exc}"
            else:
                err = None
            segment_results.append(
                {
                    "segment": name,
                    "exit_code": code,
                    "error": err,
                    "elapsed_s": round(time.perf_counter() - started, 3),
                    "md_after": observer.md_total,
                    "total_after": observer.total,
                }
            )
    finally:
        observer.stop()

    census = observer.summary()
    gate = _gate(census)
    receipt = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": EXPERIMENT_ID,
        "source": SOURCE,
        "note": (
            "Sandbox evaluator traffic — same workload family as U_AM shadow. "
            "Not production demand. No U_MD artifact compiled."
        ),
        "wall_s": round(time.perf_counter() - t0, 3),
        "segments": segment_results,
        "census": census,
        "gate": gate,
        "recommended_order": [
            "shape_census",
            "guarded_u_simplifier_ab",
            "isolated_u_md_service_candidate_only_if_needed",
            "shadow_demand",
            "authority",
        ],
        "competing_routes_for_next_phase": [
            "dynamic_U+M+D",
            "compiled_persistent_U_MD",
            "guarded_structural_reduction_in_U",
        ],
    }
    text = json.dumps(receipt, indent=2, sort_keys=True)
    receipt_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    print(json.dumps({"receipt": str(receipt_path), "gate": gate}, indent=2))
    return 0 if gate["objective"].startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
