#!/usr/bin/env python3
"""Run explanatory audit on existing token-matrix sessions (offline, no new plant run).

Freezes token verdict and audits eval_duration/actual_eval_tokens/tokens_per_s/
P_mean/gpu_temp/num_predict as E_net explanatory candidates.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_explanatory_audit.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_explanatory_audit import (  # noqa: E402
    CANDIDATE_KEYS,
    extract_features,
    run_audit,
)
from lib.rid_electrical_policy import policy_stamp  # noqa: E402

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
SESSIONS = AUTO_ARTIFACTS / "rid_electrical" / "sessions"
MATRIX_LATEST = OUT / "token_matrix_v2_latest.json"
FREEZE_PATH = OUT / "TOKEN_VERDICT_FROZEN.json"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    if not MATRIX_LATEST.exists():
        print(json.dumps({"error": "token_matrix_v2_latest.json not found"}))
        return 1

    matrix = json.loads(MATRIX_LATEST.read_text(encoding="utf-8"))
    baseline_decision = (
        (matrix.get("evaluation") or {}).get("milestone") or {}
    ).get("campaign_decision", "unknown")

    # Ensure freeze artifact is current
    if not FREEZE_PATH.exists():
        ms = (matrix.get("evaluation") or {}).get("milestone") or {}
        freeze = {
            "at": _utc(),
            "verdict": baseline_decision,
            "source_artifact": str(MATRIX_LATEST).replace("\\", "/"),
            "auto_admit": False,
            "token_cost_curve_authorized": False,
            "learning_admission_withheld": True,
        }
        FREEZE_PATH.write_text(json.dumps(freeze, indent=2), encoding="utf-8")

    admission_actions = [
        a for a in (matrix.get("actions") or [])
        if a.get("matrix_role") != "forensic"
    ]
    print(
        f"[audit] loading {len(admission_actions)} admission actions from sessions",
        flush=True,
    )
    features = []
    for act in admission_actions:
        feat = extract_features(act, SESSIONS)
        features.append(feat)
        sid = act.get("session_id", "?")[:40]
        print(
            f"[audit] {sid} np={feat.get('num_predict')} "
            f"E_net={feat.get('E_net_raw_j')} eval_dur={feat.get('eval_duration_s')} "
            f"eval_tok={feat.get('actual_eval_tokens')} tps={feat.get('tokens_per_s')}",
            flush=True,
        )

    audit = run_audit(features, baseline_decision=baseline_decision, candidates=list(CANDIDATE_KEYS))

    report = {
        "ok": True,
        "at": _utc(),
        "protocol": "rid_electrical_explanatory_audit_v1",
        "token_baseline_decision": baseline_decision,
        "overall_decision": audit["overall_decision"],
        "best_candidates": audit.get("best_candidates") or [],
        "n_features": audit["n_features"],
        "candidates_audited": audit["candidates_audited"],
        "correlations": audit["correlations"],
        "candidate_results": audit["candidate_results"],
        "decomposition_rows": audit["decomposition_rows"],
        "learning_admission_withheld": True,
        "auto_admit": False,
        "predictor_authorized": False,
        "policy": policy_stamp(),
    }

    jpath = OUT / "explanatory_audit_latest.json"
    mpath = OUT / "explanatory_audit_latest.md"
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Build human-readable summary
    lines = [
        "# Explanatory audit: token-energy candidates",
        "",
        f"- **Token baseline:** `{baseline_decision}`",
        f"- **Overall decision:** `{audit['overall_decision']}`",
        f"- **Best candidates:** {audit.get('best_candidates') or []}",
        "- **Learning admission:** withheld (`auto_admit=false`)",
        "",
        "## Correlations with E_net",
        "",
    ]
    for c in audit["correlations"]:
        lines.append(
            f"- `{c['candidate']}`: r2={c.get('r2')} spearman={c.get('spearman')} n={c.get('n')}"
        )
    lines.append("")
    lines.append("## Candidate bin-separability results")
    lines.append("")
    for cr in audit["candidate_results"]:
        lines.append(f"### `{cr['candidate']}` — `{cr['classification']}`")
        for bev in cr.get("bin_evals") or []:
            lines.append(
                f"  - bin{bev.get('bin_i')}: outcome=`{bev.get('outcome')}` "
                f"range={bev.get('bin_candidate_range')} "
                f"mu_E={bev.get('mu_E_net_raw_j')} CV_E={bev.get('CV_E')} "
                f"SNR={bev.get('SNR_net')}"
            )
        sep = cr.get("separability") or {}
        lines.append(
            f"  - separability: {sep.get('n_separable_pairs')}/{sep.get('n_pairs')} pairs sep"
        )
        lines.append("")
    lines.append("## Phase-energy decomposition (sample)")
    lines.append("")
    for row in audit.get("decomposition_rows") or []:
        lines.append(
            f"- np={row.get('num_predict')} eval_dur={row.get('eval_duration_s')} "
            f"E_net={row.get('E_net_raw_j')} E_eval={row.get('E_token_eval_j')} "
            f"E_load={row.get('E_load_j')} resid={row.get('E_residual_j')}"
        )
    lines.append("")
    mpath.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "overall_decision": audit["overall_decision"],
                "best_candidates": audit.get("best_candidates"),
                "top_correlation": (audit["correlations"][0] if audit["correlations"] else None),
                "artifact": str(jpath).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
