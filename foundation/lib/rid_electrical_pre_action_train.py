#!/usr/bin/env python3
"""Offline pre_action_energy_v1 training (sklearn confined here).

Ordinary Viv runtime must not import this module.
"""
from __future__ import annotations

import hashlib
import json
import math
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_pre_action_baseline import baseline_predict_E_net, paired_metrics
from lib.rid_electrical_pre_action_campaign_status import (
    assert_campaign_fittable,
)
from lib.rid_electrical_pre_action_corpus import (
    FREEZE_JSON,
    HOLDOUT_GROUPS,
    SELECT_GROUPS,
    TRAIN_GROUPS,
    evaluate_corpus_readiness,
    evaluate_dual_corpus_readiness,
    split_dual_rows_by_group,
    split_rows_by_group,
)
from lib.rid_electrical_pre_action_paths import (
    EVIDENCE_PLANT,
    SCHEMA_VERSION,
    plant_dir,
)
from lib.rid_electrical_pre_action_snapshot import (
    LOCKED_MODEL_CONFIG_HASH,
    REQUIRED_FEATURE_KEYS,
)
from lib.rid_electrical_predictor import ALPHA, BETA, PLANT_CONFIG_ID

CAMPAIGN = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
TRAIN_JSON = CAMPAIGN / "pre_action_offline_train_latest.json"
TRAIN_MD = CAMPAIGN / "pre_action_offline_train_latest.md"
BASELINE_JSON = CAMPAIGN / "pre_action_baseline_latest.json"
BASELINE_MD = CAMPAIGN / "pre_action_baseline_latest.md"
CANDIDATE_DIR = CAMPAIGN / "pre_action_candidates"
CANDIDATE_LOCK = CAMPAIGN / "PRE_ACTION_ENERGY_V1_CANDIDATE_LOCK.json"

FEATURE_ORDER = list(REQUIRED_FEATURE_KEYS)
SIMPLICITY_ORDER = ("linear", "ridge", "huber", "hgbr")
SKLEARN_PIN = "1.9.0"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _require_sklearn():
    try:
        import sklearn  # noqa: F401
        from sklearn.ensemble import HistGradientBoostingRegressor
        from sklearn.linear_model import HuberRegressor, LinearRegression, Ridge
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "scikit-learn required for pre-action training; "
            "install foundation/requirements-electrical-training.txt"
        ) from exc
    return {
        "sklearn": sklearn,
        "LinearRegression": LinearRegression,
        "Ridge": Ridge,
        "HuberRegressor": HuberRegressor,
        "HistGradientBoostingRegressor": HistGradientBoostingRegressor,
        "Pipeline": Pipeline,
        "StandardScaler": StandardScaler,
    }


def _xy(rows: Sequence[Mapping[str, Any]]) -> tuple[list[list[float]], list[float], list[dict]]:
    """Legacy net matrix using row['eligible'] (synthetic harness / V1-compatible)."""
    X, y, meta = [], [], []
    for r in rows:
        feats = r.get("features") or {}
        lab = r.get("label") or {}
        if not r.get("eligible"):
            continue
        if lab.get("E_net_raw_j") is None:
            continue
        try:
            rowx = [float(feats[k]) for k in FEATURE_ORDER]
            yv = float(lab["E_net_raw_j"])
        except (KeyError, TypeError, ValueError):
            continue
        X.append(rowx)
        y.append(yv)
        meta.append(dict(r))
    return X, y, meta


def _xy_head(
    rows: Sequence[Mapping[str, Any]],
    *,
    head: str,
) -> tuple[list[list[float]], list[float], list[dict]]:
    X, y, meta = [], [], []
    y_key = "E_generate_j" if head == "gross" else "E_net_raw_j"
    elig_key = "eligible_gross" if head == "gross" else "eligible_net"
    for r in rows:
        feats = r.get("features") or {}
        lab = r.get("label") or {}
        if head == "gross":
            if not r.get("eligible_gross"):
                continue
        else:
            if not (r.get("eligible_net") or (r.get("eligible") and "eligible_net" not in r)):
                continue
        if lab.get(y_key) is None:
            continue
        try:
            rowx = [float(feats[k]) for k in FEATURE_ORDER]
            yv = float(lab[y_key])
        except (KeyError, TypeError, ValueError):
            continue
        X.append(rowx)
        y.append(yv)
        meta.append(dict(r))
    return X, y, meta


