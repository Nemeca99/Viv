#!/usr/bin/env python3
"""Measure isolated creation of the exact compiled U_AM macro artifact.

The prior 1.47B request threshold used compilation of an entire benchmark
harness. This audit compiles only ``uml_u_am_v1.rs`` as a stripped Rust cdylib,
collects >=21 samples, loads the final artifact, and verifies the route contract.

It remains a conservative process-level creation measurement (rustc startup +
compile + link + file write). Production telemetry and authority remain separate.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SANDBOX = Path(__file__).resolve().parent
SOURCE = SANDBOX / "uml_u_am_v1.rs"
RUN_DIR = SANDBOX / "runs" / "uml_mixed_cost"
DLL = RUN_DIR / "uml_u_am_v1.dll"
SWEEP = SANDBOX / "runs" / "uml_am_scale_sweep_latest.json"
OUT_JSON = SANDBOX / "runs" / "uml_u_am_creation_audit_latest.json"
OUT_MD = SANDBOX / "runs" / "uml_u_am_creation_audit_latest.md"
GATE = SANDBOX / "uml_federation_promotion_gate.json"
LATTICE = SANDBOX / "uml_domain_expert_lattice.json"
RECIPE = SANDBOX / "uml_domain_expert_train_recipe.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _compile_once() -> tuple[int, str]:
    command = [
        "rustc",
        "--edition",
        "2021",
        "--crate-type",
        "cdylib",
        "-C",
        "opt-level=3",
        "-C",
        "target-cpu=native",
        "-C",
        "panic=abort",
        "-C",
        "strip=symbols",
        str(SOURCE),
        "-o",
        str(DLL),
    ]
    started = time.perf_counter_ns()
    proc = subprocess.run(
        command,
        cwd=str(SANDBOX),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    elapsed = time.perf_counter_ns() - started
    if proc.returncode != 0:
        raise RuntimeError(f"isolated_macro_compile_failed:{proc.stderr}")
    return elapsed, proc.stderr


def _validate_dll() -> dict[str, Any]:
    library = ctypes.CDLL(str(DLL))
    function = library.uml_u_am_v1
    function.argtypes = (ctypes.c_int64, ctypes.c_int64, ctypes.c_int64)
    function.restype = ctypes.c_int64
    marker = library.uml_u_am_v1_contract
    marker.argtypes = ()
    marker.restype = ctypes.c_uint64

    vectors = (
        (0, 0, 1),
        (1, 2, 3),
        (7, 11, 5),
        (255, 255, 64),
        (-3, 8, 7),
    )
    rows = []
    all_ok = True
    for x, y, z in vectors:
        got = int(function(x, y, z))
        expected = (x + y) * z
        ok = got == expected
        all_ok &= ok
        rows.append(
            {
                "x": x,
                "y": y,
                "z": z,
                "got": got,
                "expected": expected,
                "ok": ok,
            }
        )
    got_marker = int(marker())
    expected_marker = 0x0055_5F41_4D5F_5631
    marker_ok = got_marker == expected_marker
    return {
        "vectors": rows,
        "all_vectors_ok": all_ok,
        "contract_marker": f"0x{got_marker:016x}",
        "expected_contract_marker": f"0x{expected_marker:016x}",
        "contract_marker_ok": marker_ok,
        "contract_ok": all_ok and marker_ok,
    }


def _first_winner_rung() -> dict[str, Any]:
    sweep = json.loads(SWEEP.read_text(encoding="utf-8"))
    winners = [
        row for row in sweep.get("rungs") or [] if row.get("service_cost_winner")
    ]
    if not winners:
        raise RuntimeError("no_scale_winner_for_creation_audit")
    return min(winners, key=lambda row: int(row["literal_table_bytes"]))


def _break_even(
    *,
    creation_ns: float,
    persistent_ns: float,
    baseline_ns: float,
    baseline_creation_ns: float = 0.0,
) -> dict[str, Any]:
    saving = baseline_ns - persistent_ns
    creation_delta = creation_ns - baseline_creation_ns
    if saving <= 0:
        return {
            "reachable": False,
            "per_request_saving_ns": saving,
            "requests": None,
        }
    requests = max(0, math.ceil(max(0.0, creation_delta) / saving))
    return {
        "reachable": True,
        "per_request_saving_ns": saving,
        "creation_delta_ns": creation_delta,
        "requests": requests,
    }


def _sync(receipt: dict[str, Any]) -> None:
    finished = receipt["finished_at"]
    if GATE.is_file():
        gate = json.loads(GATE.read_text(encoding="utf-8"))
        gate["isolated_creation_audit"] = {
            "candidate": "U_AM",
            "objective": receipt["objective"],
            "median_creation_ns": receipt["creation"]["median_elapsed_ns"],
            "required_requests": receipt["amortization"][
                "required_requests_first_crossover"
            ],
            "receipt": str(OUT_JSON).replace("\\", "/"),
            "updated_at": finished,
        }
        GATE.write_text(
            json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    if LATTICE.is_file():
        lattice = json.loads(LATTICE.read_text(encoding="utf-8"))
        lattice["u_am_isolated_creation_latest"] = {
            "objective": receipt["objective"],
            "artifact_bytes": receipt["artifact"]["bytes"],
            "required_requests": receipt["amortization"][
                "required_requests_first_crossover"
            ],
            "promotion_ready": False,
            "receipt": str(OUT_JSON).replace("\\", "/"),
            "updated_at": finished,
        }
        LATTICE.write_text(
            json.dumps(lattice, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    if RECIPE.is_file():
        recipe = json.loads(RECIPE.read_text(encoding="utf-8"))
        recipe["last_run"] = finished
        recipe["last_objective"] = receipt["objective"]
        recipe["u_am_isolated_creation"] = {
            "median_creation_ns": receipt["creation"]["median_elapsed_ns"],
            "required_requests": receipt["amortization"][
                "required_requests_first_crossover"
            ],
            "receipt": str(OUT_JSON).replace("\\", "/"),
        }
        recipe["next_action"] = (
            "Use schema-locked production route telemetry to test whether U_AM "
            "frequency reaches the isolated creation-cost break-even; authority "
            "remains closed."
        )
        RECIPE.write_text(
            json.dumps(recipe, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=21)
    parser.add_argument("--warmup", type=int, default=2)
    args = parser.parse_args()
    if args.samples < 21:
        raise ValueError("samples_must_be_at_least_21")

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    for _ in range(args.warmup):
        _compile_once()

    elapsed_samples: list[int] = []
    stderr_rows: list[str] = []
    for _ in range(args.samples):
        elapsed, stderr = _compile_once()
        elapsed_samples.append(elapsed)
        if stderr:
            stderr_rows.append(stderr)

    validation = _validate_dll()
    rung = _first_winner_rung()
    median_creation = int(statistics.median(elapsed_samples))
    persistent_ns = float(rung["persistent_ns_per_request"]["median"])
    dynamic_ns = float(rung["dynamic_ns_per_request"]["median"])
    literal_ns = float(rung["mono_LIT_ns_per_request"]["median"])
    literal_build_ns = float(rung["literal_build_ns"])
    vs_dynamic = _break_even(
        creation_ns=median_creation,
        persistent_ns=persistent_ns,
        baseline_ns=dynamic_ns,
    )
    vs_literal = _break_even(
        creation_ns=median_creation,
        persistent_ns=persistent_ns,
        baseline_ns=literal_ns,
        baseline_creation_ns=literal_build_ns,
    )
    required = max(
        int(vs_dynamic.get("requests") or 0),
        int(vs_literal.get("requests") or 0),
    )
    valid = (
        len(elapsed_samples) >= 21
        and validation["contract_ok"]
        and DLL.is_file()
    )
    objective = "PASS_ISOLATED_CREATION" if valid else "INCONCLUSIVE"
    finished = datetime.now(timezone.utc).isoformat()
    receipt: dict[str, Any] = {
        "schema_version": "uml_u_am_creation_audit_v1",
        "status": "PASS",
        "objective": objective,
        "finished_at": finished,
        "candidate": "U_AM",
        "candidate_type": "isolated_compiled_uml_macro",
        "creation": {
            "samples": len(elapsed_samples),
            "warmup": args.warmup,
            "elapsed_ns_samples": elapsed_samples,
            "median_elapsed_ns": median_creation,
            "p95_elapsed_ns": _p95(elapsed_samples),
            "min_elapsed_ns": min(elapsed_samples),
            "max_elapsed_ns": max(elapsed_samples),
            "mean_elapsed_ns": statistics.fmean(elapsed_samples),
            "scope": "rustc startup + isolated source compile + cdylib link + file write",
            "stderr_rows": stderr_rows,
        },
        "artifact": {
            "source": str(SOURCE).replace("\\", "/"),
            "source_sha256": _sha256(SOURCE),
            "dll": str(DLL).replace("\\", "/"),
            "dll_sha256": _sha256(DLL),
            "bytes": DLL.stat().st_size,
        },
        "contract_validation": validation,
        "first_scale_crossover": {
            "literal_table_bytes": rung["literal_table_bytes"],
            "persistent_ns_per_request": persistent_ns,
            "dynamic_ns_per_request": dynamic_ns,
            "mono_LIT_ns_per_request": literal_ns,
            "literal_build_ns": literal_build_ns,
        },
        "amortization": {
            "break_even_vs_dynamic": vs_dynamic,
            "break_even_vs_mono_LIT": vs_literal,
            "required_requests_first_crossover": required,
            "production_frequency_status": "NOT_MEASURED",
        },
        "promotion": {
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
    OUT_MD.write_text(
        "\n".join(
            [
                "# U_AM Isolated Creation Audit",
                "",
                f"- Objective: **{objective}**",
                f"- Samples: {len(elapsed_samples)}",
                f"- Median creation: {median_creation / 1e6:.3f} ms",
                f"- p95 creation: {_p95(elapsed_samples) / 1e6:.3f} ms",
                f"- DLL: {DLL.stat().st_size} bytes",
                f"- Contract: {validation['contract_ok']}",
                f"- Break-even vs dynamic: {vs_dynamic['requests']} requests",
                f"- Break-even vs mono/LIT: {vs_literal['requests']} requests",
                f"- Required at first crossover: {required} requests",
                "- Production frequency: NOT MEASURED",
                "- Promoted: False",
                "",
                f"Receipt: `{OUT_JSON.as_posix()}`",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    _sync(receipt)
    print(
        f"UML_U_AM_CREATION_{objective} median_ms={median_creation / 1e6:.3f} "
        f"p95_ms={_p95(elapsed_samples) / 1e6:.3f} "
        f"bytes={DLL.stat().st_size} required={required} promoted=False",
        flush=True,
    )
    return 0 if valid else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main())
