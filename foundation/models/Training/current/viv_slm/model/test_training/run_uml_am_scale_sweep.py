#!/usr/bin/env python3
"""Replicate the U_AM service-cost comparison across LIT working-set sizes.

The same compiled composite, dynamic opcode program, request count, and sample
count are used at every rung. Only the finite mono/LIT domain grows.

This validates scaling of a *compiled UML macro*. It does not claim that the
temporary PyTorch checkpoint executes at the measured Rust cost, and it does
not invoke promotion authority.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SANDBOX = Path(__file__).resolve().parent
RUN_DIR = SANDBOX / "runs" / "uml_mixed_cost"
EXE = RUN_DIR / "bench_uml_am_cost.exe"
OUT_JSON = SANDBOX / "runs" / "uml_am_scale_sweep_latest.json"
OUT_MD = SANDBOX / "runs" / "uml_am_scale_sweep_latest.md"
GATE = SANDBOX / "uml_federation_promotion_gate.json"
LATTICE = SANDBOX / "uml_domain_expert_lattice.json"
RECIPE = SANDBOX / "uml_domain_expert_train_recipe.json"
THESIS = SANDBOX / "UML_TRAINING_THESIS.md"

RUNG_CONFIGS = (
    (16, 16, 4),
    (32, 32, 8),
    (64, 64, 16),
    (128, 128, 32),
    (256, 256, 64),
)


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _stats(elapsed: list[int], requests: int) -> dict[str, float]:
    samples = [value / requests for value in elapsed]
    return {
        "median": statistics.median(samples),
        "p95": _p95(samples),
        "mean": statistics.fmean(samples),
        "min": min(samples),
        "max": max(samples),
    }


def _ensure_exe() -> None:
    if EXE.is_file():
        return
    import run_uml_mixed_cost_benchmark as base

    base._compile()


def _run_rung(
    *,
    x_size: int,
    y_size: int,
    z_size: int,
    requests: int,
    rounds: int,
    warmup: int,
    min_win_rate: float,
) -> dict[str, Any]:
    command = [
        str(EXE),
        "--x-size",
        str(x_size),
        "--y-size",
        str(y_size),
        "--z-size",
        str(z_size),
        "--requests",
        str(requests),
        "--rounds",
        str(rounds),
        "--warmup",
        str(warmup),
    ]
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
    if proc.returncode != 0:
        raise RuntimeError(f"rung_failed:{x_size}x{y_size}x{z_size}:{proc.stderr}")
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    raw = json.loads(lines[-1])

    p_elapsed = [int(v) for v in raw["persistent_elapsed_ns"]]
    d_elapsed = [int(v) for v in raw["dynamic_elapsed_ns"]]
    l_elapsed = [int(v) for v in raw["literal_elapsed_ns"]]
    persistent = _stats(p_elapsed, requests)
    dynamic = _stats(d_elapsed, requests)
    literal = _stats(l_elapsed, requests)
    paired = min(len(p_elapsed), len(d_elapsed), len(l_elapsed))
    wins = sum(
        p_elapsed[i] < d_elapsed[i] and p_elapsed[i] < l_elapsed[i]
        for i in range(paired)
    )
    win_rate = wins / max(1, paired)
    winner = (
        bool(raw["health_ok"])
        and paired >= 21
        and persistent["median"] < dynamic["median"]
        and persistent["median"] < literal["median"]
        and persistent["p95"] < dynamic["p95"]
        and persistent["p95"] < literal["p95"]
        and win_rate >= min_win_rate
    )
    return {
        "x_size": x_size,
        "y_size": y_size,
        "z_size": z_size,
        "domain_entries": raw["domain_entries"],
        "literal_table_bytes": raw["literal_table_bytes"],
        "requests": requests,
        "rounds": rounds,
        "persistent_ns_per_request": persistent,
        "dynamic_ns_per_request": dynamic,
        "mono_LIT_ns_per_request": literal,
        "paired_wins_both": wins,
        "paired_win_rate_both": win_rate,
        "output_parity": bool(raw["health_ok"]),
        "service_cost_winner": winner,
        "literal_build_ns": raw["literal_build_ns"],
        "command": command,
    }


def _classify(rungs: list[dict[str, Any]]) -> tuple[str, str]:
    flags = [bool(row["service_cost_winner"]) for row in rungs]
    if all(flags):
        return (
            "PASS_ALL_WORKING_SETS",
            "Compiled U_AM strictly beats dynamic and dense LIT at every measured rung.",
        )
    if not any(flags):
        return (
            "FAIL_NO_SCALE_WIN",
            "Compiled U_AM does not clear the strict comparison at any measured rung.",
        )
    first = flags.index(True)
    if all(flags[first:]) and not any(flags[:first]):
        return (
            "PASS_SCALE_CROSSOVER",
            (
                "Compiled U_AM becomes a strict winner once the materialized LIT "
                f"working set reaches {rungs[first]['literal_table_bytes']} bytes."
            ),
        )
    return (
        "INCONCLUSIVE_NON_MONOTONIC",
        "Winner flags are non-monotonic across working-set rungs; do not claim scale.",
    )


def _sync(receipt: dict[str, Any]) -> None:
    objective = receipt["objective"]
    candidate = objective.startswith("PASS_")
    finished = receipt["finished_at"]

    if GATE.is_file():
        gate = json.loads(GATE.read_text(encoding="utf-8"))
        gate["scale_sweep"] = {
            "objective": objective,
            "candidate_type": "compiled_uml_macro" if candidate else None,
            "candidate": "U_AM" if candidate else None,
            "checkpoint_runtime_equivalence": "NOT_PROVED",
            "production_frequency_gate": "NOT_MEASURED",
            "authority_gate": "NOT_INVOKED",
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
        lattice["u_am_scale_sweep_latest"] = {
            "objective": objective,
            "candidate_type": "compiled_uml_macro" if candidate else None,
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
        recipe["last_objective"] = objective
        recipe["u_am_scale_sweep"] = {
            "objective": objective,
            "candidate_type": "compiled_uml_macro" if candidate else None,
            "promotion_ready": False,
            "receipt": str(OUT_JSON).replace("\\", "/"),
        }
        recipe["next_action"] = (
            "Compiled U_AM macro scales economically. Before promotion, bind the "
            "macro to the U_AM route contract, measure production frequency and "
            "creation-cost amortization, then request explicit authority. The .pt "
            "checkpoint itself has not been shown to run at macro cost."
            if candidate
            else "U_AM scale sweep did not produce a stable strict cost winner."
        )
        RECIPE.write_text(
            json.dumps(recipe, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    if THESIS.is_file() and "U_AM scale sweep" not in THESIS.read_text(encoding="utf-8"):
        thesis = THESIS.read_text(encoding="utf-8")
        lines = thesis.splitlines(keepends=True)
        output: list[str] = []
        inserted = False
        for line in lines:
            output.append(line)
            if not inserted and line.startswith("14. ~~Mixed-workload cost benchmark~~"):
                output.append(
                    "15. ~~U_AM scale sweep~~ → "
                    f"**{objective}** (`uml_am_scale_sweep_latest.json`; compiled "
                    "UML macro only; checkpoint-runtime equivalence not claimed; no promotion)\n"
                )
                inserted = True
        if inserted:
            THESIS.write_text("".join(output), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=1_048_576)
    parser.add_argument("--rounds", type=int, default=21)
    parser.add_argument("--warmup", type=int, default=4)
    parser.add_argument("--min-win-rate", type=float, default=0.80)
    args = parser.parse_args()
    if args.rounds < 21:
        raise ValueError("rounds_must_be_at_least_21")

    _ensure_exe()
    rungs = [
        _run_rung(
            x_size=x,
            y_size=y,
            z_size=z,
            requests=args.requests,
            rounds=args.rounds,
            warmup=args.warmup,
            min_win_rate=args.min_win_rate,
        )
        for x, y, z in RUNG_CONFIGS
    ]
    objective, note = _classify(rungs)
    finished = datetime.now(timezone.utc).isoformat()
    receipt = {
        "schema_version": "uml_am_scale_sweep_v1",
        "status": "PASS",
        "objective": objective,
        "hypothesis": (
            "The compiled U_AM macro's strict service-cost win is stable as the "
            "materialized mono/LIT working set scales."
        ),
        "hypothesis_supported": objective.startswith("PASS_"),
        "finished_at": finished,
        "note": note,
        "candidate_type": "compiled_uml_macro",
        "checkpoint_runtime_equivalence": "NOT_PROVED",
        "promotion": {
            "production_frequency_gate": "NOT_MEASURED",
            "creation_cost_amortization_gate": "NOT_MEASURED",
            "authority_gate": "NOT_INVOKED",
            "promotion_ready": False,
            "promoted": False,
        },
        "rungs": rungs,
        "runtime_health": {
            "valid_rungs": sum(
                bool(row["output_parity"]) and row["rounds"] >= 21 for row in rungs
            ),
            "total_rungs": len(rungs),
            "errors": 0,
            "stalls": 0,
        },
    }
    OUT_JSON.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    lines = [
        "# U_AM Scale Sweep",
        "",
        f"- Objective: **{objective}**",
        f"- {note}",
        "- Candidate type: compiled UML macro",
        "- `.pt` runtime equivalence: NOT PROVED",
        "- Promoted: False",
        "",
        "## Rungs",
    ]
    for row in rungs:
        lines.append(
            f"- LIT={row['literal_table_bytes']} bytes: "
            f"P={row['persistent_ns_per_request']['median']:.3f} "
            f"D={row['dynamic_ns_per_request']['median']:.3f} "
            f"L={row['mono_LIT_ns_per_request']['median']:.3f} ns/request; "
            f"wins={row['paired_wins_both']}/{row['rounds']}; "
            f"winner={row['service_cost_winner']}"
        )
    lines.extend(["", f"Receipt: `{OUT_JSON.as_posix()}`", ""])
    OUT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    _sync(receipt)
    print(
        f"UML_AM_SCALE_{objective} "
        + " ".join(
            f"{row['literal_table_bytes']}B={'W' if row['service_cost_winner'] else '-'}"
            for row in rungs
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main())
