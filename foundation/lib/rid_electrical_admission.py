#!/usr/bin/env python3
"""Predefined multi-window acceptance criteria for electrical lane advancement.

The lane remains measured in shadow until positive Δ_info appears across
multiple independent, sufficiently dynamic unseen windows. One strong
isolated window never advances the lane.

Criteria (locked):
  - MIN_PASSING_WINDOWS independent archived shadow A/B reports
  - each: dynamic Master (variance >= MASTER_VAR_MIN)
  - each: Δ_info >= MAE_IMPROVE_MIN on held-out tail
  - each: valid_shadow_rows >= MIN_VALID
  - windows non-overlapping in wall-clock (by report `at` + duration)
  - geom reweight ignored for advancement
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
ARCHIVE_DIR = OUT_DIR / "shadow_ab_windows"
LATEST_MULTI = OUT_DIR / "multiwindow_gate_latest.json"

# --- Predefined acceptance criteria (do not soften ad hoc) ---
MIN_PASSING_WINDOWS = 3
MIN_VALID = 10
MAE_IMPROVE_MIN = 0.005
MASTER_VAR_MIN = 1e-12
MIN_WINDOW_SEPARATION_S = 60.0  # independence: wall-clock gap between window ends/starts
EXPERIMENT_ID = "rid_electrical_shadow_ab_v2"


def _parse_at(at: str | None) -> datetime | None:
    if not at:
        return None
    try:
        return datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        return None


def window_passes_acceptance(report: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one archived shadow A/B report against predefined criteria."""
    window = report.get("window") or {}
    dep = report.get("dependence") or {}
    di = report.get("delta_info") or {}
    delta = di.get("delta_info")
    master_var = dep.get("master_s_n_variance")
    valid_n = int(window.get("valid_shadow_rows") or 0)
    dynamic = master_var is not None and float(master_var) >= MASTER_VAR_MIN
    positive = delta is not None and float(delta) >= MAE_IMPROVE_MIN
    enough = valid_n >= MIN_VALID
    # Explicitly ignore geom for pass/fail
    geom = report.get("geom_reweight") or {}
    reasons: list[str] = []
    if not enough:
        reasons.append("insufficient_valid_rows")
    if not dynamic:
        reasons.append("master_not_sufficiently_dynamic")
    if not positive:
        reasons.append("delta_info_not_positive")
    ok = enough and dynamic and positive
    return {
        "passes": ok,
        "reasons": reasons,
        "valid_shadow_rows": valid_n,
        "master_s_n_variance": master_var,
        "delta_info": delta,
        "geom_delta_mean": geom.get("delta_mean"),
        "geom_ignored_for_advancement": True,
        "at": report.get("at"),
        "duration_s": window.get("duration_s"),
        "verdict": report.get("verdict"),
        "artifact": report.get("artifact_json"),
    }


def _window_interval(report: dict[str, Any]) -> tuple[datetime, datetime] | None:
    start = _parse_at(report.get("at"))
    if start is None:
        return None
    # `at` is end-ish; approximate start = at - duration
    dur = float((report.get("window") or {}).get("duration_s") or 0.0)
    from datetime import timedelta

    end = start
    begin = start - timedelta(seconds=max(0.0, dur))
    return begin, end


def windows_independent(reports: list[dict[str, Any]]) -> bool:
    """True when intervals are non-overlapping and separated by MIN_WINDOW_SEPARATION_S."""
    intervals: list[tuple[datetime, datetime]] = []
    for r in reports:
        iv = _window_interval(r)
        if iv is None:
            return False
        intervals.append(iv)
    intervals.sort(key=lambda x: x[0])
    for i in range(1, len(intervals)):
        prev_end = intervals[i - 1][1]
        cur_start = intervals[i][0]
        gap = (cur_start - prev_end).total_seconds()
        if gap < MIN_WINDOW_SEPARATION_S:
            return False
    return True


