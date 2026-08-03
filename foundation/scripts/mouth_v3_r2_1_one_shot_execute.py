#!/usr/bin/env python3
"""One-shot authorize_once + single governed run for mouth V3 R2.1 plan v5.

Operator-authorized only. No retry on abort. No promotion/deployment.
"""
from __future__ import annotations

import json
import traceback
from pathlib import Path

import mouth_v3_r2_1_targeted_patch_experiment as exp


def _log(log_path: Path, event: str, **payload: object) -> None:
    row = {"event": event, **payload}
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")
    print(json.dumps(row, ensure_ascii=True, default=str), flush=True)


def main() -> int:
    root = exp.CAMPAIGN_ROOT
    log_path = root / "ONE_SHOT_EXECUTION_LOG.jsonl"
    decision_path = root / "FINAL_DECISION_REPORT.json"

    plan = exp._load_json(root / "campaign_plan.json")
    if plan.get("schema_version") != exp.PRODUCTION_PLAN_SCHEMA:
        raise SystemExit(f"plan_schema_not_v5:{plan.get('schema_version')}")
    if plan.get("run_authorized") is not False:
        raise SystemExit("run_authorized_must_start_false")
    if plan.get("training_authorized") is not False:
        raise SystemExit("training_authorized_must_stay_false")
    out_root = Path(plan["checkpoint_paths"]["run_root"])
    if out_root.exists():
        raise SystemExit(f"output_root_exists_abort:{out_root}")

    _log(
        log_path,
        "one_shot_start",
        experiment_id=exp.EXPERIMENT_ID,
        campaign_root=str(root),
        plan_sha_pre=exp._file_sha256(root / "campaign_plan.json"),
        schema=plan.get("schema_version"),
    )

    auth = exp.authorize_once(campaign_root=root)
    _log(
        log_path,
        "authorize_once_done",
        **{
            k: auth.get(k)
            for k in (
                "ok",
                "plan_sha256",
                "run_authorized",
                "training_authorized",
                "token_path",
                "token_status",
            )
        },
    )
    if auth.get("ok") is not True:
        raise SystemExit("authorize_once_failed")
    if auth.get("training_authorized") is not False:
        raise SystemExit("authorize_once_training_authorized_must_remain_false")
    if auth.get("run_authorized") is not True:
        raise SystemExit("authorize_once_run_authorized_false")

    authorized_sha = str(auth["plan_sha256"])
    plan2 = exp._load_json(root / "campaign_plan.json")
    if plan2.get("schema_version") != exp.PRODUCTION_PLAN_SCHEMA:
        raise SystemExit(f"post_auth_schema_not_v5:{plan2.get('schema_version')}")
    if plan2.get("training_authorized") is not False:
        raise SystemExit("post_auth_training_authorized_true")

    try:
        result = exp.run_experiment(
            campaign_root=root,
            expected_plan_sha256=authorized_sha,
        )
        _log(
            log_path,
            "run_experiment_returned",
            ok=result.get("ok"),
            pass_=result.get("pass"),
            token_consumed=result.get("token_consumed"),
            lease_opened=result.get("lease_opened"),
            decision=(result.get("decision") or {}).get("decision"),
        )
    except Exception as exc:  # noqa: BLE001 — one-shot; capture and stop
        _log(
            log_path,
            "run_experiment_aborted_no_retry",
            error=f"{type(exc).__name__}:{exc}",
            traceback=traceback.format_exc()[-4000:],
        )
        plan_after = exp._load_json(root / "campaign_plan.json")
        token_path = exp.named_authorization_path(exp.EXPERIMENT_ID)
        token = exp._load_json(token_path) if token_path.is_file() else None
        abort_report = {
            "schema_version": "mouth_v3_r2_1_final_decision_report_v1",
            "experiment_id": exp.EXPERIMENT_ID,
            "plan_schema": plan_after.get("schema_version"),
            "outcome": "ABORT",
            "ok": False,
            "error": f"{type(exc).__name__}:{exc}",
            "no_retry": True,
            "no_promotion": True,
            "no_deployment": True,
            "run_authorized": plan_after.get("run_authorized"),
            "training_authorized": plan_after.get("training_authorized"),
            "token": token,
            "authorized_plan_sha256": authorized_sha,
        }
        exp._write_json(decision_path, abort_report)
        _log(
            log_path,
            "final_decision_written",
            path=str(decision_path),
            outcome="ABORT",
        )
        return 2

    plan_after = exp._load_json(root / "campaign_plan.json")
    token_path = exp.named_authorization_path(exp.EXPERIMENT_ID)
    token = exp._load_json(token_path) if token_path.is_file() else None
    decision = result.get("decision") or {}
    report = {
        "schema_version": "mouth_v3_r2_1_final_decision_report_v1",
        "experiment_id": exp.EXPERIMENT_ID,
        "plan_schema": plan_after.get("schema_version"),
        "outcome": decision.get("decision")
        or ("WIN" if result.get("pass") else "ABORT"),
        "ok": bool(result.get("ok")),
        "pass": result.get("pass"),
        "decision": decision,
        "token_consumed": result.get("token_consumed"),
        "lease_opened": result.get("lease_opened"),
        "train_result_ok": (result.get("train_result") or {}).get("ok"),
        "eval_checkpoint_steps": [
            r.get("checkpoint_step")
            for r in (
                (result.get("eval_bundle") or {}).get("checkpoint_reports") or []
            )
        ],
        "incumbent_legacy_goals_pass": (
            (result.get("eval_bundle") or {}).get("incumbent_report") or {}
        ).get("legacy_goals_pass"),
        "finally": result.get("finally"),
        "no_retry": True,
        "no_promotion": True,
        "no_deployment": True,
        "run_authorized": plan_after.get("run_authorized"),
        "training_authorized": plan_after.get("training_authorized"),
        "token": token,
        "authorized_plan_sha256": authorized_sha,
        "output_root": str(out_root).replace("\\", "/"),
        "eval_bundle": result.get("eval_bundle"),
        "train_result": result.get("train_result"),
    }
    exp._write_json(decision_path, report)
    _log(
        log_path,
        "final_decision_written",
        path=str(decision_path),
        outcome=report["outcome"],
        run_authorized=plan_after.get("run_authorized"),
        training_authorized=plan_after.get("training_authorized"),
        token_status=(token or {}).get("status"),
    )
    print("ONE_SHOT_COMPLETE", report["outcome"], flush=True)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
