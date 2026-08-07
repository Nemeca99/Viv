#!/usr/bin/env python3
"""Compile and run the bounded U_AM mixed-workload economics benchmark.

This does not weaken the promotion law and does not promote anything.

Cost surface:
  C_persistent = median steady-state ns/request of compiled ``(x+y)*z``
  C_dynamic    = median ns/request of generic U-validated A/M opcode dispatch
  C_mono_LIT   = median ns/request of an unchecked dense materialized table

A service-cost candidate must satisfy both strict inequalities on median and
p95, win at least 80% of paired rounds, preserve output parity, and inherit a
Codex-holding temporary checkpoint. Creation/training amortization, production
frequency, and operator authority remain separate gates before promotion.
"""
from __future__ import annotations

import argparse
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
SOURCE = SANDBOX / "bench_uml_am_cost.rs"
RUN_DIR = SANDBOX / "runs" / "uml_mixed_cost"
EXE = RUN_DIR / "bench_uml_am_cost.exe"
RAW_JSON = RUN_DIR / "uml_am_raw_latest.json"
OUT_JSON = SANDBOX / "runs" / "uml_mixed_cost_benchmark_latest.json"
OUT_MD = SANDBOX / "runs" / "uml_mixed_cost_benchmark_latest.md"
PAIR_RECEIPT = SANDBOX / "runs" / "uml_temp_federations_latest.json"
TEMP_CKPT = SANDBOX / "runs" / "uml_temp_federations" / "temp_U_AM.pt"
GATE = SANDBOX / "uml_federation_promotion_gate.json"
LATTICE = SANDBOX / "uml_domain_expert_lattice.json"
RECIPE = SANDBOX / "uml_domain_expert_train_recipe.json"
THESIS = SANDBOX / "UML_TRAINING_THESIS.md"


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def _summary(elapsed_ns: list[int], requests: int) -> dict[str, Any]:
    ns_per_request = [float(value) / requests for value in elapsed_ns]
    return {
        "samples": len(ns_per_request),
        "requests_per_sample": requests,
        "events": len(ns_per_request) * requests,
        "median_ns_per_request": statistics.median(ns_per_request),
        "p95_ns_per_request": _p95(ns_per_request),
        "min_ns_per_request": min(ns_per_request),
        "max_ns_per_request": max(ns_per_request),
        "mean_ns_per_request": statistics.fmean(ns_per_request),
        "total_window_ns": sum(elapsed_ns),
        "ns_per_request_samples": ns_per_request,
    }


def _load_codex_hold() -> dict[str, Any]:
    if not PAIR_RECEIPT.is_file():
        return {
            "codex_hold": False,
            "status": "MISSING_RECEIPT",
            "checkpoint_exists": TEMP_CKPT.is_file(),
        }
    receipt = json.loads(PAIR_RECEIPT.read_text(encoding="utf-8"))
    for row in receipt.get("federations") or []:
        label = str(row.get("pair") or row.get("label") or "")
        if label == "AM":
            return {
                "codex_hold": bool(row.get("codex_hold")),
                "status": str(row.get("status") or "UNKNOWN"),
                "delta_codex_acc": row.get("delta_codex_acc"),
                "delta_uml_acc": row.get("delta_uml_acc"),
                "checkpoint": str(TEMP_CKPT).replace("\\", "/"),
                "checkpoint_exists": TEMP_CKPT.is_file(),
            }
    return {
        "codex_hold": False,
        "status": "MISSING_U_AM",
        "checkpoint_exists": TEMP_CKPT.is_file(),
    }


