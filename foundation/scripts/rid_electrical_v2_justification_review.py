#!/usr/bin/env python3
"""V2 justification review from decomposition evidence (no coefficient fit).

Outcomes:
  - v2_fit_justified_for_separate_review
  - retain_v1_decomposition_diagnostic_only

Never writes new coefficients; never unfreezes V1; authority flags stay false.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_v2_justification_review.py
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
from lib.rid_electrical_decomposition_eval import evaluate_decomposition_campaign  # noqa: E402
from lib.rid_electrical_policy import PREDICTOR_V1_FROZEN, policy_stamp  # noqa: E402

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def review_v2_justification(
    evidence: dict[str, Any] | None = None,
    *,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    out = Path(out_dir) if out_dir else OUT
    out.mkdir(parents=True, exist_ok=True)

    if evidence is None:
        epath = out / "decomposition_evidence_latest.json"
        if epath.exists():
            evidence = json.loads(epath.read_text(encoding="utf-8"))
        else:
            evidence = evaluate_decomposition_campaign(out_dir=out)

    status = str((evidence or {}).get("status") or "")
    closure = (evidence or {}).get("heldout_closure") or {}
    comps = (evidence or {}).get("component_summary") or {}
    closure_pass = bool(closure.get("closure_pass"))
    components_adequate = bool(comps.get("components_adequate"))
    evidence_complete = status == "decomposition_evidence_complete"

    justified = evidence_complete and closure_pass and components_adequate
    decision = (
        "v2_fit_justified_for_separate_review"
        if justified
        else "retain_v1_decomposition_diagnostic_only"
    )

    report = {
        "ok": True,
        "at": _utc(),
        "decision": decision,
        "v2_fit_justified": bool(justified),
        "v2_coefficients_written": False,
        "v2_fit_performed": False,
        "predictor_v1_frozen": bool(PREDICTOR_V1_FROZEN),
        "refit_v1_forbidden": True,
        "evidence_status": status,
        "evidence_complete": evidence_complete,
        "closure_pass": closure_pass,
        "components_adequate": components_adequate,
        "median_eps_closure": closure.get("median_eps_closure"),
        "gates_checked": {
            "decomposition_evidence_complete": evidence_complete,
            "heldout_closure_pass": closure_pass,
            "components_adequate": components_adequate,
        },
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "v2_fit_authorized": False,  # fit still requires separate explicit review
        },
        "note": (
            "Justification for a *separate* V2 fit review only. This script does not "
            "fit coefficients, unfreeze V1, or enable Master/routing."
            if justified
            else "Retain frozen V1; decomposition remains diagnostic-only."
        ),
        "policy": policy_stamp(),
        "evidence_artifact": str(
            (out / "decomposition_evidence_latest.json").resolve()
        ).replace("\\", "/"),
    }

    jpath = out / "v2_justification_review_latest.json"
    mpath = out / "v2_justification_review_latest.md"
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
    mpath.write_text(
        "\n".join(
            [
                "# V2 justification review",
                "",
                f"- decision: `{decision}`",
                f"- at: `{report['at']}`",
                f"- v2_fit_justified: `{justified}`",
                f"- v2_coefficients_written: `False`",
                f"- predictor_v1_frozen: `{PREDICTOR_V1_FROZEN}`",
                f"- evidence_status: `{status}`",
                f"- closure_pass: `{closure_pass}`",
                f"- components_adequate: `{components_adequate}`",
                "",
                report["note"],
                "",
            ]
        ),
        encoding="utf-8",
    )
    report["artifact_json"] = str(jpath).replace("\\", "/")
    report["artifact_md"] = str(mpath).replace("\\", "/")
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--reevaluate",
        action="store_true",
        help="Rebuild decomposition_evidence_latest from family artifacts first",
    )
    args = p.parse_args()

    evidence = None
    if args.reevaluate:
        evidence = evaluate_decomposition_campaign()
    report = review_v2_justification(evidence)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
