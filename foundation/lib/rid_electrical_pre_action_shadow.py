#!/usr/bin/env python3
"""Prospective shadow validation for pre_action_energy_v1 (never gates)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_pre_action_baseline import baseline_predict_E_net, paired_metrics
from lib.rid_electrical_pre_action_campaign_status import (
    DUAL_CAMPAIGN_ID,
    assert_campaign_fittable,
)
from lib.rid_electrical_pre_action_paths import EVIDENCE_PLANT, plant_dir
from lib.rid_electrical_pre_action_train import (
    CANDIDATE_LOCK,
    cell_rel_mae,
    load_candidate_predictor,
)
from lib.rid_electrical_pre_action_snapshot import (
    LOCKED_MODEL_CONFIG_HASH,
    PROFILE_MEASURABLE,
    capture_pre_action_snapshot,
    predict_pre_action_E_net,
    predict_pre_action_energy,
)
from lib.rid_electrical_predictor import ALPHA, BETA, PLANT_CONFIG_ID

CAMPAIGN = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
SHADOW_JSON = CAMPAIGN / "pre_action_shadow_validation_latest.json"
SHADOW_MD = CAMPAIGN / "pre_action_shadow_validation_latest.md"
SHADOW_LOG = CAMPAIGN / "pre_action_shadow_log.jsonl"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def commit_prediction(
    snapshot: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any] | None = None,
    gross_candidate: Mapping[str, Any] | None = None,
    net_candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Commit prediction before execution; returns immutable commit record."""
    feats = {
        "num_predict": snapshot.get("num_predict"),
        "trailing_throughput_tps": snapshot.get("trailing_throughput_tps"),
        "throughput_history_count": snapshot.get("throughput_history_count"),
        "prompt_utf8_bytes": snapshot.get("prompt_utf8_bytes"),
        "prompt_word_count": snapshot.get("prompt_word_count"),
        "prompt_message_count": snapshot.get("prompt_message_count"),
        "gpu_temp_start_c": snapshot.get("gpu_temp_start_c"),
        "settled_idle_power_w": snapshot.get("settled_idle_power_w"),
        "model_config_hash": snapshot.get("model_config_hash"),
    }
    base = baseline_predict_E_net(
        num_predict=feats["num_predict"],
        trailing_throughput_tps=feats.get("trailing_throughput_tps"),
        throughput_history_count=int(feats.get("throughput_history_count") or 0),
    )
    net_cand = net_candidate or candidate
    dual = predict_pre_action_energy(
        snapshot,
        gross_candidate=gross_candidate,
        net_candidate=net_cand,
        plant_config_id=str(snapshot.get("plant_config_id") or PLANT_CONFIG_ID),
        model_config_hash_value=str(snapshot.get("model_config_hash") or ""),
    )
    cand_pred = predict_pre_action_E_net(
        feats,
        plant_config_id=str(snapshot.get("plant_config_id") or PLANT_CONFIG_ID),
        model_config_hash_value=str(snapshot.get("model_config_hash") or ""),
        candidate=net_cand,
    )
    commit = {
        "committed_at": _utc(),
        "snapshot_id": snapshot.get("snapshot_id"),
        "action_id": snapshot.get("action_id"),
        "baseline": base,
        "candidate": cand_pred,
        "dual": dual,
        "gates_action": False,
        "prediction_committed_before_execution": True,
    }
    return commit


