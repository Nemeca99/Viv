#!/usr/bin/env python3
"""Bind U_AM service evidence into a replayable, non-promoted candidate.

This gate closes only evidence available locally:
  - exact U + A/M route contract and deterministic test vectors;
  - compiled-macro service-cost win and scale crossover;
  - temporary U_AM checkpoint exists and held Codex;
  - conservative creation-cost break-even estimates;
  - production route frequency, if an explicit JSONL telemetry file exists.

No training or benchmark artifact is reclassified as production telemetry.
No persistent checkpoint/macro is installed. Authority remains external.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
for path in (FOUNDATION, MODEL, SANDBOX):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib import uml_engine  # noqa: E402
from lib.uml_equation_registry import _domains_in_expr  # noqa: E402

BENCH = SANDBOX / "runs" / "uml_mixed_cost_benchmark_latest.json"
SWEEP = SANDBOX / "runs" / "uml_am_scale_sweep_latest.json"
CREATION = SANDBOX / "runs" / "uml_u_am_creation_audit_latest.json"
PAIR = SANDBOX / "runs" / "uml_temp_federations_latest.json"
SOURCE = SANDBOX / "bench_uml_am_cost.rs"
EXE = SANDBOX / "runs" / "uml_mixed_cost" / "bench_uml_am_cost.exe"
ISOLATED_SOURCE = SANDBOX / "uml_u_am_v1.rs"
ISOLATED_DLL = SANDBOX / "runs" / "uml_mixed_cost" / "uml_u_am_v1.dll"
TEMP_CKPT = SANDBOX / "runs" / "uml_temp_federations" / "temp_U_AM.pt"
DEFAULT_TELEMETRY = SANDBOX / "runs" / "uml_route_usage.jsonl"
OUT_JSON = SANDBOX / "runs" / "uml_am_candidate_gate_latest.json"
OUT_MD = SANDBOX / "runs" / "uml_am_candidate_gate_latest.md"
GATE = SANDBOX / "uml_federation_promotion_gate.json"
LATTICE = SANDBOX / "uml_domain_expert_lattice.json"
RECIPE = SANDBOX / "uml_domain_expert_train_recipe.json"
THESIS = SANDBOX / "UML_TRAINING_THESIS.md"


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _pair_row(receipt: dict[str, Any]) -> dict[str, Any]:
    for row in receipt.get("federations") or []:
        if str(row.get("pair") or row.get("label") or "") == "AM":
            return row
    raise RuntimeError("U_AM_pair_receipt_missing")


def _validate_contract() -> dict[str, Any]:
    formula = "(x+y)*z"
    symbolic_probe = "(2+3)*4"
    domains = _domains_in_expr(symbolic_probe)
    vectors = [
        (0, 0, 1),
        (1, 2, 3),
        (7, 11, 5),
        (255, 255, 64),
        (13, 0, 9),
    ]
    rows = []
    all_ok = True
    for x, y, z in vectors:
        expression = f"({x}+{y})*{z}"
        value, _node, _notation, _trace = uml_engine.evaluate(expression)
        expected = (x + y) * z
        ok = int(value) == expected
        all_ok &= ok
        rows.append(
            {
                "x": x,
                "y": y,
                "z": z,
                "expression": expression,
                "value": int(value),
                "expected": expected,
                "ok": ok,
            }
        )
    return {
        "formula": formula,
        "substitute_probe": symbolic_probe,
        "domains": sorted(domains),
        "federation": "".join(
            domain for domain in ("A", "S", "M", "D") if domain in domains
        ),
        "u_structure": {
            "program": ["X", "Y", "ADD", "Z", "MUL"],
            "stack_seals_one_destination": True,
            "malformed_reject_in_benchmark": True,
        },
        "vectors": rows,
        "all_vectors_ok": all_ok,
        "contract_ok": all_ok and domains == frozenset({"A", "M"}),
    }


def _service_row(
    sweep: dict[str, Any], *, choose: str
) -> dict[str, Any]:
    winners = [
        row for row in sweep.get("rungs") or [] if row.get("service_cost_winner")
    ]
    if not winners:
        raise RuntimeError("scale_sweep_has_no_winner")
    if choose == "first":
        return min(winners, key=lambda row: int(row["literal_table_bytes"]))
    return max(winners, key=lambda row: int(row["literal_table_bytes"]))


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
            "reason": "persistent_not_faster",
            "per_request_saving_ns": saving,
            "requests": None,
        }
    if creation_delta <= 0:
        requests = 0
    else:
        requests = math.ceil(creation_delta / saving)
    return {
        "reachable": True,
        "per_request_saving_ns": saving,
        "creation_delta_ns": creation_delta,
        "requests": requests,
    }


def _iter_telemetry(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"invalid_telemetry_json:{line_no}:{exc}") from exc
            if not isinstance(row, dict):
                raise RuntimeError(f"invalid_telemetry_row:{line_no}")
            yield row


def _frequency(
    path: Path,
    *,
    min_events: int,
    min_rate: float,
    required_requests: int,
) -> dict[str, Any]:
    if not path.is_file():
        return {
            "status": "INCONCLUSIVE_NO_PRODUCTION_TELEMETRY",
            "path": str(path).replace("\\", "/"),
            "valid_events": 0,
            "u_am_events": 0,
            "u_am_rate": None,
            "min_events": min_events,
            "min_rate": min_rate,
            "required_requests_for_amortization": required_requests,
            "passes": False,
            "note": (
                "Synthetic training/benchmark receipts are excluded. Create this "
                "JSONL only from real route decisions before invoking promotion."
            ),
        }

    valid = 0
    u_am = 0
    valid_records = 0
    rejected = 0
    for row in _iter_telemetry(path):
        # Schema lock: only explicit, healthy production records count.
        if row.get("source") != "production":
            rejected += 1
            continue
        event = row.get("event")
        if event == "uml_route_selected":
            federation = str(row.get("federation") or "").replace("+", "_")
            valid += 1
            valid_records += 1
            if federation in {"U_AM", "AM"}:
                u_am += 1
            continue
        if event == "uml_route_window":
            if (
                row.get("schema_version") != "uml_route_usage_v1"
                or row.get("outcome") != "PASS"
                or not bool(row.get("heartbeat_progressed"))
                or int(row.get("errors") or 0) != 0
                or int(row.get("stalls") or 0) != 0
            ):
                rejected += 1
                continue
            total = int(row.get("total_requests") or 0)
            counts = row.get("federation_counts") or {}
            if not isinstance(counts, dict) or total <= 0:
                rejected += 1
                continue
            count_sum = sum(int(value) for value in counts.values())
            if count_sum > total:
                rejected += 1
                continue
            valid += total
            valid_records += 1
            u_am += int(counts.get("U_AM") or counts.get("AM") or 0)
            continue
        rejected += 1
    rate = u_am / valid if valid else 0.0
    passes = (
        valid >= min_events
        and rate >= min_rate
        and u_am >= required_requests
    )
    return {
        "status": "PASS" if passes else "INCONCLUSIVE_LOW_SIGNAL",
        "path": str(path).replace("\\", "/"),
        "valid_events": valid,
        "valid_records": valid_records,
        "u_am_events": u_am,
        "u_am_rate": rate,
        "rejected_nonproduction_or_wrong_schema": rejected,
        "min_events": min_events,
        "min_rate": min_rate,
        "required_requests_for_amortization": required_requests,
        "passes": passes,
    }


def _sync(receipt: dict[str, Any]) -> None:
    finished = receipt["finished_at"]
    promotion = receipt["promotion"]

    if GATE.is_file():
        gate = _load_json(GATE)
        gate["candidate_contract"] = {
            "candidate": "U_AM",
            "candidate_type": "compiled_uml_macro",
            "contract_status": receipt["objective"],
            "service_cost_gate": promotion["service_cost_gate"],
            "codex_gate": promotion["codex_gate"],
            "frequency_amortization_gate": promotion[
                "frequency_amortization_gate"
            ],
            "authority_gate": promotion["authority_gate"],
            "promotion_ready": promotion["promotion_ready"],
            "receipt": str(OUT_JSON).replace("\\", "/"),
            "updated_at": finished,
        }
        gate["status"] = "candidate_gated_not_promoted"
        GATE.write_text(
            json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    if LATTICE.is_file():
        lattice = _load_json(LATTICE)
        lattice["composite_candidates"] = {
            "U_AM": {
                "type": "compiled_uml_macro",
                "status": receipt["objective"],
                "promotion_ready": promotion["promotion_ready"],
                "promoted": False,
                "receipt": str(OUT_JSON).replace("\\", "/"),
                "updated_at": finished,
            }
        }
        LATTICE.write_text(
            json.dumps(lattice, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    if RECIPE.is_file():
        recipe = _load_json(RECIPE)
        recipe["last_run"] = finished
        recipe["last_objective"] = receipt["objective"]
        recipe["u_am_candidate_gate"] = {
            "promotion_ready": promotion["promotion_ready"],
            "frequency_status": receipt["frequency"]["status"],
            "authority": promotion["authority_gate"],
            "receipt": str(OUT_JSON).replace("\\", "/"),
        }
        recipe["next_action"] = (
            "Collect schema-locked production route telemetry for U_AM and reach "
            "the conservative creation-cost break-even; then request explicit "
            "authority. Do not promote from synthetic benchmark frequency."
        )
        recipe["binding_read"]["not_yet"] = (
            "U_AM compiled macro is a service-cost candidate, but production "
            "frequency/amortization and authority are not satisfied; .pt runtime "
            "equivalence is not claimed."
        )
        RECIPE.write_text(
            json.dumps(recipe, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    if THESIS.is_file() and "U_AM candidate contract" not in THESIS.read_text(
        encoding="utf-8"
    ):
        thesis = THESIS.read_text(encoding="utf-8")
        lines = thesis.splitlines(keepends=True)
        output: list[str] = []
        inserted = False
        for line in lines:
            output.append(line)
            if not inserted and line.startswith("15. ~~U_AM scale sweep~~"):
                output.append(
                    "16. ~~U_AM candidate contract~~ → "
                    f"**{receipt['objective']}** (`uml_am_candidate_gate_latest.json`; "
                    "production frequency/amortization + authority remain closed; "
                    "not promoted)\n"
                )
                inserted = True
        if inserted:
            THESIS.write_text("".join(output), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telemetry", type=Path, default=DEFAULT_TELEMETRY)
    parser.add_argument("--min-production-events", type=int, default=10_000)
    parser.add_argument("--min-u-am-rate", type=float, default=0.08)
    parser.add_argument(
        "--winner-rung",
        choices=("first", "largest"),
        default="first",
        help="Use first crossover by default (most conservative LIT win surface).",
    )
    args = parser.parse_args()

    bench = _load_json(BENCH)
    sweep = _load_json(SWEEP)
    creation = _load_json(CREATION) if CREATION.is_file() else None
    pair = _pair_row(_load_json(PAIR))
    contract = _validate_contract()
    rung = _service_row(sweep, choose=args.winner_rung)

    if creation is not None and creation.get("objective") == "PASS_ISOLATED_CREATION":
        compile_ns = float(creation["creation"]["median_elapsed_ns"])
        creation_proxy = (
            "isolated U_AM rustc startup + compile + cdylib link + file write"
        )
    else:
        compile_ns = float(bench["build"]["elapsed_ns"])
        creation_proxy = "whole Rust benchmark compile (conservative upper bound)"
    persistent_ns = float(rung["persistent_ns_per_request"]["median"])
    dynamic_ns = float(rung["dynamic_ns_per_request"]["median"])
    literal_ns = float(rung["mono_LIT_ns_per_request"]["median"])
    literal_build_ns = float(rung["literal_build_ns"])
    vs_dynamic = _break_even(
        creation_ns=compile_ns,
        persistent_ns=persistent_ns,
        baseline_ns=dynamic_ns,
    )
    vs_literal = _break_even(
        creation_ns=compile_ns,
        persistent_ns=persistent_ns,
        baseline_ns=literal_ns,
        baseline_creation_ns=literal_build_ns,
    )
    required_requests = max(
        int(vs_dynamic.get("requests") or 0),
        int(vs_literal.get("requests") or 0),
    )
    frequency = _frequency(
        Path(args.telemetry),
        min_events=int(args.min_production_events),
        min_rate=float(args.min_u_am_rate),
        required_requests=required_requests,
    )

    codex_gate = bool(pair.get("codex_hold")) and pair.get("status") == "PASS"
    service_gate = bool(rung.get("service_cost_winner")) and bool(
        sweep.get("hypothesis_supported")
    )
    contract_gate = bool(contract["contract_ok"])
    frequency_gate = bool(frequency["passes"])
    authority_gate = "NOT_INVOKED"
    promotion_ready = (
        service_gate
        and codex_gate
        and contract_gate
        and frequency_gate
        and authority_gate == "PASS"
    )
    objective = (
        "CANDIDATE_AWAITING_FREQUENCY_AND_AUTHORITY"
        if service_gate and codex_gate and contract_gate
        else "CANDIDATE_REJECTED"
    )
    finished = datetime.now(timezone.utc).isoformat()

    receipt = {
        "schema_version": "uml_am_candidate_gate_v1",
        "status": "PASS",
        "objective": objective,
        "finished_at": finished,
        "candidate": {
            "id": "U_AM_v1",
            "type": "compiled_uml_macro",
            "formula": "(x+y)*z",
            "substrate": "U",
            "domains": ["A", "M"],
            "persistent_install_path": None,
            "promoted": False,
        },
        "contract": contract,
        "artifacts": {
            "rust_source": {
                "path": str(SOURCE).replace("\\", "/"),
                "sha256": _sha256(SOURCE),
                "bytes": SOURCE.stat().st_size if SOURCE.is_file() else None,
            },
            "benchmark_executable": {
                "path": str(EXE).replace("\\", "/"),
                "sha256": _sha256(EXE),
                "bytes": EXE.stat().st_size if EXE.is_file() else None,
            },
            "isolated_macro_source": {
                "path": str(ISOLATED_SOURCE).replace("\\", "/"),
                "sha256": _sha256(ISOLATED_SOURCE),
                "bytes": (
                    ISOLATED_SOURCE.stat().st_size
                    if ISOLATED_SOURCE.is_file()
                    else None
                ),
            },
            "isolated_macro_dll": {
                "path": str(ISOLATED_DLL).replace("\\", "/"),
                "sha256": _sha256(ISOLATED_DLL),
                "bytes": ISOLATED_DLL.stat().st_size if ISOLATED_DLL.is_file() else None,
            },
            "temporary_checkpoint": {
                "path": str(TEMP_CKPT).replace("\\", "/"),
                "sha256": _sha256(TEMP_CKPT),
                "bytes": TEMP_CKPT.stat().st_size if TEMP_CKPT.is_file() else None,
                "runtime_equivalence_to_macro": "NOT_CLAIMED",
            },
        },
        "service_economics": {
            "rung_literal_table_bytes": rung["literal_table_bytes"],
            "persistent_ns_per_request": persistent_ns,
            "dynamic_ns_per_request": dynamic_ns,
            "mono_LIT_ns_per_request": literal_ns,
            "paired_win_rate_both": rung["paired_win_rate_both"],
            "service_cost_gate": service_gate,
            "benchmark_receipt": str(BENCH).replace("\\", "/"),
            "sweep_receipt": str(SWEEP).replace("\\", "/"),
        },
        "creation_cost_amortization": {
            "creation_cost_proxy": creation_proxy,
            "persistent_compile_ns": compile_ns,
            "mono_LIT_materialization_ns": literal_build_ns,
            "break_even_vs_dynamic": vs_dynamic,
            "break_even_vs_mono_LIT": vs_literal,
            "required_u_am_requests": required_requests,
            "isolated_creation_receipt": (
                str(CREATION).replace("\\", "/") if creation is not None else None
            ),
            "status": (
                "PASS" if frequency_gate else "INCONCLUSIVE_NO_VALID_FREQUENCY"
            ),
        },
        "frequency": frequency,
        "codex": {
            "status": pair.get("status"),
            "codex_hold": pair.get("codex_hold"),
            "delta_codex_acc": pair.get("delta_codex_acc"),
            "delta_uml_acc": pair.get("delta_uml_acc"),
            "gate": codex_gate,
        },
        "promotion": {
            "contract_gate": contract_gate,
            "service_cost_gate": service_gate,
            "codex_gate": codex_gate,
            "frequency_amortization_gate": frequency_gate,
            "authority_gate": authority_gate,
            "promotion_ready": promotion_ready,
            "promoted": False,
        },
        "doctrine": (
            "A compiled macro may be a cost candidate without making the .pt "
            "checkpoint permanent. Synthetic benchmark traffic is not production "
            "frequency. No authority, no promotion."
        ),
    }
    OUT_JSON.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# U_AM Candidate Gate",
        "",
        f"- Objective: **{objective}**",
        f"- Contract: {contract_gate}",
        f"- Service cost: {service_gate}",
        f"- Codex hold: {codex_gate}",
        f"- Frequency/amortization: {frequency['status']}",
        f"- Required U_AM requests (conservative): {required_requests}",
        f"- Authority: {authority_gate}",
        "- Promotion ready: False",
        "- Promoted: False",
        "- Candidate type: compiled UML macro (`.pt` runtime equivalence not claimed)",
        "",
        f"Receipt: `{OUT_JSON.as_posix()}`",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    _sync(receipt)
    print(
        f"UML_AM_CANDIDATE_{objective} contract={contract_gate} "
        f"service={service_gate} codex={codex_gate} "
        f"frequency={frequency['status']} required={required_requests} "
        "authority=NOT_INVOKED promoted=False",
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
