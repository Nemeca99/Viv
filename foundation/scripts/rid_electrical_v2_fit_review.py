#!/usr/bin/env python3
"""V2 fit review: freeze-backed session-safe fit + gates + V1 compare.

Does not unfreeze V1. Writes PREDICTOR_CANDIDATE_V2.json only on proceed ladder.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_v2_fit_review.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_decomposition_corpus_freeze import (  # noqa: E402
    load_frozen_corpus,
    write_freeze,
)
from lib.rid_electrical_policy import PREDICTOR_V1_FROZEN, policy_stamp  # noqa: E402
from lib.rid_electrical_predictor_v2 import (  # noqa: E402
    PREDICTOR_VERSION,
    clear_candidate_cache,
)
from lib.rid_electrical_v2_fit import run_v2_fit_pipeline  # noqa: E402

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _md(report: dict) -> str:
    g = report.get("gates") or {}
    lad = report.get("decision_ladder") or {}
    ov = report.get("v1_overlap_compare") or {}
    hs = report.get("holdout_summary") or {}
    lines = [
        "# V2 fit review",
        "",
        f"- at: `{report.get('at')}`",
        f"- decision: `{lad.get('decision')}`",
        f"- proceed_to_prospective: `{lad.get('proceed_to_prospective')}`",
        f"- gates_all_pass: `{(g.get('all_pass'))}`",
        f"- holdout median_eps: `{hs.get('median_eps')}`",
        f"- holdout MAE_j: `{hs.get('mae_j')}`",
        f"- holdout rel_mae: `{hs.get('rel_mae')}`",
        f"- ΔMAE (V1−V2) overlap: `{ov.get('delta_mae_j')}`",
        f"- predictor_v1_frozen: `{PREDICTOR_V1_FROZEN}`",
        f"- accounting_predictor_v2_approved: `False`",
        "",
        "## Gate checks",
        "",
    ]
    for k, v in (g.get("checks") or {}).items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--skip-freeze",
        action="store_true",
        help="Use existing DECOMPOSITION_CORPUS_FROZEN_V1.json",
    )
    args = p.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    if not args.skip_freeze:
        freeze = write_freeze(out_dir=OUT)
        if not freeze.get("ok"):
            print(json.dumps({"error": "freeze_failed", "freeze": freeze}, indent=2))
            return 1

    manifest, rows = load_frozen_corpus(out_dir=OUT, verify_hashes=True)
    # Ensure freeze sources not rewritten: record source hashes again post-load
    pipeline = run_v2_fit_pipeline(rows)
    if not pipeline.get("ok"):
        print(json.dumps(pipeline, indent=2))
        return 1

    assert PREDICTOR_V1_FROZEN is True

    report = {
        "ok": True,
        "at": _utc(),
        "protocol": "rid_electrical_v2_fit_review_v1",
        "freeze_id": manifest.get("freeze_id"),
        "freeze_n_actions": manifest.get("n_actions"),
        "predictor_version": PREDICTOR_VERSION,
        "predictor_v1_frozen": True,
        "refit_v1_forbidden": True,
        **pipeline,
        "policy": policy_stamp(),
    }

    jpath = OUT / "v2_fit_review_latest.json"
    mpath = OUT / "v2_fit_review_latest.md"
    # Drop bulky fold details already summarized
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
    mpath.write_text(_md(report), encoding="utf-8")

    proceed = bool((report.get("decision_ladder") or {}).get("proceed_to_prospective"))
    cand_path = OUT / "PREDICTOR_CANDIDATE_V2.json"
    if proceed:
        cand = {
            "ok": True,
            "at": _utc(),
            "predictor_version": PREDICTOR_VERSION,
            "status": "v2_fit_candidate_pending_prospective",
            "decision": (report.get("decision_ladder") or {}).get("decision"),
            "coefficients": report.get("coefficients"),
            "heldout_rmse_j": (report.get("holdout_summary") or {}).get("rmse_j"),
            "gates": report.get("gates"),
            "v1_overlap_compare": report.get("v1_overlap_compare"),
            "freeze_id": manifest.get("freeze_id"),
            "authority": {
                "operational_authority": False,
                "master_routing_authorized": False,
                "auto_admit": False,
                "accounting_predictor_v2_approved": False,
                "predictor_v1_frozen": True,
            },
            "note": (
                "Candidate coefficients for prospective validation only. "
                "V1 remains approved accounting fallback."
            ),
        }
        cand_path.write_text(json.dumps(cand, indent=2), encoding="utf-8")
        clear_candidate_cache()
    else:
        if cand_path.exists():
            # Do not delete silently; write reject marker alongside
            reject = OUT / "PREDICTOR_CANDIDATE_V2_REJECTED.json"
            reject.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "at": _utc(),
                        "decision": (report.get("decision_ladder") or {}).get(
                            "decision"
                        ),
                        "note": "Gates/ladder did not authorize candidate write",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

    summary = {
        "ok": True,
        "decision": (report.get("decision_ladder") or {}).get("decision"),
        "proceed_to_prospective": proceed,
        "gates_all_pass": (report.get("gates") or {}).get("all_pass"),
        "holdout": report.get("holdout_summary"),
        "v1_overlap": report.get("v1_overlap_compare"),
        "candidate_written": proceed,
        "artifact_json": str(jpath).replace("\\", "/"),
        "candidate": str(cand_path).replace("\\", "/") if proceed else None,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