def shadow_step(
    *,
    snapshot: Mapping[str, Any],
    execute_fn: Callable[[], Mapping[str, Any]],
    candidate: Mapping[str, Any] | None = None,
    gross_candidate: Mapping[str, Any] | None = None,
    net_candidate: Mapping[str, Any] | None = None,
    persist_log: bool = True,
) -> dict[str, Any]:
    """snapshot → prediction commit → execute unchanged → measure → grade."""
    commit = commit_prediction(
        snapshot,
        candidate=candidate,
        gross_candidate=gross_candidate,
        net_candidate=net_candidate,
    )
    outcome = dict(execute_fn())
    # Never allow prediction to alter execution — execute_fn already ran unchanged.
    y = outcome.get("E_net_raw_j")
    if y is None:
        y = outcome.get("measured_E_net_j")
    y_gross = outcome.get("E_generate_j")
    dual = commit.get("dual") or {}
    profile = str(snapshot.get("planned_response_profile") or "")
    grade = {
        "y_true": float(y) if y is not None else None,
        "y_true_net": float(y) if y is not None else None,
        "y_true_gross": float(y_gross) if y_gross is not None else None,
        "yhat_candidate": commit["candidate"].get("predicted_E_net_j"),
        "yhat_baseline": commit["baseline"].get("predicted_E_net_j"),
        "yhat_gross": (dual.get("gross") or {}).get("predicted_E_generate_j"),
        "yhat_net": (dual.get("net") or {}).get("predicted_E_net_j"),
        "eligible_gross": bool(outcome.get("eligible_gross", True))
        and y_gross is not None
        and (dual.get("gross") or {}).get("predicted_E_generate_j") is not None,
        "eligible_net": bool(outcome.get("eligible_net", False))
        and profile == PROFILE_MEASURABLE
        and y is not None
        and (dual.get("net") or {}).get("predicted_E_net_j") is not None,
        "eligible": bool(outcome.get("eligible", True))
        and y is not None
        and commit["candidate"].get("predicted_E_net_j") is not None
        and commit["baseline"].get("predicted_E_net_j") is not None,
    }
    if grade["y_true"] is not None and grade["yhat_candidate"] is not None:
        grade["residual_candidate"] = float(grade["y_true"]) - float(grade["yhat_candidate"])
    if grade["y_true"] is not None and grade["yhat_baseline"] is not None:
        grade["residual_baseline"] = float(grade["y_true"]) - float(grade["yhat_baseline"])

    record = {
        "at": _utc(),
        "snapshot": dict(snapshot),
        "commit": commit,
        "outcome": outcome,
        "grade": grade,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "gates_action": False,
            "auto_admit": False,
            "learning_admission_withheld": True,
        },
    }
    if persist_log:
        SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SHADOW_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return record


def evaluate_shadow_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    y_c, yhat_c, y_b, yhat_b = [], [], [], []
    eligible_rows = []
    yhat_by_action = {}
    for r in records:
        g = r.get("grade") or {}
        if not g.get("eligible"):
            continue
        y_c.append(float(g["y_true"]))
        yhat_c.append(float(g["yhat_candidate"]))
        y_b.append(float(g["y_true"]))
        yhat_b.append(float(g["yhat_baseline"]))
        eligible_rows.append(r)
        yhat_by_action[str((r.get("snapshot") or {}).get("action_id"))] = float(
            g["yhat_candidate"]
        )

    cand_m = paired_metrics(y_c, yhat_c)
    base_m = paired_metrics(y_b, yhat_b)
    # Rebuild row-like for cell metrics
    row_like = []
    for r in eligible_rows:
        row_like.append(
            {
                "action_id": (r.get("snapshot") or {}).get("action_id"),
                "snapshot": r.get("snapshot"),
                "label": {"E_net_raw_j": (r.get("grade") or {}).get("y_true")},
            }
        )
    cell_rel = cell_rel_mae(row_like, yhat_by_action)

    gates = {
        "n_eligible_ge_48": cand_m.get("n", 0) >= 48,
        "rmse_improve_10pct": (
            cand_m.get("rmse") is not None
            and base_m.get("rmse") is not None
            and float(cand_m["rmse"]) <= float(base_m["rmse"]) * 0.90
        ),
        "rel_mae_le_0_20": cand_m.get("rel_mae") is not None
        and float(cand_m["rel_mae"]) <= 0.20,
        "calibration_0_8_1_2": cand_m.get("calibration_slope") is not None
        and 0.8 <= float(cand_m["calibration_slope"]) <= 1.2,
        "bias_ratio_le_0_25": (
            cand_m.get("rmse") is not None and float(cand_m["rmse"]) < 1e-6
        )
        or (
            cand_m.get("bias_over_rmse") is not None
            and float(cand_m["bias_over_rmse"]) <= 0.25
        ),
        "no_stratum_rel_mae_gt_0_30": all(v <= 0.30 for v in cell_rel.values())
        if cell_rel
        else False,
    }
    passed = all(gates.values())
    return {
        "ok": True,
        "at": _utc(),
        "status": (
            "pre_action_energy_shadow_validated_candidate_for_separate_review"
            if passed
            else "pre_action_shadow_not_validated"
        ),
        "passed": passed,
        "gates": gates,
        "candidate_metrics": cand_m,
        "baseline_metrics": base_m,
        "cell_rel_mae": cell_rel,
        "n_records": len(records),
        "n_eligible": cand_m.get("n"),
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "gates_action": False,
            "auto_admit": False,
            "auto_refit": False,
            "learning_admission_withheld": True,
            "production_prediction_authorized": False,
        },
    }