def fit_gross_throughput_baseline(
    train_rows: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    """Fit E_generate ≈ a + b * t_hat on training groups only."""
    xs, ys = [], []
    for r in train_rows:
        if not r.get("eligible_gross"):
            continue
        feats = r.get("features") or {}
        lab = r.get("label") or {}
        try:
            npv = float(feats["num_predict"])
            tps = float(feats["trailing_throughput_tps"])
            y = float(lab["E_generate_j"])
        except (KeyError, TypeError, ValueError):
            continue
        if tps <= 0:
            continue
        xs.append(npv / tps)
        ys.append(y)
    if len(xs) < 5:
        return {"alpha": float(ALPHA), "beta": float(BETA) + 55.0}
    # simple least squares
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    var = sum((x - mx) ** 2 for x in xs)
    if var < 1e-12:
        return {"alpha": my, "beta": 0.0}
    beta = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / var
    alpha = my - beta * mx
    return {"alpha": float(alpha), "beta": float(beta)}


def baseline_on_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    head: str = "net",
    gross_coeffs: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    y_true, y_pred, paired = [], [], []
    y_key = "E_generate_j" if head == "gross" else "E_net_raw_j"
    for r in rows:
        feats = r.get("features") or {}
        lab = r.get("label") or {}
        if lab.get(y_key) is None:
            continue
        try:
            npv = float(feats["num_predict"])
            tps = float(feats["trailing_throughput_tps"])
        except (KeyError, TypeError, ValueError):
            continue
        if tps <= 0:
            continue
        t_hat = npv / tps
        if head == "gross":
            coeffs = gross_coeffs or {"alpha": float(ALPHA), "beta": float(BETA) + 55.0}
            pred_v = float(coeffs["alpha"]) + float(coeffs["beta"]) * t_hat
        else:
            pred = baseline_predict_E_net(
                num_predict=feats.get("num_predict"),
                trailing_throughput_tps=feats.get("trailing_throughput_tps"),
                throughput_history_count=int(feats.get("throughput_history_count") or 0),
            )
            if pred.get("predicted_E_net_j") is None:
                continue
            pred_v = float(pred["predicted_E_net_j"])
        y_true.append(float(lab[y_key]))
        y_pred.append(pred_v)
        paired.append({"action_id": r.get("action_id"), "y": y_true[-1], "yhat": y_pred[-1]})
    metrics = paired_metrics(y_true, y_pred)
    return {"metrics": metrics, "n_paired": len(paired), "paired": paired}


def cell_rel_mae(
    rows: Sequence[Mapping[str, Any]],
    yhat_by_action: Mapping[str, float],
    *,
    y_key: str = "E_net_raw_j",
) -> dict[str, float]:
    from collections import defaultdict
    import statistics

    buckets: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for r in rows:
        aid = str(r.get("action_id") or "")
        if aid not in yhat_by_action:
            continue
        snap = r.get("snapshot") or {}
        cell = f"np{snap.get('num_predict')}__{snap.get('prompt_variant')}"
        lab = r.get("label") or {}
        y_raw = lab.get(y_key)
        if y_raw is None and y_key == "E_net_raw_j":
            y_raw = lab.get("E_generate_j")
        if y_raw is None:
            continue
        y = float(y_raw)
        buckets[cell].append((y, float(yhat_by_action[aid])))
    out: dict[str, float] = {}
    for cell, pairs in buckets.items():
        mae = statistics.fmean([abs(p - t) for t, p in pairs])
        mean_abs = statistics.fmean([abs(t) for t, _ in pairs]) or 1.0
        out[cell] = mae / mean_abs
    return out


def _fit_candidates(X_tr, y_tr, X_sel, y_sel, sk):
    Pipeline = sk["Pipeline"]
    StandardScaler = sk["StandardScaler"]
    LinearRegression = sk["LinearRegression"]
    Ridge = sk["Ridge"]
    HuberRegressor = sk["HuberRegressor"]
    HistGradientBoostingRegressor = sk["HistGradientBoostingRegressor"]

    candidates = []

    # Linear
    pipe = Pipeline([("scaler", StandardScaler()), ("model", LinearRegression())])
    pipe.fit(X_tr, y_tr)
    pred = pipe.predict(X_sel)
    m = paired_metrics(y_sel, list(pred))
    candidates.append({"name": "linear", "params": {}, "model": pipe, "select_metrics": m})

    # Ridge grid
    best_ridge = None
    for alpha in (0.1, 1.0, 10.0, 100.0):
        pipe = Pipeline(
            [("scaler", StandardScaler()), ("model", Ridge(alpha=alpha))]
        )
        pipe.fit(X_tr, y_tr)
        pred = pipe.predict(X_sel)
        m = paired_metrics(y_sel, list(pred))
        entry = {"name": "ridge", "params": {"alpha": alpha}, "model": pipe, "select_metrics": m}
        if best_ridge is None or (m["rmse"] or 1e18) < (best_ridge["select_metrics"]["rmse"] or 1e18):
            best_ridge = entry
    assert best_ridge is not None
    candidates.append(best_ridge)

    # Huber grid
    best_huber = None
    for alpha in (1e-4, 1e-2, 1.0):
        pipe = Pipeline(
            [
                ("scaler", StandardScaler()),
                ("model", HuberRegressor(epsilon=1.35, alpha=alpha, max_iter=500)),
            ]
        )
        pipe.fit(X_tr, y_tr)
        pred = pipe.predict(X_sel)
        m = paired_metrics(y_sel, list(pred))
        entry = {
            "name": "huber",
            "params": {"epsilon": 1.35, "alpha": alpha},
            "model": pipe,
            "select_metrics": m,
        }
        if best_huber is None or (m["rmse"] or 1e18) < (
            best_huber["select_metrics"]["rmse"] or 1e18
        ):
            best_huber = entry
    assert best_huber is not None
    candidates.append(best_huber)

    # HGBR fixed
    hgbr = HistGradientBoostingRegressor(
        max_iter=100,
        learning_rate=0.05,
        max_leaf_nodes=7,
        min_samples_leaf=10,
        l2_regularization=1.0,
        random_state=42,
    )
    hgbr.fit(X_tr, y_tr)
    pred = hgbr.predict(X_sel)
    m = paired_metrics(y_sel, list(pred))
    candidates.append(
        {
            "name": "hgbr",
            "params": {
                "max_iter": 100,
                "learning_rate": 0.05,
                "max_leaf_nodes": 7,
                "min_samples_leaf": 10,
                "l2_regularization": 1.0,
                "random_state": 42,
            },
            "model": hgbr,
            "select_metrics": m,
        }
    )
    return candidates


def select_by_simplicity(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Within 1% RMSE of best, prefer simpler model."""
    valid = [c for c in candidates if c["select_metrics"].get("rmse") is not None]
    if not valid:
        raise RuntimeError("no candidates with select RMSE")
    best_rmse = min(float(c["select_metrics"]["rmse"]) for c in valid)
    near = [
        c
        for c in valid
        if float(c["select_metrics"]["rmse"]) <= best_rmse * 1.01
    ]
    near.sort(key=lambda c: SIMPLICITY_ORDER.index(c["name"]))
    return near[0]


def learning_curve_grouped(
    train_rows: Sequence[Mapping[str, Any]],
    holdout_rows: Sequence[Mapping[str, Any]],
    winner_factory,
    *,
    head: str = "net",
) -> dict[str, Any]:
    """Fit on cumulative train groups; measure holdout RMSE; check final two sizes."""
    by_g: dict[int, list] = {}
    for r in train_rows:
        g = int((r.get("snapshot") or {}).get("collection_group") or 0)
        by_g.setdefault(g, []).append(r)
    groups = sorted(by_g.keys())
    points = []
    for i in range(1, len(groups) + 1):
        subset = []
        for g in groups[:i]:
            subset.extend(by_g[g])
        model = winner_factory(subset)
        X_h, y_h, meta_h = _xy_head(holdout_rows, head=head)
        if not X_h:
            continue
        pred = list(model.predict(X_h))
        m = paired_metrics(y_h, pred)
        points.append({"n_train_groups": i, "n_train": len(subset), "holdout_rmse": m["rmse"]})
    change = None
    if len(points) >= 2 and points[-2]["holdout_rmse"] and points[-1]["holdout_rmse"]:
        a, b = float(points[-2]["holdout_rmse"]), float(points[-1]["holdout_rmse"])
        change = abs(b - a) / max(a, 1e-9)
    return {"points": points, "final_two_rel_change": change}


def admit_offline(
    *,
    cand_metrics: Mapping[str, Any],
    base_metrics: Mapping[str, Any],
    cell_rel: Mapping[str, float],
    learning_curve: Mapping[str, Any],
) -> dict[str, Any]:
    gates = {}
    n = int(cand_metrics.get("n") or 0)
    gates["n_holdout_ge_24"] = n >= 24
    c_rmse = cand_metrics.get("rmse")
    b_rmse = base_metrics.get("rmse")
    gates["rmse_improve_10pct"] = (
        c_rmse is not None
        and b_rmse is not None
        and float(c_rmse) <= float(b_rmse) * 0.90
    )
    gates["mae_not_worse"] = (
        cand_metrics.get("mae") is not None
        and base_metrics.get("mae") is not None
        and float(cand_metrics["mae"]) <= float(base_metrics["mae"]) + 1e-9
    )
    gates["rel_mae_le_0_20"] = (
        cand_metrics.get("rel_mae") is not None
        and float(cand_metrics["rel_mae"]) <= 0.20
    )
    slope = cand_metrics.get("calibration_slope")
    gates["calibration_0_8_1_2"] = slope is not None and 0.8 <= float(slope) <= 1.2
    bor = cand_metrics.get("bias_over_rmse")
    c_rmse_f = float(c_rmse) if c_rmse is not None else None
    # Near-perfect fits: |bias|/rmse is numerically unstable; treat tiny RMSE as pass.
    gates["bias_ratio_le_0_25"] = (
        c_rmse_f is not None and c_rmse_f < 1e-6
    ) or (bor is not None and float(bor) <= 0.25)
    gates["no_cell_rel_mae_gt_0_30"] = all(v <= 0.30 for v in cell_rel.values()) if cell_rel else False
    lc = learning_curve.get("final_two_rel_change")
    gates["learning_curve_change_le_0_10"] = lc is not None and float(lc) <= 0.10
    passed = all(gates.values())
    return {
        "passed": passed,
        "gates": gates,
        "status": (
            "pre_action_offline_candidate_for_shadow"
            if passed
            else "training_not_justified"
        ),
    }


def run_offline_training(
    rows: Sequence[Mapping[str, Any]] | None = None,
    *,
    write: bool = True,
    evidence_source: str | None = None,
    campaign_id: str | None = None,
    out_dir: Path | None = None,
    corpus_hash: str | None = None,
) -> dict[str, Any]:
    if campaign_id:
        try:
            assert_campaign_fittable(str(campaign_id))
        except RuntimeError as exc:
            return {"ok": False, "status": str(exc), "campaign_id": campaign_id}
    # Dual campaigns use dedicated dual trainer
    if campaign_id and (
        str(campaign_id) == "pre_action_energy_dual_v1_plant_v1"
        or str(campaign_id).startswith("pre_action_energy_dual")
    ):
        return run_dual_offline_training(
            rows,
            write=write,
            evidence_source=evidence_source,
            campaign_id=campaign_id,
            out_dir=out_dir,
            corpus_hash=corpus_hash,
        )
    sk = _require_sklearn()
    ev = evidence_source
    if rows is None:
        # Prefer plant freeze when campaign_id given
        freeze_path = None
        if campaign_id:
            freeze_path = plant_dir(campaign_id) / "pre_action_corpus_freeze_latest.json"
        if freeze_path is None or not freeze_path.exists():
            freeze_path = FREEZE_JSON
        if not freeze_path.exists():
            return {"ok": False, "status": "corpus_freeze_missing"}
        payload = json.loads(freeze_path.read_text(encoding="utf-8"))
        if str(payload.get("evidence_source") or "") != EVIDENCE_PLANT:
            return {
                "ok": False,
                "status": "plant_corpus_required",
                "note": "Synthetic corpus cannot train plant candidates.",
            }
        rows = list(payload.get("rows") or [])
        ev = EVIDENCE_PLANT
        campaign_id = campaign_id or payload.get("campaign_id")
        corpus_hash = corpus_hash or payload.get("corpus_hash")
        if campaign_id:
            try:
                assert_campaign_fittable(str(campaign_id))
            except RuntimeError as exc:
                return {"ok": False, "status": str(exc), "campaign_id": campaign_id}
    if ev and ev != EVIDENCE_PLANT and write:
        return {
            "ok": False,
            "status": "plant_corpus_required",
            "note": "Refusing to write plant candidate from non-plant evidence.",
        }
    readiness = evaluate_corpus_readiness(rows)
    if not readiness.get("ok"):
        return {
            "ok": False,
            "status": "corpus_not_ready",
            "readiness": readiness,
            "note": "Training refused until corpus readiness passes.",
        }

    splits = split_rows_by_group(rows)
    train, select, holdout = splits["train"], splits["select"], splits["holdout"]
    X_tr, y_tr, _ = _xy(train)
    X_sel, y_sel, _ = _xy(select)
    X_h, y_h, meta_h = _xy(holdout)
    if len(X_tr) < 10 or len(X_sel) < 5 or len(X_h) < 5:
        return {"ok": False, "status": "insufficient_split_rows"}

    # Refit winner on train+select after selection? Plan: select on group 6, open 7-8 once.
    candidates = _fit_candidates(X_tr, y_tr, X_sel, y_sel, sk)
    winner = select_by_simplicity(candidates)

    # Refit winner on train+select for final holdout eval
    X_ts = X_tr + X_sel
    y_ts = y_tr + y_sel
    # Rebuild same class
    name = winner["name"]
    params = winner["params"]
    Pipeline = sk["Pipeline"]
    StandardScaler = sk["StandardScaler"]
    if name == "linear":
        final = Pipeline([("scaler", StandardScaler()), ("model", sk["LinearRegression"]())])
    elif name == "ridge":
        final = Pipeline(
            [("scaler", StandardScaler()), ("model", sk["Ridge"](alpha=params["alpha"]))]
        )
    elif name == "huber":
        final = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    sk["HuberRegressor"](
                        epsilon=params["epsilon"], alpha=params["alpha"], max_iter=500
                    ),
                ),
            ]
        )
    else:
        final = sk["HistGradientBoostingRegressor"](
            max_iter=100,
            learning_rate=0.05,
            max_leaf_nodes=7,
            min_samples_leaf=10,
            l2_regularization=1.0,
            random_state=42,
        )
    final.fit(X_ts, y_ts)
    pred_h = list(final.predict(X_h))
    cand_m = paired_metrics(y_h, pred_h)
    base = baseline_on_rows(meta_h)
    base_m = base["metrics"]

    yhat_by_action = {
        str(meta_h[i].get("action_id")): float(pred_h[i]) for i in range(len(meta_h))
    }
    cell_rel = cell_rel_mae(meta_h, yhat_by_action)

    def factory(subset_rows):
        Xs, ys, _ = _xy(subset_rows)
        # clone-ish refit of same architecture
        if name == "linear":
            m = Pipeline([("scaler", StandardScaler()), ("model", sk["LinearRegression"]())])
        elif name == "ridge":
            m = Pipeline(
                [("scaler", StandardScaler()), ("model", sk["Ridge"](alpha=params["alpha"]))]
            )
        elif name == "huber":
            m = Pipeline(
                [
                    ("scaler", StandardScaler()),
                    (
                        "model",
                        sk["HuberRegressor"](
                            epsilon=params["epsilon"], alpha=params["alpha"], max_iter=500
                        ),
                    ),
                ]
            )
        else:
            m = sk["HistGradientBoostingRegressor"](
                max_iter=100,
                learning_rate=0.05,
                max_leaf_nodes=7,
                min_samples_leaf=10,
                l2_regularization=1.0,
                random_state=42,
            )
        m.fit(Xs, ys)
        return m

    lc = learning_curve_grouped(train, holdout, factory)
    admission = admit_offline(
        cand_metrics=cand_m,
        base_metrics=base_m,
        cell_rel=cell_rel,
        learning_curve=lc,
    )

    sklearn_ver = sk["sklearn"].__version__
    model_path = Path(".")
    model_hash = ""
    if write:
        dest0 = out_dir or (plant_dir(str(campaign_id)) if campaign_id else CAMPAIGN)
        cand_dir0 = dest0 / "pre_action_candidates"
        cand_dir0.mkdir(parents=True, exist_ok=True)
        model_path = cand_dir0 / f"pre_action_energy_v1_{name}.pkl"
        blob = pickle.dumps(final)
        model_path.write_bytes(blob)
        model_hash = hashlib.sha256(blob).hexdigest()
    else:
        blob = pickle.dumps(final)
        model_hash = hashlib.sha256(blob).hexdigest()
    report = {
        "ok": True,
        "at": _utc(),
        "status": (
            "pre_action_energy_v1_plant_candidate_for_shadow"
            if admission["passed"] and ev == EVIDENCE_PLANT
            else admission["status"]
        ),
        "admission": admission,
        "winner": {"name": name, "params": params, "select_metrics": winner["select_metrics"]},
        "candidates_select": [
            {"name": c["name"], "params": c["params"], "select_metrics": c["select_metrics"]}
            for c in candidates
        ],
        "holdout_candidate_metrics": cand_m,
        "holdout_baseline_metrics": base_m,
        "cell_rel_mae": cell_rel,
        "learning_curve": lc,
        "feature_order": FEATURE_ORDER,
        "model_config_hash": LOCKED_MODEL_CONFIG_HASH,
        "plant_config_id": PLANT_CONFIG_ID,
        "schema_version": SCHEMA_VERSION,
        "evidence_source": ev or EVIDENCE_PLANT,
        "campaign_id": campaign_id,
        "corpus_hash": corpus_hash,
        "v1_coeffs_unchanged": {"alpha": ALPHA, "beta": BETA},
        "sklearn_version": sklearn_ver,
        "model_path": str(model_path).replace("\\", "/"),
        "model_sha256": model_hash,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "gates_action": False,
            "auto_admit": False,
            "auto_refit": False,
            "learning_admission_withheld": True,
        },
        "note": (
            "Negative or inconclusive training is valid. "
            "Pass only admits shadow review, not production."
        ),
    }

    baseline_report = {
        "ok": True,
        "at": _utc(),
        "source": "throughput_v1_baseline",
        "evidence_source": ev or EVIDENCE_PLANT,
        "campaign_id": campaign_id,
        "holdout_metrics": base_m,
        "n_paired": base.get("n_paired"),
        "note": "V1(actual t_eval) is post-action and not a competitor.",
        "authority": report["authority"],
    }

    if write:
        dest = out_dir or (plant_dir(str(campaign_id)) if campaign_id else CAMPAIGN)
        dest.mkdir(parents=True, exist_ok=True)
        # model already written above when write=True
        report["model_path"] = str(model_path).replace("\\", "/")
        report["model_sha256"] = model_hash

        train_json = dest / "pre_action_offline_train_latest.json"
        train_md = dest / "pre_action_offline_train_latest.md"
        base_json = dest / "pre_action_baseline_latest.json"
        base_md = dest / "pre_action_baseline_latest.md"
        train_json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        train_md.write_text(
            "\n".join(
                [
                    "# Pre-action offline train",
                    "",
                    f"- status: {report['status']}",
                    f"- evidence_source: {report['evidence_source']}",
                    f"- winner: {name} {params}",
                    f"- holdout RMSE candidate: {cand_m.get('rmse')}",
                    f"- holdout RMSE baseline: {base_m.get('rmse')}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        base_json.write_text(
            json.dumps(baseline_report, indent=2, default=str), encoding="utf-8"
        )
        base_md.write_text(
            "\n".join(
                [
                    "# Pre-action baseline",
                    "",
                    f"- holdout RMSE: {base_m.get('rmse')}",
                    f"- n_paired: {base.get('n_paired')}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        if admission["passed"] and str(report.get("evidence_source")) == EVIDENCE_PLANT:
            lock = {
                "ok": True,
                "at": _utc(),
                "status": "pre_action_energy_v1_plant_candidate_for_shadow",
                "evidence_source": EVIDENCE_PLANT,
                "winner": report["winner"],
                "model_path": report["model_path"],
                "model_sha256": model_hash,
                "feature_order": FEATURE_ORDER,
                "sklearn_version": sklearn_ver,
                "sklearn_pin": SKLEARN_PIN,
                "model_config_hash": LOCKED_MODEL_CONFIG_HASH,
                "plant_config_id": PLANT_CONFIG_ID,
                "schema_version": SCHEMA_VERSION,
                "campaign_id": campaign_id,
                "corpus_hash": corpus_hash,
                "authority": report["authority"],
            }
            lock_path = dest / "PRE_ACTION_ENERGY_V1_CANDIDATE_LOCK.json"
            lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
            report["candidate_lock"] = str(lock_path).replace("\\", "/")
        try:
            from lib.rid_electrical_pre_action_policy_sync import (
                sync_pre_action_readiness_from_artifacts,
            )

            report["policy_sync"] = sync_pre_action_readiness_from_artifacts()
        except Exception:  # noqa: BLE001
            pass

    return report


def _train_one_head(
    rows: Sequence[Mapping[str, Any]],
    *,
    head: str,
    write: bool,
    dest: Path,
    campaign_id: str | None,
    corpus_hash: str | None,
    evidence_source: str,
) -> dict[str, Any]:
    sk = _require_sklearn()
    splits = split_dual_rows_by_group(rows, head=head)
    train, select, holdout = splits["train"], splits["select"], splits["holdout"]
    X_tr, y_tr, _ = _xy_head(train, head=head)
    X_sel, y_sel, _ = _xy_head(select, head=head)
    X_h, y_h, meta_h = _xy_head(holdout, head=head)
    if len(X_tr) < 10 or len(X_sel) < 5 or len(X_h) < 5:
        return {
            "ok": False,
            "head": head,
            "status": "training_not_justified",
            "reason": "insufficient_split_rows",
            "n_train": len(X_tr),
            "n_select": len(X_sel),
            "n_holdout": len(X_h),
        }

    gross_coeffs = None
    if head == "gross":
        gross_coeffs = fit_gross_throughput_baseline(train)

    candidates = _fit_candidates(X_tr, y_tr, X_sel, y_sel, sk)
    winner = select_by_simplicity(candidates)
    name = winner["name"]
    params = winner["params"]
    Pipeline = sk["Pipeline"]
    StandardScaler = sk["StandardScaler"]
    X_ts = X_tr + X_sel
    y_ts = y_tr + y_sel
    if name == "linear":
        final = Pipeline([("scaler", StandardScaler()), ("model", sk["LinearRegression"]())])
    elif name == "ridge":
        final = Pipeline(
            [("scaler", StandardScaler()), ("model", sk["Ridge"](alpha=params["alpha"]))]
        )
    elif name == "huber":
        final = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    sk["HuberRegressor"](
                        epsilon=params["epsilon"], alpha=params["alpha"], max_iter=500
                    ),
                ),
            ]
        )
    else:
        final = sk["HistGradientBoostingRegressor"](
            max_iter=100,
            learning_rate=0.05,
            max_leaf_nodes=7,
            min_samples_leaf=10,
            l2_regularization=1.0,
            random_state=42,
        )
    final.fit(X_ts, y_ts)
    pred_h = list(final.predict(X_h))
    cand_m = paired_metrics(y_h, pred_h)
    base = baseline_on_rows(meta_h, head=head, gross_coeffs=gross_coeffs)
    base_m = base["metrics"]
    yhat_by_action = {
        str(meta_h[i].get("action_id")): float(pred_h[i]) for i in range(len(meta_h))
    }
    cell_rel = cell_rel_mae(
        meta_h,
        yhat_by_action,
        y_key="E_generate_j" if head == "gross" else "E_net_raw_j",
    )

    def factory(subset_rows):
        Xs, ys, _ = _xy_head(subset_rows, head=head)
        if name == "linear":
            m = Pipeline([("scaler", StandardScaler()), ("model", sk["LinearRegression"]())])
        elif name == "ridge":
            m = Pipeline(
                [("scaler", StandardScaler()), ("model", sk["Ridge"](alpha=params["alpha"]))]
            )
        elif name == "huber":
            m = Pipeline(
                [
                    ("scaler", StandardScaler()),
                    (
                        "model",
                        sk["HuberRegressor"](
                            epsilon=params["epsilon"], alpha=params["alpha"], max_iter=500
                        ),
                    ),
                ]
            )
        else:
            m = sk["HistGradientBoostingRegressor"](
                max_iter=100,
                learning_rate=0.05,
                max_leaf_nodes=7,
                min_samples_leaf=10,
                l2_regularization=1.0,
                random_state=42,
            )
        m.fit(Xs, ys)
        return m

    lc = learning_curve_grouped(train, holdout, factory, head=head)
    # Dual holdout gate: use n>=10 instead of 24 when holdout is smaller dual split
    admission = admit_offline(
        cand_metrics=cand_m,
        base_metrics=base_m,
        cell_rel=cell_rel,
        learning_curve=lc,
    )
    # Plan keeps same numeric gates; dual holdout may be smaller — keep n_holdout_ge_24
    # as-is per plan ("unchanged numeric gates").

    sklearn_ver = sk["sklearn"].__version__
    blob = pickle.dumps(final)
    model_hash = hashlib.sha256(blob).hexdigest()
    model_path = dest / "pre_action_candidates" / f"pre_action_energy_dual_{head}_{name}.pkl"
    status = (
        f"pre_action_energy_dual_{head}_candidate_for_shadow"
        if admission["passed"] and evidence_source == EVIDENCE_PLANT
        else "training_not_justified"
    )
    report = {
        "ok": True,
        "at": _utc(),
        "head": head,
        "status": status,
        "admission": admission,
        "winner": {"name": name, "params": params, "select_metrics": winner["select_metrics"]},
        "holdout_candidate_metrics": cand_m,
        "holdout_baseline_metrics": base_m,
        "cell_rel_mae": cell_rel,
        "learning_curve": lc,
        "gross_baseline_coeffs": gross_coeffs,
        "feature_order": FEATURE_ORDER,
        "model_config_hash": LOCKED_MODEL_CONFIG_HASH,
        "plant_config_id": PLANT_CONFIG_ID,
        "schema_version": SCHEMA_VERSION,
        "evidence_source": evidence_source,
        "campaign_id": campaign_id,
        "corpus_hash": corpus_hash,
        "sklearn_version": sklearn_ver,
        "model_path": str(model_path).replace("\\", "/"),
        "model_sha256": model_hash,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "gates_action": False,
            "auto_admit": False,
            "auto_refit": False,
            "learning_admission_withheld": True,
        },
    }
    if write:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_bytes(blob)
        head_json = dest / f"pre_action_offline_train_{head}_latest.json"
        head_json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        if admission["passed"] and evidence_source == EVIDENCE_PLANT:
            lock = {
                "ok": True,
                "at": _utc(),
                "status": status,
                "head": head,
                "evidence_source": EVIDENCE_PLANT,
                "winner": report["winner"],
                "model_path": report["model_path"],
                "model_sha256": model_hash,
                "feature_order": FEATURE_ORDER,
                "sklearn_version": sklearn_ver,
                "sklearn_pin": SKLEARN_PIN,
                "model_config_hash": LOCKED_MODEL_CONFIG_HASH,
                "plant_config_id": PLANT_CONFIG_ID,
                "schema_version": SCHEMA_VERSION,
                "campaign_id": campaign_id,
                "corpus_hash": corpus_hash,
                "authority": report["authority"],
            }
            lock_path = dest / f"PRE_ACTION_ENERGY_DUAL_{head.upper()}_CANDIDATE_LOCK.json"
            lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
            report["candidate_lock"] = str(lock_path).replace("\\", "/")
    return report


def run_dual_offline_training(
    rows: Sequence[Mapping[str, Any]] | None = None,
    *,
    write: bool = True,
    evidence_source: str | None = None,
    campaign_id: str | None = None,
    out_dir: Path | None = None,
    corpus_hash: str | None = None,
) -> dict[str, Any]:
    """Independent gross/net offline training for dual plant campaign."""
    if campaign_id:
        try:
            assert_campaign_fittable(str(campaign_id))
        except RuntimeError as exc:
            return {"ok": False, "status": str(exc), "campaign_id": campaign_id}
    ev = evidence_source
    if rows is None:
        if not campaign_id:
            return {"ok": False, "status": "campaign_id_required"}
        freeze_path = plant_dir(campaign_id) / "pre_action_corpus_freeze_latest.json"
        if not freeze_path.exists():
            return {"ok": False, "status": "corpus_freeze_missing"}
        payload = json.loads(freeze_path.read_text(encoding="utf-8"))
        if str(payload.get("evidence_source") or "") != EVIDENCE_PLANT:
            return {"ok": False, "status": "plant_corpus_required"}
        rows = list(payload.get("rows") or [])
        ev = EVIDENCE_PLANT
        corpus_hash = corpus_hash or payload.get("corpus_hash")
    if ev and ev != EVIDENCE_PLANT and write:
        return {"ok": False, "status": "plant_corpus_required"}

    readiness = evaluate_dual_corpus_readiness(rows)
    if not readiness.get("ok"):
        return {
            "ok": False,
            "status": "pre_action_dual_corpus_not_ready",
            "readiness": readiness,
        }

    dest = out_dir or plant_dir(str(campaign_id))
    dest.mkdir(parents=True, exist_ok=True)
    gross = _train_one_head(
        rows,
        head="gross",
        write=write,
        dest=dest,
        campaign_id=campaign_id,
        corpus_hash=corpus_hash,
        evidence_source=ev or EVIDENCE_PLANT,
    )
    net = _train_one_head(
        rows,
        head="net",
        write=write,
        dest=dest,
        campaign_id=campaign_id,
        corpus_hash=corpus_hash,
        evidence_source=ev or EVIDENCE_PLANT,
    )
    any_pass = bool(gross.get("admission", {}).get("passed")) or bool(
        net.get("admission", {}).get("passed")
    )
    report = {
        "ok": True,
        "at": _utc(),
        "status": (
            "pre_action_energy_dual_heads_trained"
            if any_pass
            else "training_not_justified"
        ),
        "gross": gross,
        "net": net,
        "evidence_source": ev or EVIDENCE_PLANT,
        "campaign_id": campaign_id,
        "corpus_hash": corpus_hash,
        "schema_version": SCHEMA_VERSION,
        "readiness": readiness,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "gates_action": False,
            "auto_admit": False,
            "auto_refit": False,
            "learning_admission_withheld": True,
        },
        "note": "Each head admits independently; failure of one does not block the other.",
    }
    if write:
        path = dest / "pre_action_offline_train_latest.json"
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        (dest / "pre_action_offline_train_latest.md").write_text(
            "\n".join(
                [
                    "# Dual offline train",
                    "",
                    f"- status: {report['status']}",
                    f"- gross: {gross.get('status')}",
                    f"- net: {net.get('status')}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        try:
            from lib.rid_electrical_pre_action_policy_sync import (
                sync_pre_action_readiness_from_artifacts,
            )

            report["policy_sync"] = sync_pre_action_readiness_from_artifacts()
        except Exception:  # noqa: BLE001
            pass
    return report


def load_candidate_predictor(
    lock_path: Path | None = None,
    *,
    require_plant: bool = True,
    head: str | None = None,
) -> dict[str, Any] | None:
    """Load candidate only after provenance checks (before pickle deserialize)."""
    path = lock_path or CANDIDATE_LOCK
    if not path.exists():
        return None
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    campaign = str(lock.get("campaign_id") or "")
    if campaign:
        try:
            assert_campaign_fittable(campaign)
        except RuntimeError:
            return None
    if require_plant and str(lock.get("evidence_source") or "") != EVIDENCE_PLANT:
        return None
    if head is not None and str(lock.get("head") or "") not in {"", head}:
        return None
    model_path = Path(str(lock.get("model_path") or ""))
    if not model_path.is_file():
        return None
    from lib.rid_electrical_pre_action_paths import PLANT_ROOT as _PR

    try:
        model_resolved = model_path.resolve()
        plant_root = _PR.resolve()
        allowed = False
        if campaign:
            cand_root = (plant_dir(campaign) / "pre_action_candidates").resolve()
            try:
                model_resolved.relative_to(cand_root)
                allowed = True
            except ValueError:
                pass
        if not allowed:
            try:
                model_resolved.relative_to(plant_root)
                allowed = True
            except ValueError:
                allowed = False
        if not allowed:
            return None
    except OSError:
        return None

    expected_hash = str(lock.get("model_sha256") or "")
    blob = model_path.read_bytes()
    actual_hash = hashlib.sha256(blob).hexdigest()
    if not expected_hash or actual_hash != expected_hash:
        return None
    schema = str(lock.get("schema_version") or "")
    if schema not in {SCHEMA_VERSION, "PreActionSnapshotV1", "PreActionSnapshotV2"}:
        return None
    # Dual locks require V2
    if lock.get("head") and schema not in {SCHEMA_VERSION, "PreActionSnapshotV2"}:
        return None
    if str(lock.get("plant_config_id") or "") != PLANT_CONFIG_ID:
        return None
    if str(lock.get("model_config_hash") or "") != LOCKED_MODEL_CONFIG_HASH:
        return None
    try:
        import sklearn

        if lock.get("sklearn_version") and str(lock["sklearn_version"]) != sklearn.__version__:
            return None
    except Exception:  # noqa: BLE001
        return None

    try:
        model = pickle.loads(blob)
    except Exception:  # noqa: BLE001
        return None
    order = list(lock.get("feature_order") or FEATURE_ORDER)

    def predict_fn(features: Mapping[str, Any]) -> float:
        x = [[float(features[k]) for k in order]]
        return float(model.predict(x)[0])

    return {
        "lock": lock,
        "model": model,
        "predict_fn": predict_fn,
        "model_name": (lock.get("winner") or {}).get("name"),
        "head": lock.get("head"),
    }
