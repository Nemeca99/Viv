"""Self-modifying governor loop — analyze history, tune params, rollback on failure."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from typing import Any

from lib.governor_params import (
    BOUNDS,
    GovernorParams,
    HISTORY_PATH,
    append_tune_log,
    load_params,
    save_params,
)

DORMANCY = 0.45
MIN_SAMPLES = 15


def read_history(limit: int = 500) -> list[dict[str, Any]]:
    if not HISTORY_PATH.is_file():
        return []
    lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def analyze(samples: list[dict[str, Any]], params: GovernorParams) -> dict[str, Any]:
    if len(samples) < MIN_SAMPLES:
        return {
            "verdict": "INCONCLUSIVE",
            "reason": f"need>={MIN_SAMPLES}_samples_have_{len(samples)}",
            "n": len(samples),
        }

    pkg_sn = [float(s.get("package_s_n", 0)) for s in samples]
    budgets = [float(s.get("package_budget_pct", 0)) for s in samples]
    max_temps = [float(s.get("max_temp_c", 0)) for s in samples]
    swap_counts = [len(s.get("swaps") or []) for s in samples]

    dormancy_rate = sum(1 for x in pkg_sn if x < DORMANCY) / len(pkg_sn)
    budget_std = statistics.pstdev(budgets) if len(budgets) > 1 else 0.0
    budget_delta = [
        abs(budgets[i] - budgets[i - 1]) for i in range(1, len(budgets))
    ]
    budget_whip = statistics.mean(budget_delta) if budget_delta else 0.0
    max_temp = max(max_temps) if max_temps else 0.0
    mean_temp = statistics.mean(max_temps) if max_temps else 0.0
    swap_rate = statistics.mean(swap_counts) if swap_counts else 0.0
    near_ceiling = sum(1 for t in max_temps if t >= params.t_max_c * 0.92) / len(max_temps)

    return {
        "verdict": "OK",
        "n": len(samples),
        "dormancy_rate": round(dormancy_rate, 4),
        "budget_std": round(budget_std, 2),
        "budget_whip": round(budget_whip, 2),
        "max_temp_c": round(max_temp, 1),
        "mean_temp_c": round(mean_temp, 1),
        "swap_rate": round(swap_rate, 3),
        "near_ceiling_rate": round(near_ceiling, 4),
        "mean_package_s_n": round(statistics.mean(pkg_sn), 4),
    }


def propose_tuning(metrics: dict[str, Any], params: GovernorParams) -> dict[str, Any]:
    if metrics.get("verdict") != "OK":
        return {"applied": False, "changes": [], "reason": metrics.get("reason", "inconclusive")}

    changes: list[dict[str, Any]] = []
    p = params.clamped()

    # Whipsaw / oscillation -> smoother EMA
    if metrics["budget_std"] > 18.0 or metrics["budget_whip"] > 12.0:
        new_ema = min(BOUNDS["budget_ema"][1], p.budget_ema + 0.08)
        if new_ema > p.budget_ema:
            changes.append({"field": "budget_ema", "from": p.budget_ema, "to": new_ema, "why": "budget_oscillation"})

    # Hot but throttling too hard (dormancy while temps still have headroom)
    if metrics["dormancy_rate"] > 0.25 and metrics["max_temp_c"] < p.t_max_c * 0.88:
        new_tmax = min(BOUNDS["t_max_c"][1], p.t_max_c + 1.5)
        if new_tmax > p.t_max_c:
            changes.append({"field": "t_max_c", "from": p.t_max_c, "to": new_tmax, "why": "false_dormancy_headroom"})

    # Running near thermal ceiling -> tighten
    if metrics["near_ceiling_rate"] > 0.15 or metrics["max_temp_c"] >= p.t_max_c * 0.98:
        new_tmax = max(BOUNDS["t_max_c"][0], p.t_max_c - 1.0)
        if new_tmax < p.t_max_c:
            changes.append({"field": "t_max_c", "from": p.t_max_c, "to": new_tmax, "why": "thermal_ceiling"})

    # RSR too sensitive (rapid delta-T collapses S_n) -> widen max_delta
    if metrics["budget_whip"] > 8.0 and metrics["mean_package_s_n"] < 0.35:
        new_delta = min(BOUNDS["max_delta_c"][1], p.max_delta_c + 0.5)
        if new_delta > p.max_delta_c:
            changes.append({"field": "max_delta_c", "from": p.max_delta_c, "to": new_delta, "why": "rsr_oversensitive"})

    # Swap churn -> raise swap threshold slightly (swap less aggressively)
    if metrics["swap_rate"] > 0.4:
        new_swap = min(BOUNDS["swap_s_n"][1], p.swap_s_n + 0.03)
        if new_swap > p.swap_s_n:
            changes.append({"field": "swap_s_n", "from": p.swap_s_n, "to": new_swap, "why": "swap_churn"})

    # Stable and cool -> allow slightly snappier response (only if very stable)
    if (
        metrics["budget_std"] < 8.0
        and metrics["dormancy_rate"] < 0.05
        and metrics["near_ceiling_rate"] < 0.02
        and p.budget_ema > 0.25
    ):
        new_ema = max(BOUNDS["budget_ema"][0], p.budget_ema - 0.05)
        if new_ema < p.budget_ema:
            changes.append({"field": "budget_ema", "from": p.budget_ema, "to": new_ema, "why": "stable_speed_up"})

    if not changes:
        return {"applied": False, "changes": [], "reason": "no_adjustment_needed", "metrics": metrics}

    return {"applied": True, "changes": changes, "metrics": metrics}


def apply_proposal(proposal: dict[str, Any], params: GovernorParams) -> GovernorParams:
    p = params.clamped()
    for ch in proposal.get("changes", []):
        field = ch["field"]
        if hasattr(p, field):
            setattr(p, field, float(ch["to"]))
    p.version += 1
    p.source = "self_tune"
    return p.clamped()


def tune_once(*, dry_run: bool = False, sample_limit: int = 200) -> dict[str, Any]:
    """One self-modify cycle: analyze -> propose -> apply (with backup)."""
    params = load_params()
    samples = read_history(sample_limit)
    metrics = analyze(samples, params)
    proposal = propose_tuning(metrics, params)
    report: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "params_before": params.to_dict(),
        "metrics": metrics,
        "proposal": proposal,
        "dry_run": dry_run,
    }

    if not proposal.get("applied"):
        report["verdict"] = "NO_CHANGE"
        report["params_after"] = params.to_dict()
        append_tune_log(report)
        return report

    new_params = apply_proposal(proposal, params)
    report["params_after"] = new_params.to_dict()
    report["verdict"] = "APPLIED"

    if not dry_run:
        save_params(new_params, backup=True)
        append_tune_log(report)
    return report


def evaluate_tune_window(before: list[dict], after: list[dict]) -> dict[str, Any]:
    """Compare stability before/after a tune — for rollback decision."""
    if len(before) < 5 or len(after) < 5:
        return {"verdict": "INCONCLUSIVE", "rollback": False}
    b_std = statistics.pstdev([float(x.get("package_budget_pct", 0)) for x in before])
    a_std = statistics.pstdev([float(x.get("package_budget_pct", 0)) for x in after])
    b_dorm = sum(1 for x in before if float(x.get("package_s_n", 1)) < DORMANCY) / len(before)
    a_dorm = sum(1 for x in after if float(x.get("package_s_n", 1)) < DORMANCY) / len(after)
    worse = a_std > b_std * 1.35 and a_dorm >= b_dorm
    return {
        "verdict": "WORSE" if worse else "OK",
        "rollback": worse,
        "budget_std_before": round(b_std, 2),
        "budget_std_after": round(a_std, 2),
        "dormancy_before": round(b_dorm, 4),
        "dormancy_after": round(a_dorm, 4),
    }