def archive_window_report(report: dict[str, Any]) -> Path:
    """Persist a stamped copy for multi-window accumulation."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    at = (report.get("at") or _utc_stamp()).replace(":", "").replace("+", "p")
    path = ARCHIVE_DIR / f"window_{at}.json"
    # Avoid storing full row payloads twice if huge — keep evidence, drop rows if present
    slim = dict(report)
    if "rows" in slim and isinstance(slim["rows"], list) and len(slim["rows"]) > 0:
        slim["rows_n"] = len(slim["rows"])
        slim["rows"] = slim["rows"]  # keep for replay; archive is evidence
    path.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    return path


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_archived_windows() -> list[dict[str, Any]]:
    if not ARCHIVE_DIR.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(ARCHIVE_DIR.glob("window_*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def evaluate_multiwindow(reports: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Archival multi-window eval — advancement permanently closed after negative decisive.

    Computes historical pass counts for evidence replay, but never sets
    lane_advancement_eligible True under rejected_operational_use.
    """
    from lib.rid_electrical_policy import LIFECYCLE, RAIL_ROLE, policy_stamp

    reports = reports if reports is not None else load_archived_windows()
    evaluated = [window_passes_acceptance(r) for r in reports]
    passing_reports = [r for r, e in zip(reports, evaluated) if e["passes"]]
    passing_evals = [e for e in evaluated if e["passes"]]

    selected: list[dict[str, Any]] = []
    selected_reports: list[dict[str, Any]] = []
    for r, e in zip(passing_reports, passing_evals):
        trial = selected_reports + [r]
        if windows_independent(trial):
            selected_reports.append(r)
            selected.append(e)

    n_pass = len(selected)
    return {
        "ok": True,
        "at": _utc_stamp(),
        "lifecycle": LIFECYCLE,
        "rail_role": RAIL_ROLE,
        "prediction_branch": "closed_negative_result",
        "lane_advancement_eligible": False,
        "supports_admission_review": False,
        "admission_granted": False,
        "electrical_in_A_t": False,
        "historical_passing_independent_n": n_pass,
        "would_have_met_min_windows": n_pass >= MIN_PASSING_WINDOWS,
        "criteria": {
            "min_passing_windows": MIN_PASSING_WINDOWS,
            "min_valid": MIN_VALID,
            "mae_improve_min": MAE_IMPROVE_MIN,
            "master_var_min": MASTER_VAR_MIN,
            "min_window_separation_s": MIN_WINDOW_SEPARATION_S,
            "geom_reweight_counts_as_evidence": False,
            "isolated_strong_window_advances_lane": False,
            "advancement_permanently_closed": True,
        },
        "archive_n": len(reports),
        "passing_independent_n": 0,
        "passing_windows": [],
        "all_window_evals": evaluated,
        "policy": policy_stamp(),
        "rule": (
            "Prediction branch closed (rejected_operational_use). Multi-window "
            "Master-weight advancement is obsolete. Rails remain observe_only_diagnostics. "
            "Historical window evals retained for evidence replay only."
        ),
    }


def write_multiwindow_report(payload: dict[str, Any]) -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = payload["at"].replace(":", "").replace("+", "p")
    stamped = OUT_DIR / f"multiwindow_gate_{stamp}.json"
    text = json.dumps(payload, indent=2)
    stamped.write_text(text, encoding="utf-8")
    LATEST_MULTI.write_text(text, encoding="utf-8")
    md = "\n".join(
        [
            "# Electrical multi-window advancement gate — CLOSED",
            "",
            f"- **Lifecycle:** {payload.get('lifecycle')}",
            f"- **lane_advancement_eligible:** {payload['lane_advancement_eligible']}",
            f"- **supports_admission_review:** {payload['supports_admission_review']}",
            f"- **admission_granted:** false",
            f"- **Historical passing (archival):** "
            f"{payload.get('historical_passing_independent_n', 0)}",
            f"- **Archived windows:** {payload['archive_n']}",
            "",
            payload["rule"],
            "",
        ]
    )
    md_path = OUT_DIR / "multiwindow_gate_latest.md"
    md_path.write_text(md, encoding="utf-8")
    payload["artifact_json"] = str(stamped).replace("\\", "/")
    payload["artifact_md"] = str(md_path).replace("\\", "/")
    payload["latest"] = str(LATEST_MULTI).replace("\\", "/")
    return payload
