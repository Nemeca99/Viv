#!/usr/bin/env python3
"""A/B: dynamic MD route vs guarded U canonicalization before federation.

Baseline: existing dynamic MD route (domains {M,D}, full AST cost).
Candidate: seal-gated U cancel ((V*K)/K -> V, ...) before federation routing.

Hard gates: K != 0, exact output identity, zero seal failures, no arithmetic
semantics change. Codex hold here = sealed destination identity hold.

Win: defect routes never reach M or D; only residual irreducible MD remains
eligible for a later U_MD service-cost investigation.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
FOUNDATION = HERE.parents[5]
RUNS = HERE / "runs"
sys.path.insert(0, str(FOUNDATION))
sys.path.insert(0, str(HERE))

from lib import uml_engine  # noqa: E402
from lib.uml_guarded_canonicalize import (  # noqa: E402
    domains,
    shape_template,
    try_guarded_cancel,
)

EXPERIMENT_ID = "uml_md_guarded_canonicalization_ab_v1"
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
        "test_uml_route_governor_md_ab",
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


class GuardedCancelABObserver:
    """Observe MD traffic; measure baseline vs guarded-U candidate (no mutate)."""

    def __init__(self, *, experiment_id: str) -> None:
        self.experiment_id = experiment_id
        self._lock = threading.RLock()
        self._active = False
        self.total = 0
        self.md_total = 0
        self.routes_removed = 0
        self.residual_md = 0
        self.seal_failures = 0
        self.identity_holds = 0
        self.identity_fails = 0
        self.baseline_cost_sum = 0
        self.candidate_cost_sum = 0
        self.baseline_route_work_ns = 0
        self.candidate_route_work_ns = 0
        self.candidate_rewrite_ns = 0
        self.rule_counts: Counter[str] = Counter()
        self.reject_counts: Counter[str] = Counter()
        self.residual_shapes: Counter[str] = Counter()
        self.removed_shapes: Counter[str] = Counter()
        self.fail_examples: list[dict[str, Any]] = []

    def start(self) -> "GuardedCancelABObserver":
        with self._lock:
            if self._active:
                return self
            uml_engine.install_evaluation_observer(
                self,
                experiment_id=self.experiment_id,
                fail_closed=True,
            )
            self._active = True
        return self

    def stop(self) -> None:
        with self._lock:
            if not self._active:
                return
            uml_engine.remove_evaluation_observer(experiment_id=self.experiment_id)
            self._active = False

    def __call__(
        self,
        expr: str,
        node: uml_engine.Node,
        authoritative_value: Any,
        _notation: str,
    ) -> None:
        with self._lock:
            self.total += 1
            if domains(node) != {"M", "D"}:
                return
            self.md_total += 1

            # Baseline: dynamic MD route work = full AST eval.
            def walk(cur: uml_engine.Node) -> int:
                if not cur.children:
                    return 1
                return 1 + sum(walk(c) for c in cur.children)

            baseline_cost = walk(node)
            t0 = time.perf_counter_ns()
            _ = uml_engine.eval_node(node)
            baseline_route_ns = time.perf_counter_ns() - t0

            t1 = time.perf_counter_ns()
            result = try_guarded_cancel(
                expr,
                node=node,
                authoritative_value=authoritative_value,
                require_md=True,
            )
            rewrite_ns = time.perf_counter_ns() - t1

            t2 = time.perf_counter_ns()
            if result.applied and result.reduced_node is not None:
                _ = uml_engine.eval_node(result.reduced_node)
            elif not result.applied:
                _ = uml_engine.eval_node(node)
            route_work_ns = time.perf_counter_ns() - t2

            self.baseline_cost_sum += baseline_cost
            self.baseline_route_work_ns += baseline_route_ns
            self.candidate_rewrite_ns += rewrite_ns
            self.candidate_route_work_ns += route_work_ns

            shape = shape_template(node)
            if result.applied and result.seal_ok:
                self.routes_removed += 1
                self.identity_holds += 1
                self.candidate_cost_sum += int(result.reduced_cost or 1)
                self.rule_counts[str(result.rule_id)] += 1
                self.removed_shapes[shape] += 1
            else:
                self.residual_md += 1
                self.candidate_cost_sum += baseline_cost
                self.residual_shapes[shape] += 1
                reason = result.reject_reason or "unknown"
                self.reject_counts[reason] += 1
                if reason == "identity_mismatch":
                    self.seal_failures += 1
                    self.identity_fails += 1
                    if len(self.fail_examples) < 8:
                        self.fail_examples.append(
                            {
                                "expr": expr,
                                "authoritative": authoritative_value,
                                "reduced": result.reduced_value,
                                "rule": result.rule_id,
                            }
                        )

    def summary(self) -> dict[str, Any]:
        with self._lock:
            md = self.md_total
            return {
                "evaluator_invocations": self.total,
                "md_invocations": md,
                "routes_removed": self.routes_removed,
                "residual_md": self.residual_md,
                "routes_removed_share": (self.routes_removed / md) if md else 0.0,
                "residual_share": (self.residual_md / md) if md else 0.0,
                "seal_failures": self.seal_failures,
                "identity_holds": self.identity_holds,
                "identity_fails": self.identity_fails,
                "identity_hold_rate": (
                    self.identity_holds / self.routes_removed
                    if self.routes_removed
                    else 1.0
                ),
                "baseline": {
                    "mean_symbolic_cost": (self.baseline_cost_sum / md) if md else None,
                    "total_symbolic_cost": self.baseline_cost_sum,
                    "mean_route_work_ns": (
                        self.baseline_route_work_ns / md if md else None
                    ),
                    "federation": "dynamic_U+M+D",
                },
                "candidate": {
                    "mean_symbolic_cost": (self.candidate_cost_sum / md) if md else None,
                    "total_symbolic_cost": self.candidate_cost_sum,
                    "mean_route_work_ns": (
                        self.candidate_route_work_ns / md if md else None
                    ),
                    "mean_rewrite_ns": (
                        self.candidate_rewrite_ns / md if md else None
                    ),
                    "federation": "guarded_U_cancel_then_residual_MD",
                },
                "cost_delta_mean": (
                    (self.candidate_cost_sum - self.baseline_cost_sum) / md if md else None
                ),
                "route_work_delta_mean_ns": (
                    (self.candidate_route_work_ns - self.baseline_route_work_ns) / md
                    if md
                    else None
                ),
                "rule_counts": dict(self.rule_counts),
                "reject_counts": dict(self.reject_counts),
                "removed_shapes": self.removed_shapes.most_common(8),
                "residual_shapes": self.residual_shapes.most_common(8),
                "fail_examples": list(self.fail_examples),
            }


def _selfcheck() -> list[str]:
    failures: list[str] = []
    cases = [
        ("(41*2)/2", True, 41.0),
        ("(2*41)/2", True, 41.0),
        ("(2*2)/2", True, 2.0),
        ("(1*4)/2", False, 2.0),
        ("6/2", False, 3.0),
        ("(41*0)/0", False, None),  # undefined / no safe cancel
    ]
    for expr, expect_apply, expect_val in cases:
        try:
            value, node, _n, _t = uml_engine.evaluate(expr)
        except Exception:
            if expect_apply:
                failures.append(f"eval_failed:{expr}")
            continue
        result = try_guarded_cancel(
            expr, node=node, authoritative_value=value, require_md=True
        )
        if bool(result.applied) != expect_apply:
            failures.append(
                f"apply:{expr}:got={result.applied}:reason={result.reject_reason}"
            )
        if expect_apply and expect_val is not None:
            if not uml_engine._approx_eq(result.reduced_value, expect_val):
                failures.append(f"value:{expr}:{result.reduced_value}")
            if result.reduced_domains:
                failures.append(f"domains_not_empty:{expr}:{result.reduced_domains}")
    return failures


def _gate(metrics: dict[str, Any]) -> dict[str, Any]:
    seal_failures = int(metrics["seal_failures"])
    removed_share = float(metrics["routes_removed_share"])
    residual_share = float(metrics["residual_share"])
    cost_delta = metrics["cost_delta_mean"]
    route_work_delta = metrics.get("route_work_delta_mean_ns")
    route_work_win = route_work_delta is not None and route_work_delta < 0
    cost_win = cost_delta is not None and cost_delta < 0
    identity_ok = float(metrics["identity_hold_rate"]) >= 1.0 - 1e-15

    if seal_failures > 0:
        objective = "FAIL_SEAL"
        next_step = "halt_do_not_enable_guarded_cancel"
    elif metrics["md_invocations"] == 0:
        objective = "INCONCLUSIVE_NO_MD_TRAFFIC"
        next_step = "expand_workload"
    elif removed_share >= 0.90 and cost_win and identity_ok and seal_failures == 0:
        objective = "PASS_SUBTRACT_MD_DRAG"
        next_step = (
            "enable_guarded_u_cancel_before_federation;"
            "only_residual_irreducible_md_eligible_for_u_md_service_cost"
        )
    elif removed_share >= 0.50 and identity_ok and seal_failures == 0:
        objective = "PASS_PARTIAL_SUBTRACT"
        next_step = "expand_safe_rule_set_or_accept_partial_enable"
    else:
        objective = "FAIL_NO_WIN"
        next_step = "keep_dynamic_md_investigate_rules"

    return {
        "objective": objective,
        "next_step": next_step,
        "compile_u_md_now": False,
        "u_md_eligible_share": residual_share,
        "seal_failures": seal_failures,
        "identity_ok": identity_ok,
        "cost_win": cost_win,
        "route_work_win": route_work_win,
        "doctrine": (
            "A fast composite is inferior to no computation when UML seals a "
            "valid reduction. Frequency does not prove usefulness."
        ),
    }


def main() -> int:
    RUNS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt_path = RUNS / f"uml_md_guarded_canonicalization_ab_{stamp}.json"
    latest_path = RUNS / "uml_md_guarded_canonicalization_ab_latest.json"
    md_path = RUNS / "uml_md_guarded_canonicalization_ab_latest.md"

    selfcheck = _selfcheck()
    if selfcheck:
        print(json.dumps({"selfcheck_failures": selfcheck}, indent=2))
        return 1

    observer = GuardedCancelABObserver(experiment_id=EXPERIMENT_ID)
    observer.start()
    t0 = time.perf_counter()
    segment_results: list[dict[str, Any]] = []
    try:
        for name, fn in SEGMENTS:
            started = time.perf_counter()
            try:
                code = int(fn())
                err = None
            except Exception as exc:  # noqa: BLE001
                code = 1
                err = f"{type(exc).__name__}: {exc}"
            segment_results.append(
                {
                    "segment": name,
                    "exit_code": code,
                    "error": err,
                    "elapsed_s": round(time.perf_counter() - started, 3),
                    "md_after": observer.md_total,
                }
            )
    finally:
        observer.stop()

    metrics = observer.summary()
    gate = _gate(metrics)
    receipt = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": EXPERIMENT_ID,
        "source": SOURCE,
        "hypothesis": (
            "Guarded U canonicalization before federation removes "
            "canonicalization-defect MD routes; residual irreducible MD only "
            "remains eligible for U_MD service-cost investigation."
        ),
        "arms": {
            "baseline": "dynamic_U+M+D",
            "candidate": "guarded_U_cancel_before_federation",
        },
        "hard_conditions": [
            "seal_validity",
            "K!=0",
            "exact_output_identity",
            "no_changed_arithmetic_semantics",
            "zero_seal_failures",
        ],
        "wall_s": round(time.perf_counter() - t0, 3),
        "selfcheck_failures": selfcheck,
        "segments": segment_results,
        "metrics": metrics,
        "gate": gate,
    }
    text = json.dumps(receipt, indent=2, sort_keys=True)
    receipt_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")

    md = "\n".join(
        [
            "# U_MD guarded U canonicalization A/B",
            "",
            f"**Objective:** `{gate['objective']}`",
            f"**Next:** `{gate['next_step']}`",
            "",
            f"- MD invocations: {metrics['md_invocations']}",
            f"- Routes removed: {metrics['routes_removed']} "
            f"({metrics['routes_removed_share']:.4%})",
            f"- Residual MD: {metrics['residual_md']} "
            f"({metrics['residual_share']:.4%})",
            f"- Seal failures: {metrics['seal_failures']}",
            f"- Baseline mean symbolic cost: "
            f"{metrics['baseline']['mean_symbolic_cost']}",
            f"- Candidate mean symbolic cost: "
            f"{metrics['candidate']['mean_symbolic_cost']}",
            f"- Baseline mean route-work ns: "
            f"{metrics['baseline']['mean_route_work_ns']}",
            f"- Candidate mean route-work ns: "
            f"{metrics['candidate']['mean_route_work_ns']}",
            f"- Candidate mean rewrite ns: "
            f"{metrics['candidate']['mean_rewrite_ns']}",
            f"- `compile_u_md_now`: false",
            f"- U_MD-eligible share (residual): {gate['u_md_eligible_share']:.4%}",
            "",
            "Saint-Exupéry: the first apparent permanent expert was subtracted.",
            "",
            f"Receipt: `{receipt_path.name}`",
        ]
    )
    md_path.write_text(md + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt": str(receipt_path),
                "gate": gate,
                "routes_removed": metrics["routes_removed"],
                "residual_md": metrics["residual_md"],
                "seal_failures": metrics["seal_failures"],
            },
            indent=2,
        )
    )
    return 0 if gate["objective"].startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
