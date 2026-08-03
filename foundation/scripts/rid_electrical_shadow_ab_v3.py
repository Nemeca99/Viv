#!/usr/bin/env python3
"""Electrical shadow A/B v3 — session-held-out Δ_info (not row-split).

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_shadow_ab_v3.py

Uses whole sessions under artifacts/auto/rid_electrical/sessions/.
Never mutates Master. One strong session does not advance the lane.
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

from lib.master_rid import MASTER_RID_PATH  # noqa: E402
from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_admission import (  # noqa: E402
    MAE_IMPROVE_MIN,
    MIN_PASSING_WINDOWS,
    archive_window_report,
    evaluate_multiwindow,
    write_multiwindow_report,
)
from lib.rid_electrical_session_eval import (  # noqa: E402
    clean_improvement,
    evaluate_feature_on_holdout,
    list_session_dirs,
    secondary_metrics,
    session_series,
    split_train_test_sessions,
)

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
EXPERIMENT_ID = "rid_electrical_shadow_ab_v3"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run() -> dict[str, Any]:
    master_before = (
        MASTER_RID_PATH.read_text(encoding="utf-8") if MASTER_RID_PATH.is_file() else None
    )
    dirs = list_session_dirs()
    series = [session_series(d) for d in dirs]
    train, test = split_train_test_sessions(series)

    primary = evaluate_feature_on_holdout(train, test, "S_electrical")
    baseline_only = evaluate_feature_on_holdout(train, test, "none")
    secondary = secondary_metrics(test, "S_electrical")

    delta = primary.get("delta_info")
    dynamic_test = any(s.get("dynamic") for s in test)
    n_dynamic_sessions = sum(1 for s in series if s.get("dynamic"))

    clean = clean_improvement(delta if isinstance(delta, (int, float)) else None, secondary)

    if len(series) < 2:
        verdict = "INCONCLUSIVE"
        reason = "need_at_least_two_whole_sessions_for_session_holdout"
    elif not test:
        verdict = "INCONCLUSIVE"
        reason = "no_held_out_session"
    elif not dynamic_test and n_dynamic_sessions == 0:
        verdict = "INCONCLUSIVE_LOW_SIGNAL"
        reason = "no_sufficiently_dynamic_sessions;lane_stays_measured_in_shadow"
    elif clean:
        verdict = "SHADOW_WINDOW_PASS"
        reason = (
            "positive_delta_info_on_held_out_sessions;"
            "isolated_result_does_not_advance_lane;"
            "multiwindow_criteria_required"
        )
    elif delta is not None and float(delta) >= MAE_IMPROVE_MIN and not clean:
        verdict = "SHADOW_ONLY"
        reason = (
            "mae_improved_but_false_warning_rate_exceeds_ceiling;"
            "not_clean_improvement;lane_stays_measured_in_shadow"
        )
    else:
        verdict = "SHADOW_ONLY"
        reason = (
            "flat_or_inconsistent_delta_info_on_session_holdout;"
            "lane_stays_measured_in_shadow"
        )

    report: dict[str, Any] = {
        "ok": True,
        "experiment_id": EXPERIMENT_ID,
        "at": _utc(),
        "authority": "shadow_only_no_master_write",
        "lifecycle": "measured_in_shadow",
        "goal": "prove_electrical_info_gain_not_master_admission",
        "verdict": verdict,
        "reason": reason,
        "protocol": "whole_session_holdout",
        "sessions": {
            "n_total": len(series),
            "n_train": len(train),
            "n_test": len(test),
            "train_ids": [s["session_id"] for s in train],
            "test_ids": [s["session_id"] for s in test],
            "workloads": sorted({str(s.get("workload")) for s in series}),
            "n_dynamic": n_dynamic_sessions,
        },
        "delta_info": {
            "metric": "one_step_master_s_n_mae_session_holdout",
            "epsilon": MAE_IMPROVE_MIN,
            "baseline_persistence_mae": baseline_only.get("baseline_mae"),
            "pilot_master_plus_electrical_mae": primary.get("pilot_mae"),
            "delta_info": delta,
            "fit_n": primary.get("fit_n"),
            "test_n": primary.get("test_n"),
            "blend_a": primary.get("blend_a"),
            "blend_b": primary.get("blend_b"),
            "by_workload": primary.get("by_workload"),
            "clean_improvement": clean,
        },
        "secondary": secondary,
        "geom_reweight": {
            "is_info_gain_evidence": False,
            "note": "Geometric reweighting remains diagnostic, not evidence of information gain.",
        },
        "admission": {
            "granted": False,
            "electrical_in_A_t": False,
            "supports_admission_review": False,
            "lane_advancement_eligible": False,
            "isolated_strong_window_advances_lane": False,
            "min_passing_windows": MIN_PASSING_WINDOWS,
            "rule": (
                "Lane advances only after positive Delta_info across multiple "
                "independent dynamic unseen sessions. Until then measured in shadow."
            ),
        },
        "runtime_health": {
            "master_disk_mutated": False,
            "electrical_in_master_subsystems": False,
        },
    }

    # Archive for multi-window gate (map session report into acceptance shape)
    archive_payload = {
        "at": report["at"],
        "verdict": verdict,
        "window": {
            "duration_s": sum(float((s.get("meta") or {}).get("duration_s") or 0) for s in test)
            or 1.0,
            "valid_shadow_rows": int(primary.get("test_n") or 0),
        },
        "dependence": {
            "master_s_n_variance": max(
                (s.get("master_var") or 0.0) for s in test
            )
            if test
            else 0.0,
        },
        "delta_info": {"delta_info": delta if clean else (delta if delta is not None else 0.0)},
        "geom_reweight": {"delta_mean": None},
        "artifact_json": None,
    }
    # Only count as passing window when clean improvement on dynamic holdout
    if not clean:
        archive_payload["delta_info"]["delta_info"] = 0.0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jpath = OUT_DIR / f"ab-report-{EXPERIMENT_ID}.json"
    mpath = OUT_DIR / f"ab-report-{EXPERIMENT_ID}.md"
    report["artifact_json"] = str(jpath).replace("\\", "/")
    report["artifact_md"] = str(mpath).replace("\\", "/")
    archive_payload["artifact_json"] = report["artifact_json"]

    arch = archive_window_report(archive_payload)
    multi = write_multiwindow_report(evaluate_multiwindow())
    report["admission"]["supports_admission_review"] = bool(multi["supports_admission_review"])
    report["admission"]["lane_advancement_eligible"] = bool(multi["lane_advancement_eligible"])
    report["admission"]["multiwindow"] = {
        "passing_independent_n": multi["passing_independent_n"],
        "min_passing_windows": multi["criteria"]["min_passing_windows"],
        "archive_n": multi["archive_n"],
        "archive_path": str(arch).replace("\\", "/"),
        "artifact": multi.get("latest"),
    }

    master_after = (
        MASTER_RID_PATH.read_text(encoding="utf-8") if MASTER_RID_PATH.is_file() else None
    )
    report["runtime_health"]["master_disk_mutated"] = master_before != master_after

    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = "\n".join(
        [
            f"# A/B report — {EXPERIMENT_ID}",
            "",
            "- **Goal:** prove electrical info-gain (not Master admission)",
            "- **Lifecycle:** measured in shadow",
            f"- **Verdict:** {verdict}",
            f"- **Reason:** {reason}",
            f"- **Protocol:** whole-session holdout (train={len(train)}, test={len(test)})",
            f"- **Δ_info:** {delta} (ε={MAE_IMPROVE_MIN}, clean={clean})",
            f"- **False-warning rate:** {secondary.get('false_warning_rate')}",
            f"- **Multi-window eligible:** {report['admission']['lane_advancement_eligible']}",
            f"- **Master mutated:** {report['runtime_health']['master_disk_mutated']}",
            "",
            "One isolated strong session does not advance the lane.",
            "",
        ]
    )
    mpath.write_text(md, encoding="utf-8")
    return report


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    out = run()
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
