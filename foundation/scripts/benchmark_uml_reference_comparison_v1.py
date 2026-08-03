#!/usr/bin/env python3
"""Compare an incoming UML calculator reference with the canonical engine."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.uml_engine import evaluate as canonical_evaluate, verify as canonical_verify  # noqa: E402


CASES = (
    ("[3,4]", 7.0),
    ("{10,3}", 7.0),
    (">6,7<", 42.0),
    ("<{8,2},3>", 2.0),
    ("^3[2]", 8.0),
    ("![5]", 120.0),
    ("%[17,5]", 2.0),
    ("[pi,pi]", 6.283185307179586),
    ("&[2,8]", 3.0),
    ("|~[5]", 5.0),
    ("\\/[9]", 3j),
)


def load_reference(path: Path):
    spec = importlib.util.spec_from_file_location("incoming_uml_calculator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_reference:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def equivalent(left: object, right: object) -> bool:
    try:
        return abs(complex(left) - complex(right)) <= 1e-9 * max(1.0, abs(complex(left)), abs(complex(right)))
    except (TypeError, ValueError):
        return left == right


def measure(fn, expr: str, repeats: int) -> tuple[object, float]:
    started = time.perf_counter_ns()
    value = None
    for _ in range(repeats):
        value, _node, _notation, _trace = fn(expr)
    return value, (time.perf_counter_ns() - started) / 1_000_000 / repeats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path, default=Path("artifacts/uml_calculator-12.py"), nargs="?")
    parser.add_argument("--repeats", type=int, default=200)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    reference = load_reference(args.reference)
    rows = []
    for expr, expected in CASES:
        row = {"expr": expr, "expected": repr(expected)}
        for label, evaluate_fn, verify_fn in (
            ("incoming", reference.evaluate, reference.verify),
            ("canonical", canonical_evaluate, canonical_verify),
        ):
            try:
                value, mean_ms = measure(evaluate_fn, expr, max(1, args.repeats))
                verify_result = verify_fn(expr)
                verify_ok = bool(verify_result[0])
                row[label] = {
                    "value": repr(value),
                    "correct": equivalent(value, expected),
                    "verified": verify_ok,
                    "verification_report": str(verify_result[1]),
                    "mean_eval_ms": mean_ms,
                }
            except Exception as exc:  # noqa: BLE001 — receipt records reference incompatibility
                row[label] = {"error": f"{type(exc).__name__}:{exc}"}
        rows.append(row)

    summary = {}
    for label in ("incoming", "canonical"):
        selected = [row[label] for row in rows if label in row and "error" not in row[label]]
        summary[label] = {
            "cases": len(selected),
            "correct": sum(bool(row["correct"]) for row in selected),
            "verified": sum(bool(row["verified"]) for row in selected),
            "mean_eval_ms": statistics.fmean(float(row["mean_eval_ms"]) for row in selected) if selected else None,
        }
    status = "PASS" if all(
        row.get(label, {}).get("correct") and row.get(label, {}).get("verified")
        for row in rows for label in ("incoming", "canonical")
    ) else "HOLD"
    payload = json.dumps({"status": status, "reference": str(args.reference), "repeats": args.repeats, "summary": summary, "rows": rows}, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(json.dumps({"status": status, "reference": str(args.reference), "repeats": args.repeats, "summary": summary, "output": str(args.output) if args.output else None, "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()}, indent=2, ensure_ascii=False))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
