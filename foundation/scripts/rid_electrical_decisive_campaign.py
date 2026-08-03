#!/usr/bin/env python3
"""Decisive multi-round full-length electrical evidence campaign.

Runs N independent rounds of all five full (non-smoke) workload profiles,
then evaluates session-held-out Δ_info with Master-variance qualification.
Master disk writes and routing behavior remain disabled.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_decisive_campaign.py --rounds 3
  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_decisive_campaign.py --evaluate-only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
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
    DECISIVE_MASTER_VAR_MIN,
    FALSE_WARNING_CEILING,
    clean_improvement,
    evaluate_feature_on_holdout,
    list_decisive_sessions,
    qualify_for_prediction,
    secondary_metrics,
    split_train_test_sessions,
)
OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
SESSIONS = OUT_DIR / "sessions"
PROFILES = ("cpu_ramp", "gpu_infer", "mixed", "cpu_gpu_switch", "coolant_eq")


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _mark_incomplete_sessions() -> list[str]:
    """Flag sessions that never got session_meta.ended_at (killed mid-run)."""
    marked: list[str] = []
    if not SESSIONS.is_dir():
        return marked
    for d in SESSIONS.iterdir():
        meta_path = d / "session_meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if meta.get("ended_at") or meta.get("incomplete"):
            continue
        if not (d / "samples.jsonl").is_file():
            continue
        meta["incomplete"] = True
        meta["incomplete_reason"] = "missing_ended_at_assumed_killed"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        marked.append(d.name)
    return marked


def _complete_counts() -> dict[str, int]:
    counts = {p: 0 for p in PROFILES}
    for s in list_decisive_sessions():
        wl = str(s.get("workload") or "")
        if wl in counts:
            counts[wl] += 1
    return counts


def _run_session(profile: str, *, cadence_s: float) -> dict[str, Any]:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "rid_electrical_workload_session",
        FOUNDATION / "scripts" / "rid_electrical_workload_session.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run_session(profile, smoke=False, cadence_s=cadence_s)


def run_rounds(rounds: int, *, cadence_s: float = 1.0, resume: bool = True) -> list[dict[str, Any]]:
    marked = _mark_incomplete_sessions()
    if marked:
        print(f"[decisive] marked incomplete: {marked}", flush=True)
    master_before = (
        MASTER_RID_PATH.read_text(encoding="utf-8") if MASTER_RID_PATH.is_file() else None
    )
    summaries: list[dict[str, Any]] = []
    target = max(1, int(rounds))
    # Fill each profile to `target` complete full-length sessions (resume-safe).
    for fill_i in range(1, target + 1):
        counts = _complete_counts()
        print(
            f"[decisive] === fill {fill_i}/{target} counts={counts} ===",
            flush=True,
        )
        ran_any = False
        for profile in PROFILES:
            have = _complete_counts().get(profile, 0)
            if resume and have >= target:
                print(
                    f"[decisive] skip {profile} already {have}/{target}",
                    flush=True,
                )
                continue
            print(
                f"[decisive] fill={fill_i} profile={profile} FULL ({have}->{have+1})",
                flush=True,
            )
            s = _run_session(profile, cadence_s=cadence_s)
            s["fill"] = fill_i
            summaries.append(s)
            ran_any = True
            time.sleep(65.0)
        if not ran_any:
            print("[decisive] all profiles at target; stopping early", flush=True)
            break
        if fill_i < target:
            time.sleep(30.0)
    master_after = (
        MASTER_RID_PATH.read_text(encoding="utf-8") if MASTER_RID_PATH.is_file() else None
    )
    if master_before != master_after:
        print("[decisive] WARNING: master_rid.json changed during campaign", flush=True)
    return summaries


def _folds(qualified: list[dict[str, Any]]) -> list[tuple[list[dict[str, Any]], list[dict[str, Any]], str]]:
    """Build multiple whole-session holdout folds for repeatability."""
    folds: list[tuple[list[dict[str, Any]], list[dict[str, Any]], str]] = []
    if len(qualified) < 2:
        return folds
    # Chronological: train early / test late
    tr, te = split_train_test_sessions(qualified, min_test=max(1, len(qualified) // 3))
    if tr and te:
        folds.append((tr, te, "chrono_early_train_late_test"))
    # Leave-last-round-ish: if >=6 sessions, also test last 5 (one profile set)
    if len(qualified) >= 10:
        folds.append((qualified[:-5], qualified[-5:], "leave_last_five_sessions"))
    if len(qualified) >= 8:
        mid = len(qualified) // 2
        folds.append((qualified[:mid], qualified[mid:], "chrono_half_split"))
    # Deduplicate identical splits
    seen = set()
    uniq = []
    for tr, te, name in folds:
        key = (tuple(s["session_id"] for s in tr), tuple(s["session_id"] for s in te))
        if key in seen:
            continue
        seen.add(key)
        uniq.append((tr, te, name))
    return uniq


def evaluate_decisive() -> dict[str, Any]:
    all_full = list_decisive_sessions()
    qualified = [s for s in all_full if qualify_for_prediction(s)]
    disqualified = [
        {
            "session_id": s["session_id"],
            "workload": s.get("workload"),
            "master_var": s.get("master_var"),
            "reason": "inadequate_master_variance"
            if not s.get("decisive_dynamic")
            else "unknown",
        }
        for s in all_full
        if not qualify_for_prediction(s)
    ]

    fold_reports = []
    positive_folds = 0
    for train, test, name in _folds(qualified):
        primary = evaluate_feature_on_holdout(train, test, "S_electrical")
        secondary = secondary_metrics(test, "S_electrical")
        delta = primary.get("delta_info")
        clean = clean_improvement(
            delta if isinstance(delta, (int, float)) else None, secondary
        )
        if clean:
            positive_folds += 1
        fold_reports.append(
            {
                "fold": name,
                "train_ids": [s["session_id"] for s in train],
                "test_ids": [s["session_id"] for s in test],
                "train_workloads": sorted({str(s.get("workload")) for s in train}),
                "test_workloads": sorted({str(s.get("workload")) for s in test}),
                "delta_info": delta,
                "baseline_mae": primary.get("baseline_mae"),
                "pilot_mae": primary.get("pilot_mae"),
                "by_workload": primary.get("by_workload"),
                "secondary": secondary,
                "clean_improvement": clean,
            }
        )

    # Combined unseen = last chrono fold primary metrics
    combined = fold_reports[0] if fold_reports else None
    by_workload_combined = (combined or {}).get("by_workload") or {}

    # Ablation on best chrono fold
    ablation = {}
    if fold_reports:
        tr_ids = set(fold_reports[0]["train_ids"])
        te_ids = set(fold_reports[0]["test_ids"])
        train = [s for s in qualified if s["session_id"] in tr_ids]
        test = [s for s in qualified if s["session_id"] in te_ids]
        for feat in ("none", "P", "P_V", "P_V_I", "S_electrical"):
            ablation[feat] = evaluate_feature_on_holdout(train, test, feat)

    repeatable = positive_folds >= min(2, max(1, len(fold_reports))) and positive_folds >= 2
    if len(fold_reports) < 2:
        repeatable = False

    delta_main = (combined or {}).get("delta_info")
    secondary_main = (combined or {}).get("secondary") or {}
    clean_main = bool((combined or {}).get("clean_improvement"))

    # Decision evidence bundle
    evidence = {
        "delta_info": delta_main,
        "lead_time_s_mean": secondary_main.get("transition_warning_lead_time_s_mean"),
        "false_alarms": {
            "rate": secondary_main.get("false_warning_rate"),
            "count": secondary_main.get("false_warning_count"),
            "ceiling": FALSE_WARNING_CEILING,
        },
        "calibration_mae_persistence": secondary_main.get("calibration_mae_persistence"),
        "overhead_ms_mean": secondary_main.get("mean_collect_overhead_ms"),
        "repeatability": {
            "positive_clean_folds": positive_folds,
            "folds_total": len(fold_reports),
            "repeatable_positive_delta_info": repeatable,
            "min_folds_required": 2,
        },
    }

    # Outcome
    misleading = (
        delta_main is not None
        and float(delta_main) >= MAE_IMPROVE_MIN
        and not clean_main
    ) or (delta_main is not None and float(delta_main) < 0)
    if repeatable and clean_main and delta_main is not None and float(delta_main) >= MAE_IMPROVE_MIN:
        outcome = "repeatable_useful_gain"
        disposition = "advisory_routing_candidate_then_canary_review"
    elif misleading:
        outcome = "unstable_or_misleading_signal"
        disposition = "reject_operational_use"
    else:
        outcome = "no_prediction_gain_but_reliable_diagnostic_value"
        disposition = "permanent_shadow_diagnostic"

    # Archive combined fold for multi-window gate (only if clean+dynamic)
    holdout_rows = 0
    if fold_reports:
        te_ids = set(fold_reports[0]["test_ids"])
        holdout_rows = sum(
            len(s.get("samples") or []) for s in qualified if s["session_id"] in te_ids
        )
    archive_payload = {
        "at": _utc(),
        "verdict": "SHADOW_WINDOW_PASS" if clean_main else "SHADOW_ONLY",
        "window": {
            "duration_s": float(
                sum((s.get("meta") or {}).get("duration_s") or 0.0 for s in qualified)
            ),
            "valid_shadow_rows": holdout_rows,
        },
        "dependence": {
            "master_s_n_variance": max(
                (s.get("master_var") or 0.0) for s in qualified
            )
            if qualified
            else 0.0,
        },
        "delta_info": {
            "delta_info": float(delta_main)
            if isinstance(delta_main, (int, float))
            else 0.0
        },
        "geom_reweight": {"delta_mean": None},
        "decisive_fold": (combined or {}).get("fold"),
        "clean_improvement": clean_main,
    }

    arch = archive_window_report(archive_payload)
    multi = write_multiwindow_report(evaluate_multiwindow())

    report = {
        "ok": True,
        "at": _utc(),
        "experiment_id": "rid_electrical_decisive_evidence_v1",
        "goal": "prove_electrical_info_gain_not_master_admission",
        "lifecycle": "measured_in_shadow",
        "authority": "evidence_only_no_master_write_no_routing_behavior",
        "master_writes_disabled": True,
        "routing_behavior_disabled": True,
        "admission_granted": False,
        "criteria": {
            "mae_improve_min": MAE_IMPROVE_MIN,
            "decisive_master_var_min": DECISIVE_MASTER_VAR_MIN,
            "false_warning_ceiling": FALSE_WARNING_CEILING,
            "min_passing_windows": MIN_PASSING_WINDOWS,
            "holdout": "whole_sessions_never_rows",
            "smoke_excluded": True,
        },
        "corpus": {
            "full_sessions_n": len(all_full),
            "qualified_sessions_n": len(qualified),
            "disqualified": disqualified,
            "qualified_ids": [s["session_id"] for s in qualified],
            "workloads_present": sorted({str(s.get("workload")) for s in qualified}),
        },
        "decision_evidence": evidence,
        "by_workload": by_workload_combined,
        "folds": fold_reports,
        "ablation": {
            k: {
                "delta_info": v.get("delta_info"),
                "baseline_mae": v.get("baseline_mae"),
                "pilot_mae": v.get("pilot_mae"),
            }
            for k, v in ablation.items()
        },
        "outcome": outcome,
        "disposition": disposition,
        "multiwindow": {
            "lane_advancement_eligible": multi.get("lane_advancement_eligible"),
            "passing_independent_n": multi.get("passing_independent_n"),
            "archive_path": str(arch).replace("\\", "/"),
        },
        "primary_metric": "Delta_info = MAE_Master - MAE_Master+electrical",
        "note": (
            "Decisive evidence uses full-length sessions only, requires adequate "
            "Master S_n variance, whole-session holdouts, and repeatable positive "
            "Delta_info. Master writes and routing behavior remain disabled."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jpath = OUT_DIR / "decisive_evidence_latest.json"
    mpath = OUT_DIR / "decisive_evidence_latest.md"
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Decisive electrical evidence",
        "",
        f"- **Outcome:** {outcome}",
        f"- **Disposition:** {disposition}",
        f"- **Δ_info (combined):** {delta_main}",
        f"- **Repeatable positive folds:** {positive_folds}/{len(fold_reports)}",
        f"- **Qualified sessions:** {len(qualified)} / {len(all_full)} full",
        f"- **Master writes:** disabled",
        f"- **Routing behavior:** disabled",
        f"- **Admission granted:** false",
        "",
        "## Decision evidence",
        "",
        f"- lead_time_s_mean: {evidence['lead_time_s_mean']}",
        f"- false_alarm_rate: {evidence['false_alarms']['rate']}",
        f"- calibration_mae: {evidence['calibration_mae_persistence']}",
        f"- overhead_ms_mean: {evidence['overhead_ms_mean']}",
        f"- repeatability: {evidence['repeatability']}",
        "",
        "## By workload (combined fold)",
        "",
    ]
    for wl, row in sorted(by_workload_combined.items()):
        lines.append(
            f"- **{wl}:** Δ_info={row.get('delta_info')} n={row.get('n')}"
        )
    lines.extend(["", "## Ablation Δ_info", ""])
    for k, v in (report.get("ablation") or {}).items():
        lines.append(f"- {k}: {v.get('delta_info')}")
    lines.append("")
    mpath.write_text("\n".join(lines), encoding="utf-8")
    report["artifact_json"] = str(jpath).replace("\\", "/")
    report["artifact_md"] = str(mpath).replace("\\", "/")
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rounds", type=int, default=3, help="Target complete full sessions per profile")
    p.add_argument("--cadence", type=float, default=1.0)
    p.add_argument("--evaluate-only", action="store_true", help="Skip capture; evaluate existing full sessions")
    p.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore existing sessions; always run rounds*profiles new captures",
    )
    p.add_argument(
        "--force-reopen-same-construction",
        action="store_true",
        help="FORBIDDEN for normal ops — required to bypass closed prediction branch",
    )
    args = p.parse_args()
    from lib.rid_electrical_policy import LIFECYCLE, PREDICTION_BRANCH

    closed = OUT_DIR / "CLOSED_PREDICTION_BRANCH.json"
    if closed.is_file() and not args.evaluate_only and not args.force_reopen_same_construction:
        print(
            json.dumps(
                {
                    "ok": False,
                    "refused": True,
                    "lifecycle": LIFECYCLE,
                    "prediction_branch": PREDICTION_BRANCH,
                    "reason": (
                        "Prediction branch closed after decisive negative Δ_info. "
                        "Do not collect more of the same measurement construction. "
                        "Use --evaluate-only to replay frozen corpus, or reopen only "
                        "under REOPEN_CONDITIONS in lib/rid_electrical_policy.py."
                    ),
                },
                indent=2,
            ),
            flush=True,
        )
        return 2
    summaries = []
    if not args.evaluate_only:
        summaries = run_rounds(
            max(1, int(args.rounds)),
            cadence_s=float(args.cadence),
            resume=not bool(args.no_resume),
        )
    # After capture, also refresh role card from decisive evidence
    report = evaluate_decisive()
    report["campaign_sessions"] = summaries
    Path(report["artifact_json"]).write_text(json.dumps(report, indent=2), encoding="utf-8")
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "rid_electrical_role_decision",
            FOUNDATION / "scripts" / "rid_electrical_role_decision.py",
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            role = mod.decide()
            report["role_decision"] = {
                "outcome": role.get("outcome"),
                "disposition": role.get("disposition"),
            }
            Path(report["artifact_json"]).write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
    except Exception as exc:  # noqa: BLE001
        report["role_decision_error"] = str(exc)
    print(json.dumps({k: v for k, v in report.items() if k != "campaign_sessions"}, indent=2), flush=True)
    if summaries:
        print(
            json.dumps(
                {"campaign_n": len(summaries), "ids": [s.get("session_id") for s in summaries]},
                indent=2,
            ),
            flush=True,
        )
    print("[decisive] DONE", flush=True)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