def _compile() -> dict[str, Any]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter_ns()
    proc = subprocess.run(
        [
            "rustc",
            "--edition",
            "2021",
            "-C",
            "opt-level=3",
            "-C",
            "target-cpu=native",
            str(SOURCE),
            "-o",
            str(EXE),
        ],
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
        raise RuntimeError(f"rustc_failed:{proc.returncode}:{proc.stderr}")
    return {
        "elapsed_ns": elapsed,
        "stderr": proc.stderr,
        "artifact": str(EXE).replace("\\", "/"),
        "artifact_bytes": EXE.stat().st_size,
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    }


def _run_bench(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    command = [
        str(EXE),
        "--x-size",
        str(args.x_size),
        "--y-size",
        str(args.y_size),
        "--z-size",
        str(args.z_size),
        "--requests",
        str(args.requests),
        "--rounds",
        str(args.rounds),
        "--warmup",
        str(args.warmup),
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
    wall_ns = time.perf_counter_ns() - started
    if proc.returncode != 0:
        raise RuntimeError(f"benchmark_failed:{proc.returncode}:{proc.stderr}")
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("benchmark_empty_stdout")
    raw = json.loads(lines[-1])
    RAW_JSON.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return raw, {
        "command": command,
        "wall_ns": wall_ns,
        "stderr": proc.stderr,
        "stdout_lines": len(lines),
    }


def _sync(receipt: dict[str, Any]) -> None:
    finished = receipt["finished_at"]
    economics = receipt["economics"]
    service_winner = bool(economics["service_cost_winner"])

    if GATE.is_file():
        gate = json.loads(GATE.read_text(encoding="utf-8"))
        current = dict(gate.get("current_evidence") or {})
        current.update(
            {
                "service_cost_winners": 1 if service_winner else 0,
                "full_promotion_winners": 0,
                "candidate": "U_AM" if service_winner else None,
                "last_benchmark": receipt["objective"],
                "receipt": str(OUT_JSON).replace("\\", "/"),
                "updated_at": finished,
            }
        )
        gate["current_evidence"] = current
        gate["mixed_workload_benchmark"] = {
            "surface": "variable_input_computation",
            "formula": "(x+y)*z",
            "service_cost_winner": service_winner,
            "codex_hold": receipt["codex"]["codex_hold"],
            "production_frequency_gate": "NOT_MEASURED",
            "authority_gate": "NOT_INVOKED",
            "receipt": str(OUT_JSON).replace("\\", "/"),
        }
        GATE.write_text(
            json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    if LATTICE.is_file():
        lattice = json.loads(LATTICE.read_text(encoding="utf-8"))
        lattice["mixed_workload_cost_latest"] = {
            "objective": receipt["objective"],
            "candidate": "U_AM" if service_winner else None,
            "service_cost_winner": service_winner,
            "promotion_ready": False,
            "reason_not_promoted": (
                "production_frequency_and_authority_not_satisfied"
                if service_winner
                else "cost_comparison_failed"
            ),
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
        recipe["mixed_workload_cost"] = {
            "candidate": "U_AM" if service_winner else None,
            "service_cost_winner": service_winner,
            "promotion_ready": False,
            "receipt": str(OUT_JSON).replace("\\", "/"),
        }
        recipe["next_action"] = (
            "U_AM clears service-cost and Codex gates. Measure real production "
            "frequency/amortization, then request explicit authority; do not promote yet."
            if service_winner
            else "U_AM did not clear the strict service-cost gate. Leave temporary."
        )
        RECIPE.write_text(
            json.dumps(recipe, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    if THESIS.is_file() and "Mixed-workload cost benchmark" not in THESIS.read_text(
        encoding="utf-8"
    ):
        thesis = THESIS.read_text(encoding="utf-8")
        lines = thesis.splitlines(keepends=True)
        output: list[str] = []
        inserted = False
        for line in lines:
            output.append(line)
            if not inserted and line.startswith("13. ~~Cost-winner hunt~~"):
                output.append(
                    "14. ~~Mixed-workload cost benchmark~~ → "
                    f"**{receipt['objective']}** (`uml_mixed_cost_benchmark_latest.json`; "
                    "variable-input U_AM; no promotion without frequency + authority)\n"
                )
                inserted = True
        if inserted:
            THESIS.write_text("".join(output), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x-size", type=int, default=256)
    parser.add_argument("--y-size", type=int, default=256)
    parser.add_argument("--z-size", type=int, default=64)
    parser.add_argument("--requests", type=int, default=1_048_576)
    parser.add_argument("--rounds", type=int, default=31)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--min-round-win-rate", type=float, default=0.80)
    args = parser.parse_args()
    if args.rounds < 21:
        raise ValueError("rounds_must_be_at_least_21")

    compile_info = _compile()
    raw, run_info = _run_bench(args)
    requests = int(raw["requests"])
    persistent = _summary(
        [int(v) for v in raw["persistent_elapsed_ns"]], requests
    )
    dynamic = _summary([int(v) for v in raw["dynamic_elapsed_ns"]], requests)
    literal = _summary([int(v) for v in raw["literal_elapsed_ns"]], requests)

    p_samples = persistent["ns_per_request_samples"]
    d_samples = dynamic["ns_per_request_samples"]
    l_samples = literal["ns_per_request_samples"]
    paired = min(len(p_samples), len(d_samples), len(l_samples))
    wins_dynamic = sum(p_samples[i] < d_samples[i] for i in range(paired))
    wins_literal = sum(p_samples[i] < l_samples[i] for i in range(paired))
    wins_both = sum(
        p_samples[i] < d_samples[i] and p_samples[i] < l_samples[i]
        for i in range(paired)
    )
    win_rate_both = wins_both / max(1, paired)

    strict_median = (
        persistent["median_ns_per_request"] < dynamic["median_ns_per_request"]
        and persistent["median_ns_per_request"] < literal["median_ns_per_request"]
    )
    strict_p95 = (
        persistent["p95_ns_per_request"] < dynamic["p95_ns_per_request"]
        and persistent["p95_ns_per_request"] < literal["p95_ns_per_request"]
    )
    valid_samples = (
        paired >= 21
        and bool(raw.get("health_ok"))
        and all(
            item["samples"] == paired for item in (persistent, dynamic, literal)
        )
    )
    economics_pass = (
        valid_samples
        and strict_median
        and strict_p95
        and win_rate_both >= float(args.min_round_win_rate)
    )
    codex = _load_codex_hold()
    service_winner = economics_pass and bool(codex["codex_hold"])
    objective = (
        "FOUND_SERVICE_COST_WINNER"
        if service_winner
        else (
            "ECONOMICS_PASS_CODEX_BLOCK"
            if economics_pass
            else "NO_SERVICE_COST_WINNER"
        )
    )

    literal_lifecycle_ns_per_request = (
        literal["median_ns_per_request"]
        + float(raw["literal_build_ns"]) / requests
    )
    finished = datetime.now(timezone.utc).isoformat()
    receipt: dict[str, Any] = {
        "schema_version": "uml_mixed_cost_benchmark_v1",
        "status": "PASS",
        "objective": objective,
        "finished_at": finished,
        "hypothesis": (
            "On variable-input U_AM computation, a compiled persistent composite "
            "has lower steady-state service cost than dynamic U+A+M dispatch and "
            "the strongest dense mono/LIT table, while the temporary U_AM holds Codex."
        ),
        "hypothesis_supported": service_winner,
        "cost_scope": {
            "metric": "steady_state_ns_per_request",
            "creation_training_cost": "NOT_INCLUDED_REQUIRES_FREQUENCY_AMORTIZATION",
            "storage_reported_separately": True,
            "surface": "variable_input_computation_not_sealed_destination_encoding",
        },
        "workload": {
            "federation": raw["federation"],
            "formula": raw["formula"],
            "x_size": raw["x_size"],
            "y_size": raw["y_size"],
            "z_size": raw["z_size"],
            "domain_entries": raw["domain_entries"],
            "requests_per_round": requests,
            "rounds": raw["rounds"],
            "warmup": raw["warmup"],
            "literal_table_bytes": raw["literal_table_bytes"],
            "request_stream_bytes": raw["request_stream_bytes"],
            "program_bytes": raw["program_bytes"],
            "literal_build_ns": raw["literal_build_ns"],
            "literal_lifecycle_first_window_ns_per_request": (
                literal_lifecycle_ns_per_request
            ),
        },
        "ab_windows": {
            "pilot_persistent": persistent,
            "control_dynamic": dynamic,
            "control_mono_LIT": literal,
            "action_distribution": {
                "persistent_events": persistent["events"],
                "dynamic_events": dynamic["events"],
                "mono_LIT_events": literal["events"],
            },
            "deltas_pilot_minus_control_ns_per_request": {
                "vs_dynamic_median": (
                    persistent["median_ns_per_request"]
                    - dynamic["median_ns_per_request"]
                ),
                "vs_mono_LIT_median": (
                    persistent["median_ns_per_request"]
                    - literal["median_ns_per_request"]
                ),
                "vs_dynamic_p95": (
                    persistent["p95_ns_per_request"]
                    - dynamic["p95_ns_per_request"]
                ),
                "vs_mono_LIT_p95": (
                    persistent["p95_ns_per_request"]
                    - literal["p95_ns_per_request"]
                ),
            },
        },
        "economics": {
            "valid_samples": valid_samples,
            "strict_median_both": strict_median,
            "strict_p95_both": strict_p95,
            "paired_rounds": paired,
            "persistent_wins_vs_dynamic": wins_dynamic,
            "persistent_wins_vs_mono_LIT": wins_literal,
            "persistent_wins_both": wins_both,
            "persistent_win_rate_both": win_rate_both,
            "min_round_win_rate": args.min_round_win_rate,
            "service_cost_winner": service_winner,
            "comparison": (
                "C_persistent < C_dynamic AND C_persistent < C_mono_LIT"
            ),
        },
        "codex": codex,
        "promotion": {
            "candidate": "U_AM" if service_winner else None,
            "production_frequency_gate": "NOT_MEASURED",
            "creation_cost_amortization_gate": "NOT_MEASURED",
            "authority_gate": "NOT_INVOKED",
            "promotion_ready": False,
            "promoted": False,
        },
        "runtime_health": {
            "checksum": raw["checksum"],
            "output_parity": bool(raw["health_ok"]),
            "errors": 0,
            "stalls": 0,
            "benchmark_wall_ns": run_info["wall_ns"],
            "stderr": run_info["stderr"],
        },
        "build": compile_info,
        "replay": {
            "command": run_info["command"],
            "raw": str(RAW_JSON).replace("\\", "/"),
        },
    }
    OUT_JSON.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    md = "\n".join(
        [
            "# UML Mixed-Workload Cost Benchmark",
            "",
            f"- Objective: **{objective}**",
            f"- Formula: `{raw['formula']}` ({raw['federation']})",
            f"- Valid rounds: {paired}; events/path: {persistent['events']}",
            (
                "- Persistent median/p95: "
                f"{persistent['median_ns_per_request']:.3f}/"
                f"{persistent['p95_ns_per_request']:.3f} ns/request"
            ),
            (
                "- Dynamic median/p95: "
                f"{dynamic['median_ns_per_request']:.3f}/"
                f"{dynamic['p95_ns_per_request']:.3f} ns/request"
            ),
            (
                "- Mono/LIT median/p95: "
                f"{literal['median_ns_per_request']:.3f}/"
                f"{literal['p95_ns_per_request']:.3f} ns/request"
            ),
            (
                "- Persistent paired wins against both: "
                f"{wins_both}/{paired} ({win_rate_both:.3f})"
            ),
            f"- Literal table: {raw['literal_table_bytes']} bytes",
            f"- Output parity: {bool(raw['health_ok'])}",
            f"- Codex hold: {codex['codex_hold']}",
            "- Promoted: **False** (frequency/amortization + authority not yet satisfied)",
            "",
            f"Receipt: `{OUT_JSON.as_posix()}`",
            "",
        ]
    )
    OUT_MD.write_text(md, encoding="utf-8", newline="\n")
    _sync(receipt)

    print(
        f"UML_MIXED_COST_{objective} "
        f"P={persistent['median_ns_per_request']:.3f}ns "
        f"D={dynamic['median_ns_per_request']:.3f}ns "
        f"L={literal['median_ns_per_request']:.3f}ns "
        f"wins={wins_both}/{paired} codex={codex['codex_hold']} promoted=False",
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
