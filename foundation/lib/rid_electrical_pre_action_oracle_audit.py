#!/usr/bin/env python3
"""Diagnostic oracle: actual workload → energy on frozen dual corpus.

deployable=false always. Never promotes tokens/duration/done_reason as features.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_pre_action_baseline import paired_metrics
from lib.rid_electrical_pre_action_campaign_status import DUAL_CAMPAIGN_ID
from lib.rid_electrical_pre_action_corpus import split_dual_rows_by_group
from lib.rid_electrical_pre_action_paths import EVIDENCE_PLANT, plant_dir
from lib.rid_electrical_pre_action_snapshot import FORBIDDEN_FEATURE_KEYS

SESSIONS = AUTO_ARTIFACTS / "rid_electrical" / "sessions"
ORACLE_JSON_NAME = "pre_action_oracle_audit_latest.json"
ORACLE_MD_NAME = "pre_action_oracle_audit_latest.md"

VERDICT_BOTTLENECK = "duration_demand_bottleneck"
VERDICT_TOO_VARIABLE = "measurement_or_target_too_variable"
VERDICT_INCONCLUSIVE = "inconclusive_low_coverage"

EARLY_STOP_RATIO = 0.90  # actual_tokens < 0.9 * num_predict => early semantic stop
DONE_REASON_COVERAGE_MIN = 0.80
MIN_HOLDOUT_N = 12
REL_MAE_MAX = 0.15
SLOPE_LO = 0.85
SLOPE_HI = 1.15
BIAS_RMSE_MAX = 0.20
RMSE_IMPROVE_MIN = 0.25  # ≥25% RMSE reduction vs dual pre-action holdout


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ols_fit(xs: Sequence[Sequence[float]], ys: Sequence[float]) -> list[float]:
    """Least-squares with intercept. Returns [intercept, *coefs].

    Uses a tiny ridge term on the diagonal to survive near-collinear designs.
    """
    n = len(ys)
    if n == 0:
        raise ValueError("empty_fit")
    p = len(xs[0]) + 1
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for xrow, y in zip(xs, ys):
        row = [1.0, *[float(v) for v in xrow]]
        for i in range(p):
            xty[i] += row[i] * float(y)
            for j in range(p):
                xtx[i][j] += row[i] * row[j]
    ridge = 1e-6
    for i in range(p):
        xtx[i][i] += ridge
    a = [xtx[i][:] + [xty[i]] for i in range(p)]
    for col in range(p):
        pivot = max(range(col, p), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-18:
            raise ValueError("singular_design")
        a[col], a[pivot] = a[pivot], a[col]
        piv = a[col][col]
        for j in range(col, p + 1):
            a[col][j] /= piv
        for r in range(p):
            if r == col:
                continue
            factor = a[r][col]
            for j in range(col, p + 1):
                a[r][j] -= factor * a[col][j]
    return [a[i][p] for i in range(p)]


def _ols_predict(coefs: Sequence[float], xrow: Sequence[float]) -> float:
    return float(coefs[0]) + sum(float(c) * float(x) for c, x in zip(coefs[1:], xrow))


def load_done_reason_index(
    sessions_root: Path | None = None,
) -> dict[tuple[int, int, float], str]:
    root = sessions_root or SESSIONS
    idx: dict[tuple[int, int, float], str] = {}
    if not root.exists():
        return idx
    for path in root.glob("ctrl2_*/controlled_action_v2.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        infer = data.get("infer") or {}
        cell = data.get("cell") or {}
        try:
            npv = int(cell.get("num_predict") or infer.get("num_predict"))
            toks = int(infer.get("eval_count"))
            dur = round(float(infer.get("eval_duration_s")), 6)
        except (TypeError, ValueError):
            continue
        reason = infer.get("done_reason")
        if reason is None:
            continue
        idx[(npv, toks, dur)] = str(reason)
    return idx


def enrich_row_with_done_reason(
    row: Mapping[str, Any],
    done_index: Mapping[tuple[int, int, float], str],
) -> dict[str, Any]:
    out = dict(row)
    lab = dict(out.get("label") or {})
    snap = out.get("snapshot") if isinstance(out.get("snapshot"), Mapping) else {}
    try:
        npv = int((snap or {}).get("num_predict") or out.get("num_predict"))
        toks = int(lab.get("actual_eval_tokens"))
        dur = round(float(lab.get("eval_duration_s")), 6)
        key = (npv, toks, dur)
        if key in done_index:
            lab["done_reason"] = done_index[key]
    except (TypeError, ValueError):
        pass
    out["label"] = lab
    return out


def _y(row: Mapping[str, Any], head: str) -> float | None:
    lab = row.get("label") or {}
    key = "E_generate_j" if head == "gross" else "E_net_raw_j"
    try:
        v = float(lab.get(key))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


def _oracle_x(
    row: Mapping[str, Any],
    *,
    mode: str,
    include_done: bool,
) -> list[float] | None:
    lab = row.get("label") or {}
    try:
        t_eval = float(lab.get("eval_duration_s"))
        n_eval = float(lab.get("actual_eval_tokens"))
        t_prompt = float(lab.get("prompt_eval_duration_s") or 0.0)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(t_eval) or not math.isfinite(n_eval):
        return None
    if mode == "duration":
        xs = [t_eval]
    elif mode == "tokens":
        xs = [n_eval]
    elif mode == "joint":
        xs = [t_eval, n_eval]
    elif mode == "joint_prompt":
        xs = [t_eval, n_eval, t_prompt]
    else:
        raise ValueError(f"unknown_mode:{mode}")
    if include_done:
        reason = str(lab.get("done_reason") or "")
        # binary: length (hit ceiling) vs early stop / other
        xs.append(1.0 if reason == "length" else 0.0)
    if any(not math.isfinite(v) for v in xs):
        return None
    return xs


def fit_oracle(
    train_rows: Sequence[Mapping[str, Any]],
    *,
    head: str,
    mode: str,
    include_done: bool,
) -> dict[str, Any] | None:
    xs: list[list[float]] = []
    ys: list[float] = []
    for r in train_rows:
        y = _y(r, head)
        x = _oracle_x(r, mode=mode, include_done=include_done)
        if y is None or x is None:
            continue
        xs.append(x)
        ys.append(y)
    if len(ys) < max(4, len(xs[0]) + 2 if xs else 4):
        return None
    try:
        coefs = _ols_fit(xs, ys)
    except ValueError:
        return None
    return {
        "mode": mode,
        "include_done_reason": include_done,
        "n_train": len(ys),
        "coefs": coefs,
        "feature_names": _feature_names(mode, include_done),
        "deployable": False,
    }


def _feature_names(mode: str, include_done: bool) -> list[str]:
    if mode == "duration":
        names = ["eval_duration_s"]
    elif mode == "tokens":
        names = ["actual_eval_tokens"]
    elif mode == "joint":
        names = ["eval_duration_s", "actual_eval_tokens"]
    else:
        names = ["eval_duration_s", "actual_eval_tokens", "prompt_eval_duration_s"]
    if include_done:
        names.append("done_reason_length")
    return names


def eval_oracle(
    model: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    head: str,
) -> dict[str, Any]:
    mode = str(model["mode"])
    include_done = bool(model["include_done_reason"])
    coefs = list(model["coefs"])
    y_true: list[float] = []
    y_pred: list[float] = []
    for r in rows:
        y = _y(r, head)
        x = _oracle_x(r, mode=mode, include_done=include_done)
        if y is None or x is None:
            continue
        y_true.append(y)
        y_pred.append(_ols_predict(coefs, x))
    m = paired_metrics(y_true, y_pred)
    m["deployable"] = False
    return m


def ceiling_mismatch_stats(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    early = 0
    at_limit = 0
    n = 0
    by_reason: dict[str, int] = {}
    ratios: list[float] = []
    for r in rows:
        lab = r.get("label") or {}
        snap = r.get("snapshot") if isinstance(r.get("snapshot"), Mapping) else {}
        try:
            toks = float(lab.get("actual_eval_tokens"))
            npv = float((snap or {}).get("num_predict") or r.get("num_predict"))
        except (TypeError, ValueError):
            continue
        if npv <= 0 or not math.isfinite(toks) or not math.isfinite(npv):
            continue
        n += 1
        ratio = toks / npv
        ratios.append(ratio)
        reason = str(lab.get("done_reason") or "unknown")
        by_reason[reason] = by_reason.get(reason, 0) + 1
        if reason == "length" or ratio >= EARLY_STOP_RATIO:
            at_limit += 1
        else:
            early += 1
    mean_ratio = sum(ratios) / len(ratios) if ratios else None
    return {
        "n": n,
        "early_stop_count": early,
        "stop_at_limit_count": at_limit,
        "early_stop_rate": (early / n) if n else None,
        "stop_at_limit_rate": (at_limit / n) if n else None,
        "mean_actual_over_num_predict": mean_ratio,
        "done_reason_counts": by_reason,
        "early_stop_definition": (
            f"done_reason!='length' and actual_eval_tokens < {EARLY_STOP_RATIO} "
            "* num_predict (semantic early-stop under ceiling)"
        ),
    }


def _passes_ceiling_gates(
    metrics: Mapping[str, Any],
    *,
    dual_holdout_rmse: float | None,
) -> dict[str, Any]:
    rel = metrics.get("rel_mae")
    slope = metrics.get("calibration_slope")
    bor = metrics.get("bias_over_rmse")
    rmse = metrics.get("rmse")
    n = int(metrics.get("n") or 0)
    gates = {
        "n_holdout_ge_min": n >= MIN_HOLDOUT_N,
        "rel_mae_le_0_15": rel is not None and float(rel) <= REL_MAE_MAX,
        "slope_in_0_85_1_15": (
            slope is not None and SLOPE_LO <= float(slope) <= SLOPE_HI
        ),
        "bias_rmse_le_0_20": bor is not None and float(bor) <= BIAS_RMSE_MAX,
        "rmse_improve_ge_25pct_vs_dual_preaction": False,
    }
    improve = None
    if (
        dual_holdout_rmse is not None
        and float(dual_holdout_rmse) > 0
        and rmse is not None
    ):
        improve = 1.0 - (float(rmse) / float(dual_holdout_rmse))
        gates["rmse_improve_ge_25pct_vs_dual_preaction"] = improve >= RMSE_IMPROVE_MIN
    return {
        "passed": all(gates.values()),
        "gates": gates,
        "rmse_improvement_vs_dual": improve,
    }


def run_oracle_audit(
    *,
    campaign_id: str = DUAL_CAMPAIGN_ID,
    sessions_root: Path | None = None,
) -> dict[str, Any]:
    root = plant_dir(campaign_id)
    freeze_path = root / "pre_action_corpus_freeze_latest.json"
    train_path = root / "pre_action_offline_train_latest.json"
    if not freeze_path.exists():
        raise FileNotFoundError(f"missing_freeze:{freeze_path}")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    rows_raw = list(freeze.get("rows") or [])
    done_index = load_done_reason_index(sessions_root)
    rows = [enrich_row_with_done_reason(r, done_index) for r in rows_raw]
    done_cov = sum(
        1 for r in rows if (r.get("label") or {}).get("done_reason") is not None
    ) / max(len(rows), 1)

    dual_ref: dict[str, Any] = {}
    if train_path.exists():
        train_art = json.loads(train_path.read_text(encoding="utf-8"))
        for head in ("gross", "net"):
            hm = (train_art.get(head) or {}).get("holdout_candidate_metrics") or {}
            dual_ref[head] = {
                "rmse": hm.get("rmse"),
                "rel_mae": hm.get("rel_mae"),
                "calibration_slope": hm.get("calibration_slope"),
                "bias_over_rmse": hm.get("bias_over_rmse"),
                "n": hm.get("n"),
            }

    include_done = done_cov >= DONE_REASON_COVERAGE_MIN

    results: dict[str, Any] = {}
    best_by_head: dict[str, Any] = {}
    for head in ("gross", "net"):
        splits = split_dual_rows_by_group(rows, head=head)
        train_rows = splits["train"]
        select_rows = splits["select"]
        holdout_rows = splits["holdout"]
        head_out: dict[str, Any] = {
            "n_train": len(train_rows),
            "n_select": len(select_rows),
            "n_holdout": len(holdout_rows),
            "oracles": {},
        }
        candidates: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        specs = [
            ("duration", False),
            ("tokens", False),
            ("joint", False),
        ]
        if include_done:
            specs.append(("joint", True))
        for mode, with_done in specs:
            name = mode if not with_done else "joint_done_reason"
            model = fit_oracle(
                train_rows, head=head, mode=mode, include_done=with_done
            )
            if model is None:
                head_out["oracles"][name] = {"ok": False, "error": "fit_failed"}
                continue
            select_m = eval_oracle(model, select_rows, head=head)
            holdout_m = eval_oracle(model, holdout_rows, head=head)
            train_m = eval_oracle(model, train_rows, head=head)
            gate = _passes_ceiling_gates(
                holdout_m,
                dual_holdout_rmse=(dual_ref.get(head) or {}).get("rmse"),
            )
            entry = {
                "ok": True,
                "deployable": False,
                "model": {
                    "mode": model["mode"],
                    "include_done_reason": model["include_done_reason"],
                    "feature_names": model["feature_names"],
                    "coefs": model["coefs"],
                    "n_train": model["n_train"],
                    "deployable": False,
                },
                "train_metrics": train_m,
                "select_metrics": select_m,
                "holdout_metrics": holdout_m,
                "ceiling_gates": gate,
            }
            head_out["oracles"][name] = entry
            candidates.append((name, holdout_m, gate))
        # Prefer duration/joint for bottleneck decision
        best_name = None
        best_gate = None
        best_m = None
        for name, holdout_m, gate in candidates:
            if name not in ("duration", "joint", "joint_done_reason"):
                continue
            if best_m is None or (
                holdout_m.get("rmse") is not None
                and (
                    best_m.get("rmse") is None
                    or float(holdout_m["rmse"]) < float(best_m["rmse"])
                )
            ):
                best_name, best_m, best_gate = name, holdout_m, gate
        head_out["best_duration_family"] = {
            "name": best_name,
            "holdout_metrics": best_m,
            "ceiling_gates": best_gate,
        }
        results[head] = head_out
        best_by_head[head] = head_out["best_duration_family"]

    ceiling = ceiling_mismatch_stats(rows)

    # Verdict: require gross duration-family pass (primary); net informative.
    gross_gate = (best_by_head.get("gross") or {}).get("ceiling_gates") or {}
    coverage_ok = len(rows) >= 50 and (
        (results.get("gross") or {}).get("n_holdout", 0) >= MIN_HOLDOUT_N
    )
    if not coverage_ok:
        verdict = VERDICT_INCONCLUSIVE
        verdict_reason = "holdout_or_corpus_coverage_too_low"
    elif bool(gross_gate.get("passed")):
        verdict = VERDICT_BOTTLENECK
        verdict_reason = (
            "duration/joint oracle meets ceiling gates vs dual pre-action holdout; "
            "instrumentation adequate; missing pre-action workload demand"
        )
    else:
        verdict = VERDICT_TOO_VARIABLE
        verdict_reason = (
            "best duration/joint oracle failed ceiling gates; "
            "measurement or target still too variable"
        )

    forbidden_still = sorted(
        k
        for k in (
            "eval_duration_s",
            "actual_eval_tokens",
            "prompt_eval_duration_s",
            "done_reason",
        )
        if k in FORBIDDEN_FEATURE_KEYS
    )

    payload: dict[str, Any] = {
        "ok": True,
        "at": _utc(),
        "campaign_id": campaign_id,
        "evidence_source": EVIDENCE_PLANT,
        "deployable": False,
        "diagnostic_only": True,
        "corpus_hash": freeze.get("corpus_hash"),
        "n_rows": len(rows),
        "done_reason_coverage": done_cov,
        "done_reason_included": include_done,
        "forbidden_feature_keys_confirmed": forbidden_still,
        "dual_preaction_holdout_reference": dual_ref,
        "ceiling_mismatch": ceiling,
        "heads": results,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "authority": {
            "operational_authority": False,
            "learning_admission_withheld": True,
            "auto_admit": False,
            "auto_refit": False,
            "master_routing_authorized": False,
            "gates_action": False,
            "oracle_promotes_features": False,
        },
        "continue_to_action_contract": verdict == VERDICT_BOTTLENECK,
    }

    out_json = root / ORACLE_JSON_NAME
    out_md = root / ORACLE_MD_NAME
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    out_md.write_text(_to_md(payload), encoding="utf-8")
    payload["artifact"] = str(out_json).replace("\\", "/")
    payload["artifact_md"] = str(out_md).replace("\\", "/")
    return payload


def _fmt_m(m: Mapping[str, Any] | None) -> str:
    if not m:
        return "n/a"
    parts = []
    for k in ("n", "rmse", "rel_mae", "calibration_slope", "bias_over_rmse"):
        v = m.get(k)
        if v is None:
            parts.append(f"{k}=n/a")
        elif isinstance(v, float):
            parts.append(f"{k}={v:.4g}")
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts)


def _to_md(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Pre-action oracle audit (diagnostic)",
        "",
        f"- at: `{payload.get('at')}`",
        f"- campaign: `{payload.get('campaign_id')}`",
        f"- deployable: **false**",
        f"- verdict: **{payload.get('verdict')}**",
        f"- continue_to_action_contract: `{payload.get('continue_to_action_contract')}`",
        f"- reason: {payload.get('verdict_reason')}",
        f"- done_reason_coverage: {payload.get('done_reason_coverage')}",
        "",
        "## Ceiling mismatch (num_predict vs actual tokens)",
        "",
    ]
    cm = payload.get("ceiling_mismatch") or {}
    lines.extend(
        [
            f"- n: {cm.get('n')}",
            f"- early_stop_rate: {cm.get('early_stop_rate')}",
            f"- stop_at_limit_rate: {cm.get('stop_at_limit_rate')}",
            f"- mean actual/num_predict: {cm.get('mean_actual_over_num_predict')}",
            f"- done_reason_counts: `{cm.get('done_reason_counts')}`",
            "",
            "## Heads",
            "",
        ]
    )
    for head, h in (payload.get("heads") or {}).items():
        lines.append(f"### {head}")
        lines.append(
            f"- split sizes train/select/holdout: "
            f"{h.get('n_train')}/{h.get('n_select')}/{h.get('n_holdout')}"
        )
        best = h.get("best_duration_family") or {}
        lines.append(f"- best duration-family: `{best.get('name')}`")
        lines.append(f"- holdout: {_fmt_m(best.get('holdout_metrics'))}")
        cg = best.get("ceiling_gates") or {}
        lines.append(f"- ceiling gates passed: `{cg.get('passed')}` `{cg.get('gates')}`")
        ref = (payload.get("dual_preaction_holdout_reference") or {}).get(head) or {}
        lines.append(f"- dual pre-action holdout ref: {_fmt_m(ref)}")
        for name, o in (h.get("oracles") or {}).items():
            if not o.get("ok"):
                lines.append(f"- oracle `{name}`: fit_failed")
                continue
            lines.append(
                f"- oracle `{name}` holdout: {_fmt_m(o.get('holdout_metrics'))}"
            )
        lines.append("")
    lines.extend(
        [
            "## Authority",
            "",
            "- Oracle never promotes deployable features.",
            "- Tokens / duration / done_reason remain forbidden for pre-action models.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"
