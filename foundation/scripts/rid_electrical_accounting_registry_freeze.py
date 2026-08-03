#!/usr/bin/env python3
"""Freeze ACCOUNTING_REGISTRY_RELEASE_V1 (hashes + locked values; no source mutation).

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_accounting_registry_freeze.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_accounting_registry_release import (  # noqa: E402
    RELEASE_ID,
    sha256_file,
)
from lib.rid_electrical_drift_check import (  # noqa: E402
    DRIFT_RMSE_MULT,
    LOCKED_REVALIDATION_FINGERPRINT,
)
from lib.rid_electrical_policy import policy_stamp  # noqa: E402
from lib.rid_electrical_predictor import (  # noqa: E402
    ALPHA,
    BETA,
    DOMAIN_MAX_S,
    DOMAIN_MIN_S,
    HELD_OUT_RMSE_J,
    PLANT_CONFIG_ID,
    PREDICTOR_VERSION,
)

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
V1_FREEZE = OUT / "PREDICTOR_V1_BASELINE_FROZEN.json"
V2_CAND = OUT / "PREDICTOR_CANDIDATE_V2.json"
V2_APPR = OUT / "PREDICTOR_V2_APPROVED.json"
V2_SCALES = OUT / "V2_UNCERTAINTY_SCALES.json"
V2_RMSE = OUT / "V2_VALIDATED_RMSE.json"
RELEASE_JSON = OUT / "ACCOUNTING_REGISTRY_RELEASE_V1.json"
RELEASE_MD = OUT / "ACCOUNTING_REGISTRY_RELEASE_V1.md"

SELECTION_RULES = (
    "Predictor(x) = V1 if warm-resident eval-only and "
    f"{DOMAIN_MIN_S} ≤ t_eval ≤ {DOMAIN_MAX_S} "
    "and no cold load and no expanded tail / prompt decomposition; "
    "V2 if cold load, prompt-decomposition, or defined tail accounting "
    "AND mapped component ∈ approved_components; "
    "null outside either validated domain, when V2 stale on expanded domain, "
    "or when component ∈ rejected_components "
    "(tail_5, warm_prompt_eval never use nearby horizon/coeff fallback)."
)

CLOSED_NEGATIVE_REOPEN = {
    "strata": ["tail_5", "warm_prompt_eval"],
    "status": "closed_negative",
    "release_id": RELEASE_ID,
    "reopen_requires": (
        "named separate campaign with predeclared measurement/control changes"
    ),
    "repeated_sampling_alone_insufficient": True,
}


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    missing = [p for p in (V1_FREEZE, V2_CAND, V2_APPR, V2_SCALES) if not p.exists()]
    if missing:
        print(
            json.dumps(
                {
                    "error": "missing_required_artifacts",
                    "missing": [str(m).replace("\\", "/") for m in missing],
                },
                indent=2,
            )
        )
        return 1

    v1 = json.loads(V1_FREEZE.read_text(encoding="utf-8"))
    v2 = json.loads(V2_CAND.read_text(encoding="utf-8"))
    appr = json.loads(V2_APPR.read_text(encoding="utf-8"))
    scales = json.loads(V2_SCALES.read_text(encoding="utf-8"))
    v2_rmse = None
    if V2_RMSE.exists():
        v2_rmse = json.loads(V2_RMSE.read_text(encoding="utf-8"))

    approved = list(appr.get("approved_components") or [])
    rejected = list(appr.get("rejected_components") or ["tail_5", "warm_prompt_eval"])

    v1_rmse = float(
        (v1.get("uncertainty") or {}).get("heldout_rmse_j") or HELD_OUT_RMSE_J
    )
    v2_validated = None
    if v2_rmse and v2_rmse.get("validated_rmse_j") is not None:
        v2_validated = float(v2_rmse["validated_rmse_j"])
    else:
        v2_validated = float(
            v2.get("heldout_rmse_j")
            or (v2.get("coefficients") or {}).get("heldout_rmse_j")
            or 0.0
        )

    sources = {
        "PREDICTOR_V1_BASELINE_FROZEN": {
            "path": str(V1_FREEZE).replace("\\", "/"),
            "sha256": sha256_file(V1_FREEZE),
        },
        "PREDICTOR_CANDIDATE_V2": {
            "path": str(V2_CAND).replace("\\", "/"),
            "sha256": sha256_file(V2_CAND),
        },
        "PREDICTOR_V2_APPROVED": {
            "path": str(V2_APPR).replace("\\", "/"),
            "sha256": sha256_file(V2_APPR),
        },
        "V2_UNCERTAINTY_SCALES": {
            "path": str(V2_SCALES).replace("\\", "/"),
            "sha256": sha256_file(V2_SCALES),
            "values": scales.get("scales"),
            "fallback_rmse_j": scales.get("fallback_rmse_j"),
        },
        "V2_VALIDATED_RMSE": {
            "path": str(V2_RMSE).replace("\\", "/") if V2_RMSE.exists() else None,
            "sha256": sha256_file(V2_RMSE),
            "validated_rmse_j": v2_validated,
        },
    }

    release = {
        "ok": True,
        "at": _utc(),
        "release_id": RELEASE_ID,
        "immutable": True,
        "silent_mutate_forbidden": True,
        "status": "accounting_registry_release_frozen",
        "lifecycle_from": "accounting_predictor_v2_approved",
        "lifecycle_target": "production_accounting_registry_validated",
        "v1": {
            "predictor_version": v1.get("predictor_version") or PREDICTOR_VERSION,
            "coefficients": {
                "alpha_j": float((v1.get("coefficients") or {}).get("alpha_j", ALPHA)),
                "beta_j_per_s": float(
                    (v1.get("coefficients") or {}).get("beta_j_per_s", BETA)
                ),
                "formula": (v1.get("coefficients") or {}).get("formula")
                or "E_net_hat = alpha + beta * eval_duration_s",
            },
            "domain": {
                "min_eval_duration_s": float(
                    (v1.get("domain") or {}).get("min_eval_duration_s", DOMAIN_MIN_S)
                ),
                "max_eval_duration_s": float(
                    (v1.get("domain") or {}).get("max_eval_duration_s", DOMAIN_MAX_S)
                ),
            },
            "heldout_rmse_j": v1_rmse,
            "runtime_locked_alpha_j": float(ALPHA),
            "runtime_locked_beta_j_per_s": float(BETA),
        },
        "v2": {
            "predictor_version": v2.get("predictor_version"),
            "coefficients": v2.get("coefficients"),
            "heldout_rmse_j": v2.get("heldout_rmse_j"),
            "validated_rmse_j": v2_validated,
        },
        "approved_components": approved,
        "rejected_components": rejected,
        "plant_config_id": v1.get("plant_config_id") or PLANT_CONFIG_ID,
        "revalidation_fingerprint": v1.get("revalidation_fingerprint")
        or LOCKED_REVALIDATION_FINGERPRINT,
        "drift_thresholds": {
            "mult": DRIFT_RMSE_MULT,
            "v1": {
                "validated_rmse_j": v1_rmse,
                "stale_threshold_j": DRIFT_RMSE_MULT * v1_rmse,
                "rule": "1.5 × validated RMSE",
            },
            "v2": {
                "validated_rmse_j": v2_validated,
                "stale_threshold_j": DRIFT_RMSE_MULT * float(v2_validated),
                "rule": "1.5 × validated RMSE",
            },
        },
        "registry_selection_rules": SELECTION_RULES,
        "closed_negative_reopen_policy": CLOSED_NEGATIVE_REOPEN,
        "source_artifacts": sources,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "gates_action": False,
            "accounting_read_only": True,
        },
        "policy": policy_stamp(),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    RELEASE_JSON.write_text(json.dumps(release, indent=2), encoding="utf-8")
    md = "\n".join(
        [
            "# ACCOUNTING_REGISTRY_RELEASE_V1",
            "",
            f"- release_id: `{RELEASE_ID}`",
            f"- at: `{release['at']}`",
            "- immutable: true",
            "- silent_mutate_forbidden: true",
            f"- approved_components: `{approved}`",
            f"- rejected_components: `{rejected}`",
            f"- plant_config_id: `{release['plant_config_id']}`",
            f"- V1 drift threshold: `{release['drift_thresholds']['v1']['stale_threshold_j']:.4f} J`",
            f"- V2 drift threshold: `{release['drift_thresholds']['v2']['stale_threshold_j']:.4f} J`",
            "",
            "## Selection rules",
            "",
            SELECTION_RULES,
            "",
            "## Closed-negative reopen",
            "",
            (
                f"`tail_5` / `warm_prompt_eval` closed for `{RELEASE_ID}`; "
                "reopen only via named separate campaign with predeclared "
                "measurement/control changes."
            ),
            "",
        ]
    )
    RELEASE_MD.write_text(md, encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "release_id": RELEASE_ID,
                "artifact": str(RELEASE_JSON).replace("\\", "/"),
                "md": str(RELEASE_MD).replace("\\", "/"),
                "approved_components": approved,
                "rejected_components": rejected,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
