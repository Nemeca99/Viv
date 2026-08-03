#!/usr/bin/env python3
"""Ablation audit: Master / +P / +P+V / +P+V+I / +S_electrical on session holdouts.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_ablation.py

Honestly measures whether S_electrical adds over power telemetry reweighting.
Never mutates Master.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_admission import MAE_IMPROVE_MIN  # noqa: E402
from lib.rid_electrical_session_eval import (  # noqa: E402
    evaluate_feature_on_holdout,
    list_session_dirs,
    session_series,
    split_train_test_sessions,
)

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
FEATURES = ("none", "P", "P_V", "P_V_I", "S_electrical")


def run() -> dict[str, Any]:
    series = [session_series(d) for d in list_session_dirs()]
    train, test = split_train_test_sessions(series)
    results = {k: evaluate_feature_on_holdout(train, test, k) for k in FEATURES}

    # Compare S_electrical vs best power-family feature
    power_deltas = {
        k: results[k].get("delta_info")
        for k in ("P", "P_V", "P_V_I")
        if results[k].get("delta_info") is not None
    }
    best_power_key = None
    best_power_delta = None
    if power_deltas:
        best_power_key = max(power_deltas, key=lambda k: float(power_deltas[k]))
        best_power_delta = power_deltas[best_power_key]

    s_delta = results["S_electrical"].get("delta_info")
    adds_over_power = None
    if s_delta is not None and best_power_delta is not None:
        adds_over_power = float(s_delta) - float(best_power_delta)

    interpretation = "insufficient_sessions"
    if len(series) >= 2 and s_delta is not None:
        if adds_over_power is not None and adds_over_power >= MAE_IMPROVE_MIN:
            interpretation = "S_electrical_adds_beyond_power_family"
        elif best_power_delta is not None and float(best_power_delta) >= MAE_IMPROVE_MIN:
            interpretation = (
                "power_family_carries_gain;S_electrical_likely_nonlinear_reweight"
            )
        elif s_delta is not None and float(s_delta) >= MAE_IMPROVE_MIN:
            interpretation = "S_electrical_gain_without_clear_power_baseline"
        else:
            interpretation = "no_prediction_gain_observed"

    report = {
        "ok": True,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "experiment_id": "rid_electrical_ablation_v1",
        "lifecycle": "measured_in_shadow",
        "authority": "shadow_only_no_master_write",
        "protocol": "whole_session_holdout",
        "sessions": {
            "n_total": len(series),
            "n_train": len(train),
            "n_test": len(test),
            "train_ids": [s["session_id"] for s in train],
            "test_ids": [s["session_id"] for s in test],
        },
        "ablation": results,
        "comparison": {
            "best_power_feature": best_power_key,
            "best_power_delta_info": best_power_delta,
            "S_electrical_delta_info": s_delta,
            "S_electrical_minus_best_power": adds_over_power,
            "epsilon": MAE_IMPROVE_MIN,
            "interpretation": interpretation,
            "note": (
                "Derived I comes from P and V; full triad may behave as nonlinear "
                "reweighting. That is acceptable if prediction improves — measured here."
            ),
        },
        "admission_granted": False,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jpath = OUT_DIR / "ablation_latest.json"
    mpath = OUT_DIR / "ablation_latest.md"
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Electrical ablation audit",
        "",
        f"- **Interpretation:** {interpretation}",
        f"- **Sessions:** train={len(train)} test={len(test)}",
        f"- **Best power Δ_info ({best_power_key}):** {best_power_delta}",
        f"- **S_electrical Δ_info:** {s_delta}",
        f"- **S_electrical − best power:** {adds_over_power}",
        "",
        "| Feature | baseline MAE | pilot MAE | Δ_info |",
        "|---------|--------------|-----------|--------|",
    ]
    for k in FEATURES:
        r = results[k]
        lines.append(
            f"| {k} | {r.get('baseline_mae')} | {r.get('pilot_mae')} | {r.get('delta_info')} |"
        )
    lines.extend(["", "Master admission: **not granted**.", ""])
    mpath.write_text("\n".join(lines), encoding="utf-8")
    report["artifact_json"] = str(jpath).replace("\\", "/")
    report["artifact_md"] = str(mpath).replace("\\", "/")
    return report


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    out = run()
    print(json.dumps(out, indent=2), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
