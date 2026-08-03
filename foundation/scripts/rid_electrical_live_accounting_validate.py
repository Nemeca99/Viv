#!/usr/bin/env python3
"""Live accounting validation for eval_duration_v1.

Seeds drift log from eval_duration_validation_latest.json (in-domain actions),
evaluates live RMSE with n>=20 gate, writes live_accounting_validation_latest.*.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_live_accounting_validate.py
  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_live_accounting_validate.py --no-seed
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
from lib.rid_electrical_drift_check import (  # noqa: E402
    DRIFT_LOG_PATH,
    LOCKED_REVALIDATION_FINGERPRINT,
    evaluate_live_accounting,
    load_drift_log,
    make_revalidation_fingerprint,
    record_accounting_use,
)
from lib.rid_electrical_policy import (  # noqa: E402
    apply_live_accounting_verdict,
    policy_stamp,
)
from lib.rid_electrical_predictor import DOMAIN_MAX_S, DOMAIN_MIN_S, PLANT_CONFIG_ID  # noqa: E402

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
SESSIONS = AUTO_ARTIFACTS / "rid_electrical" / "sessions"
VALIDATION_JSON = OUT / "eval_duration_validation_latest.json"
LATEST_JSON = OUT / "live_accounting_validation_latest.json"
LATEST_MD = OUT / "live_accounting_validation_latest.md"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _gpu_temp_from_session(session_id: str | None) -> float | None:
    if not session_id:
        return None
    art = SESSIONS / str(session_id) / "controlled_action_v2.json"
    if not art.exists():
        return None
    try:
        full = json.loads(art.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    temps = full.get("temperatures") or {}
    t = temps.get("gpu_temp_c_settle")
    try:
        return float(t) if t is not None else None
    except (TypeError, ValueError):
        return None


def seed_from_validation(*, truncate: bool = True) -> list[dict]:
    """Replay validation actions into the drift log as live accounting uses."""
    if not VALIDATION_JSON.exists():
        raise FileNotFoundError(str(VALIDATION_JSON))
    data = json.loads(VALIDATION_JSON.read_text(encoding="utf-8"))
    actions = data.get("actions") or []
    if truncate:
        DRIFT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DRIFT_LOG_PATH.write_text("", encoding="utf-8")

    records: list[dict] = []
    for i, act in enumerate(actions):
        t_eval = act.get("eval_duration_s")
        e_net = act.get("E_net_raw_j")
        if t_eval is None or e_net is None:
            continue
        t = float(t_eval)
        if not (DOMAIN_MIN_S <= t <= DOMAIN_MAX_S):
            continue
        sid = act.get("session_id") or f"seed_action_{i}"
        residency = "warm_repeat"
        fp = make_revalidation_fingerprint(
            plant_config_id=PLANT_CONFIG_ID,
            residency=residency,
        )
        rec = record_accounting_use(
            t,
            float(e_net),
            session_id=str(sid),
            plant_config_id=PLANT_CONFIG_ID,
            gpu_temp_settle_c=_gpu_temp_from_session(sid),
            residency=residency,
            revalidation_fingerprint=fp,
            append=True,
        )
        records.append(rec)
    return records


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--no-seed",
        action="store_true",
        help="Do not reseeds from validation artifact; evaluate existing drift log only",
    )
    p.add_argument(
        "--append-seed",
        action="store_true",
        help="Seed without truncating existing drift log",
    )
    args = p.parse_args()

    seeded: list[dict] = []
    if not args.no_seed:
        seeded = seed_from_validation(truncate=not args.append_seed)

    records = load_drift_log()
    verdict = evaluate_live_accounting(records)
    policy_update = apply_live_accounting_verdict(verdict["status"])

    report = {
        "ok": True,
        "at": _utc(),
        "protocol": "rid_electrical_live_accounting_validation_v1",
        "source_validation_artifact": str(VALIDATION_JSON).replace("\\", "/"),
        "drift_log": str(DRIFT_LOG_PATH).replace("\\", "/"),
        "n_seeded": len(seeded),
        "n_log_rows": len(records),
        "locked_revalidation_fingerprint": LOCKED_REVALIDATION_FINGERPRINT,
        "evaluation": verdict,
        "policy_update": policy_update,
        "authority": {
            "accounting_estimates_authorized": True,
            "live_accounting_validated": bool(verdict.get("live_accounting_validated")),
            "predictor_stale": bool(verdict.get("predictor_stale")),
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "predictor_blocked_meaning": (
                "blocked_from_operational_control_not_guarded_accounting"
            ),
        },
        "policy": policy_stamp(),
    }
    LATEST_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# Live accounting validation",
        "",
        f"- **Status:** `{verdict.get('status')}`",
        f"- **n_usable:** {verdict.get('n_usable')} (min={verdict.get('min_live_n')})",
        f"- **RMSE_live (J):** {verdict.get('rmse_live_j')}",
        f"- **RMSE_heldout (J):** {verdict.get('heldout_rmse_j')}",
        f"- **Threshold (1.5x heldout):** {verdict.get('drift_alert_threshold_j')}",
        f"- **Validated:** {verdict.get('live_accounting_validated')}",
        f"- **Stale:** {verdict.get('predictor_stale')}",
        "- **Operational authority:** false",
        "- **Master routing:** false",
        "- **Auto admit:** false",
        "",
        str(verdict.get("note") or ""),
        "",
    ]
    LATEST_MD.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": verdict.get("status"),
                "n_usable": verdict.get("n_usable"),
                "rmse_live_j": verdict.get("rmse_live_j"),
                "artifact": str(LATEST_JSON).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