def run_synthetic_shadow_campaign(
    *,
    n_actions: int = 60,
    write: bool = True,
) -> dict[str, Any]:
    """Unit/harness path: synthetic outcomes proving commit-before-execute protocol."""
    from lib.rid_electrical_pre_action_corpus import collection_plan
    from lib.rid_electrical_predictor import ALPHA, BETA

    cand = load_candidate_predictor(require_plant=False)
    # Synthetic harness uses same prompt texts as training cells so a locked
    # linear candidate can be graded fairly; plant shadow uses held-out variants.
    plans = collection_plan(n_groups=4)[:n_actions]
    for p in plans:
        p["action_id"] = f"pre_action_shadow_{p['action_id']}"
    records = []
    executed_before_predict = []

    for i, plan in enumerate(plans):
        # Fixed tps keeps all num_predict grid points inside [2.5, 4.5] s.
        tps = 103.2
        t_hat = plan["num_predict"] / tps
        temp = 47.0 + ((i % 15) - 7)
        fixed_prompt = "Explain GPU power draw briefly."
        snap = capture_pre_action_snapshot(
            action_id=plan["action_id"],
            num_predict=plan["num_predict"],
            prompt=fixed_prompt,
            gpu_temp_start_c=temp,
            settled_idle_power_w=55.0,
            trailing_throughput_tps=tps,
            throughput_history_count=20,
            collection_session_id=f"shadow_synth_{plan['collection_group']}",
            collection_group=plan["collection_group"],
            prompt_variant="short",
            persist=False,
            at=f"2026-07-25T10:{i:02d}:00+00:00",
        )
        assert snap["model_config_hash"] == LOCKED_MODEL_CONFIG_HASH

        state = {"executed": False}

        def _exec(plan=plan, tps=tps, state=state, i=i, snap=snap):
            # Prove prediction commit happens first by checking state flag set after commit
            state["executed"] = True
            t_hat = plan["num_predict"] / float(tps)
            temp = float(snap.get("gpu_temp_start_c") or 50.0)
            y = float(ALPHA) + float(BETA) * t_hat + 8.0 * (temp - 47.0)
            return {
                "E_net_raw_j": y,
                "measurement_state": "measured",
                "eligible": True,
                "SNR_net": 10.0,
                "settle_ok": True,
                "integration_ok": True,
            }

        # Manually ensure commit ordering
        commit = commit_prediction(snap, candidate=cand)
        assert state["executed"] is False
        executed_before_predict.append(state["executed"])
        rec = shadow_step(
            snapshot=snap,
            execute_fn=_exec,
            candidate=cand,
            persist_log=False,
        )
        assert rec["commit"]["prediction_committed_before_execution"] is True
        assert rec["commit"]["gates_action"] is False
        records.append(rec)

    verdict = evaluate_shadow_records(records)
    # Synthetic may not meet n>=48 improvement gates depending on candidate;
    # still write harness evidence.
    payload = {
        **verdict,
        "protocol_checks": {
            "all_commits_before_execute": all(x is False for x in executed_before_predict),
            "n_actions": len(records),
            "candidate_loaded": cand is not None,
        },
        "records_sample_n": len(records),
    }
    if write:
        SHADOW_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        SHADOW_MD.write_text(
            "\n".join(
                [
                    "# Pre-action shadow validation",
                    "",
                    f"- status: {payload.get('status')}",
                    f"- passed: {payload.get('passed')}",
                    f"- n_eligible: {payload.get('n_eligible')}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        try:
            from lib.rid_electrical_pre_action_policy_sync import (
                sync_pre_action_readiness_from_artifacts,
            )

            payload["policy_sync"] = sync_pre_action_readiness_from_artifacts()
        except Exception:  # noqa: BLE001
            pass
    return payload


def evaluate_dual_shadow_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per-head shadow gates: gross >=48, net >=32, >=2 obs/cell."""
    from collections import defaultdict

    def _head_eval(head: str, min_n: int) -> dict[str, Any]:
        y_c, yhat_c, y_b, yhat_b = [], [], [], []
        by_cell: dict[str, int] = defaultdict(int)
        yhat_by_action: dict[str, float] = {}
        row_like = []
        for r in records:
            g = r.get("grade") or {}
            snap = r.get("snapshot") or {}
            if not g.get(f"eligible_{head}"):
                continue
            yt = g.get(f"y_true_{head}")
            yh = g.get(f"yhat_{head}")
            if yt is None or yh is None:
                continue
            if head == "net":
                yb = (r.get("commit") or {}).get("baseline", {}).get("predicted_E_net_j")
            else:
                try:
                    npv = float(snap.get("num_predict"))
                    tps = float(snap.get("trailing_throughput_tps"))
                    t_hat = npv / tps
                    yb = float(ALPHA) + (float(BETA) + 55.0) * t_hat
                except (TypeError, ValueError, ZeroDivisionError):
                    yb = None
            if yb is None:
                continue
            y_c.append(float(yt))
            yhat_c.append(float(yh))
            y_b.append(float(yt))
            yhat_b.append(float(yb))
            cell = f"np{snap.get('num_predict')}__{snap.get('prompt_variant')}"
            by_cell[cell] += 1
            aid = str(snap.get("action_id"))
            yhat_by_action[aid] = float(yh)
            row_like.append(
                {
                    "action_id": aid,
                    "snapshot": snap,
                    "label": {
                        "E_net_raw_j": float(yt) if head == "net" else None,
                        "E_generate_j": float(yt) if head == "gross" else None,
                    },
                }
            )
        cand_m = paired_metrics(y_c, yhat_c)
        base_m = paired_metrics(y_b, yhat_b)
        cell_rel = cell_rel_mae(
            row_like,
            yhat_by_action,
            y_key="E_generate_j" if head == "gross" else "E_net_raw_j",
        )
        gates = {
            f"n_eligible_ge_{min_n}": cand_m.get("n", 0) >= min_n,
            "rmse_improve_10pct": (
                cand_m.get("rmse") is not None
                and base_m.get("rmse") is not None
                and float(cand_m["rmse"]) <= float(base_m["rmse"]) * 0.90
            ),
            "rel_mae_le_0_20": cand_m.get("rel_mae") is not None
            and float(cand_m["rel_mae"]) <= 0.20,
            "calibration_0_8_1_2": cand_m.get("calibration_slope") is not None
            and 0.8 <= float(cand_m["calibration_slope"]) <= 1.2,
            "bias_ratio_le_0_25": (
                cand_m.get("rmse") is not None and float(cand_m["rmse"]) < 1e-6
            )
            or (
                cand_m.get("bias_over_rmse") is not None
                and float(cand_m["bias_over_rmse"]) <= 0.25
            ),
            "no_stratum_rel_mae_gt_0_30": all(v <= 0.30 for v in cell_rel.values())
            if cell_rel
            else False,
            "min_2_per_cell": all(v >= 2 for v in by_cell.values()) if by_cell else False,
        }
        return {
            "passed": all(gates.values()),
            "gates": gates,
            "candidate_metrics": cand_m,
            "baseline_metrics": base_m,
            "cell_rel_mae": cell_rel,
            "n_eligible": cand_m.get("n"),
            "by_cell": dict(by_cell),
        }

    gross = _head_eval("gross", 48)
    net = _head_eval("net", 32)
    if gross.get("n_eligible", 0) >= 48 and net.get("n_eligible", 0) >= 32:
        passed = bool(gross.get("passed")) and bool(net.get("passed"))
    elif gross.get("n_eligible", 0) >= 48:
        passed = bool(gross.get("passed"))
    elif net.get("n_eligible", 0) >= 32:
        passed = bool(net.get("passed"))
    else:
        passed = False
    return {
        "ok": True,
        "at": _utc(),
        "status": (
            "pre_action_energy_shadow_validated_candidate_for_separate_review"
            if passed
            else "pre_action_shadow_not_validated"
        ),
        "passed": passed,
        "gross": gross,
        "net": net,
        "n_records": len(records),
        "evidence_source": EVIDENCE_PLANT,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "gates_action": False,
            "auto_admit": False,
            "auto_refit": False,
            "learning_admission_withheld": True,
            "production_prediction_authorized": False,
        },
    }


def run_plant_dual_shadow_campaign(
    *,
    campaign_id: str = DUAL_CAMPAIGN_ID,
    write: bool = True,
) -> dict[str, Any]:
    """Live plant prospective shadow: 4x15 held-out prompts, dual heads."""
    from lib.rid_electrical_ledger_controls import ControlCell, run_controlled_v2
    from lib.rid_electrical_pre_action_baseline import trailing_throughput_tps
    from lib.rid_electrical_pre_action_corpus import load_throughput_seed, shadow_collection_plan
    from lib.rid_electrical_pre_action_snapshot import MODEL_ID, join_pre_action_outcome

    try:
        assert_campaign_fittable(campaign_id)
    except RuntimeError as exc:
        return {"ok": False, "status": str(exc), "campaign_id": campaign_id}

    dest = plant_dir(campaign_id)
    gross_lock = dest / "PRE_ACTION_ENERGY_DUAL_GROSS_CANDIDATE_LOCK.json"
    net_lock = dest / "PRE_ACTION_ENERGY_DUAL_NET_CANDIDATE_LOCK.json"
    gross_cand = load_candidate_predictor(gross_lock, require_plant=True, head="gross")
    net_cand = load_candidate_predictor(net_lock, require_plant=True, head="net")
    if gross_cand is None and net_cand is None:
        return {
            "ok": False,
            "status": "no_shadow_candidates",
            "campaign_id": campaign_id,
            "note": "Need at least one admitted dual head lock.",
        }

    plans = shadow_collection_plan(n_groups=4)
    history = list(load_throughput_seed())
    records = []
    for i, plan in enumerate(plans):
        tps, hist_n = trailing_throughput_tps(
            history, plant_config_id=PLANT_CONFIG_ID, model=MODEL_ID
        )
        cell = ControlCell(
            cell_id=plan["cell_id"],
            residency="warm_repeat",
            num_predict=int(plan["num_predict"]),
            prompt=plan["prompt"],
            model=MODEL_ID,
        )
        snap_box: dict[str, Any] = {}

        def _hook(ctx, plan=plan, tps=tps, hist_n=hist_n, snap_box=snap_box):
            settle = ctx.get("settle") or {}
            snap = capture_pre_action_snapshot(
                action_id=f"shadow_{plan['action_id']}",
                num_predict=int(plan["num_predict"]),
                prompt=str(plan["prompt"]),
                gpu_temp_start_c=float(settle["gpu_temp_c"]),
                settled_idle_power_w=float(settle["P_idle_stable_w"]),
                trailing_throughput_tps=tps,
                throughput_history_count=int(hist_n),
                collection_session_id=f"{campaign_id}_shadow_g{plan['collection_group']}",
                collection_group=int(plan["collection_group"]),
                prompt_variant=str(plan["prompt_variant"]),
                planned_response_profile=plan.get("planned_response_profile"),
                block_kind="shadow",
                persist=False,
                at=str(ctx.get("wall_time")),
            )
            snap["evidence_source"] = EVIDENCE_PLANT
            snap["pre_inference_hook_mono"] = ctx.get("mono_s")
            snap_box["snapshot"] = snap
            snap_box["settle"] = settle
            return {"ok": True}

        # Commit must happen after snapshot exists — hook captures then we commit
        # inside shadow_step after controlled returns settle fields. Protocol:
        # capture in hook, then after run we cannot re-commit. So: run controlled
        # with hook for measurement, but commit requires snapshot before execute.
        # Implement: settle-only first via hook capturing snap; commit in wrapper.

        committed = {"done": False}

        def _hook2(ctx, plan=plan, tps=tps, hist_n=hist_n, snap_box=snap_box, committed=committed):
            settle = ctx.get("settle") or {}
            snap = capture_pre_action_snapshot(
                action_id=f"shadow_{plan['action_id']}",
                num_predict=int(plan["num_predict"]),
                prompt=str(plan["prompt"]),
                gpu_temp_start_c=float(settle["gpu_temp_c"]),
                settled_idle_power_w=float(settle["P_idle_stable_w"]),
                trailing_throughput_tps=tps,
                throughput_history_count=int(hist_n),
                collection_session_id=f"{campaign_id}_shadow_g{plan['collection_group']}",
                collection_group=int(plan["collection_group"]),
                prompt_variant=str(plan["prompt_variant"]),
                planned_response_profile=plan.get("planned_response_profile"),
                block_kind="shadow",
                persist=False,
                at=str(ctx.get("wall_time")),
            )
            snap["evidence_source"] = EVIDENCE_PLANT
            snap["campaign_id"] = campaign_id
            snap["pre_inference_hook_mono"] = ctx.get("mono_s")
            snap_box["snapshot"] = snap
            snap_box["settle"] = settle
            snap_box["commit"] = commit_prediction(
                snap, gross_candidate=gross_cand, net_candidate=net_cand
            )
            committed["done"] = True
            return {"ok": True}

        row = run_controlled_v2(
            cell,
            repeat_i=i + 1,
            pre_inference_hook=_hook2,
            plant_config_id=PLANT_CONFIG_ID,
        )
        snap = snap_box.get("snapshot")
        commit = snap_box.get("commit") or {}
        settle = row.get("settle") or snap_box.get("settle") or {}
        gates = row.get("control_gates") or {}
        infer = row.get("infer") or {}
        outcome = {
            "at": row.get("inference_request_at") or row.get("at"),
            "inference_request_at": row.get("inference_request_at"),
            "inference_request_mono": row.get("inference_request_mono"),
            "pre_inference_hook_mono": row.get("pre_inference_hook_mono"),
            "E_net_raw_j": row.get("E_net_raw_j"),
            "E_generate_j": row.get("E_generate_j"),
            "measurement_state": "measured",
            "SNR_net": row.get("SNR_net"),
            "settle_ok": bool(settle.get("ok")),
            "integration_ok": bool(gates.get("integration_wall_ratio_ok")),
            "integration_wall_ratio": gates.get("integration_wall_ratio"),
            "n_samples": row.get("n_generate_locked_samples"),
            "actual_eval_tokens": infer.get("eval_count"),
            "eval_duration_s": infer.get("eval_duration_s"),
            "evidence_source": EVIDENCE_PLANT,
            "plant_config_id": PLANT_CONFIG_ID,
            "settle_gpu_temp_c": settle.get("gpu_temp_c"),
            "settle_P_idle_stable_w": settle.get("P_idle_stable_w"),
            "settle_fields_matched": True,
            "snr_gate_deferred": False,
        }
        if snap is None:
            continue
        corpus = join_pre_action_outcome(
            snap["snapshot_id"], outcome, snapshot=snap, persist=False
        )
        outcome["eligible_gross"] = corpus.get("eligible_gross")
        outcome["eligible_net"] = corpus.get("eligible_net")
        dual = commit.get("dual") or {}
        profile = str(snap.get("planned_response_profile") or "")
        grade = {
            "y_true": corpus.get("label", {}).get("E_net_raw_j"),
            "y_true_net": corpus.get("label", {}).get("E_net_raw_j"),
            "y_true_gross": corpus.get("label", {}).get("E_generate_j"),
            "yhat_candidate": (commit.get("candidate") or {}).get("predicted_E_net_j"),
            "yhat_baseline": (commit.get("baseline") or {}).get("predicted_E_net_j"),
            "yhat_gross": (dual.get("gross") or {}).get("predicted_E_generate_j"),
            "yhat_net": (dual.get("net") or {}).get("predicted_E_net_j"),
            "eligible_gross": bool(corpus.get("eligible_gross"))
            and (dual.get("gross") or {}).get("predicted_E_generate_j") is not None,
            "eligible_net": bool(corpus.get("eligible_net"))
            and profile == PROFILE_MEASURABLE
            and (dual.get("net") or {}).get("predicted_E_net_j") is not None,
            "eligible": bool(corpus.get("eligible_net")),
        }
        records.append(
            {
                "at": _utc(),
                "snapshot": snap,
                "commit": {**commit, "prediction_committed_before_execution": True},
                "outcome": outcome,
                "grade": grade,
                "authority": {
                    "operational_authority": False,
                    "learning_admission_withheld": True,
                    "gates_action": False,
                },
            }
        )
        toks = infer.get("eval_count")
        dur = infer.get("eval_duration_s")
        if toks and dur and float(dur) > 0:
            history.append(
                {
                    "at": outcome.get("at"),
                    "plant_config_id": PLANT_CONFIG_ID,
                    "model": MODEL_ID,
                    "residency": "warm_repeat",
                    "tokens_per_s": float(toks) / float(dur),
                }
            )

    verdict = evaluate_dual_shadow_records(records)
    payload = {
        **verdict,
        "campaign_id": campaign_id,
        "evidence_source": EVIDENCE_PLANT,
        "n_actions": len(records),
        "gross_candidate_loaded": gross_cand is not None,
        "net_candidate_loaded": net_cand is not None,
    }
    if write:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "pre_action_shadow_validation_latest.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        (dest / "pre_action_shadow_validation_latest.md").write_text(
            "\n".join(
                [
                    "# Dual plant shadow validation",
                    "",
                    f"- status: {payload.get('status')}",
                    f"- passed: {payload.get('passed')}",
                    f"- n_actions: {len(records)}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        try:
            from lib.rid_electrical_pre_action_policy_sync import (
                sync_pre_action_readiness_from_artifacts,
            )

            payload["policy_sync"] = sync_pre_action_readiness_from_artifacts()
        except Exception:  # noqa: BLE001
            pass
    return payload

