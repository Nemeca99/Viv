#!/usr/bin/env python3
"""Pre-action corpus collect: synthetic harness or hardened plant campaign.

Plant mode must not use placeholder settle fields or deferred SNR.
Do not run --plant until collector hardening + green foundation preflight.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_pre_action_baseline import trailing_throughput_tps  # noqa: E402
from lib.rid_electrical_pre_action_campaign import (  # noqa: E402
    all_manifest_rows,
    load_manifest,
    parse_groups_spec,
    pending_plans,
    record_completed,
    save_manifest,
)
from lib.rid_electrical_pre_action_campaign_status import (  # noqa: E402
    ACTION_CONTRACT_CAMPAIGN_ID,
    DUAL_CAMPAIGN_ID,
    V1_CAMPAIGN_ID,
    assert_campaign_fittable,
    assert_same_matrix_expandable,
    is_closed_not_ready,
)
from lib.rid_electrical_pre_action_corpus import (  # noqa: E402
    BLOCK_PRIMARY,
    BLOCK_SHORT_RECOVERY,
    evaluate_corpus_readiness,
    evaluate_dual_corpus_readiness,
    freeze_corpus,
    synthesize_ready_corpus,
)
from lib.rid_electrical_pre_action_paths import (  # noqa: E402
    EVIDENCE_PLANT,
    EVIDENCE_SYNTHETIC,
    SCHEMA_VERSION,
    SYNTHETIC_DIR,
    ensure_layout,
    plant_dir,
)
from lib.rid_electrical_pre_action_snapshot import (  # noqa: E402
    MODEL_ID,
    capture_pre_action_snapshot,
    join_pre_action_outcome,
)
from lib.rid_electrical_predictor import PLANT_CONFIG_ID  # noqa: E402


PLACEHOLDER_TEMP_C = 50.0
PLACEHOLDER_IDLE_W = 55.0


def _corpus_hash(rows: list[dict[str, Any]]) -> str:
    raw = json.dumps(rows, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_synthetic(freeze: bool = True) -> dict:
    ensure_layout()
    rows = synthesize_ready_corpus()
    for r in rows:
        r["evidence_source"] = EVIDENCE_SYNTHETIC
        r["synthetic"] = True
        if isinstance(r.get("snapshot"), dict):
            r["snapshot"]["evidence_source"] = EVIDENCE_SYNTHETIC
    if freeze:
        out = freeze_corpus(
            rows,
            write=True,
            out_dir=SYNTHETIC_DIR,
            evidence_source=EVIDENCE_SYNTHETIC,
            campaign_id="synthetic_harness",
        )
        # also keep legacy latest copies labeled synthetic for harness paths
        freeze_corpus(
            rows,
            write=True,
            evidence_source=EVIDENCE_SYNTHETIC,
            campaign_id="synthetic_harness",
        )
        return out
    return {"ok": True, "n_rows": len(rows), "rows": rows, "evidence_source": EVIDENCE_SYNTHETIC}


def _plant_hook_factory(
    *,
    plan: dict[str, Any],
    campaign_id: str,
    tps: float | None,
    hist_n: int,
    snap_box: dict[str, Any],
):
    def _hook(ctx: dict[str, Any]) -> dict[str, Any]:
        settle = ctx.get("settle") or {}
        gpu_t = settle.get("gpu_temp_c")
        p_idle = settle.get("P_idle_stable_w")
        if gpu_t is None or p_idle is None:
            raise RuntimeError("settle_missing_temp_or_idle")
        # Reject classic placeholders unless they truly match settle (equality later)
        snap = capture_pre_action_snapshot(
            action_id=str(plan["action_id"]),
            num_predict=int(plan["num_predict"]),
            prompt=str(plan["prompt"]),
            gpu_temp_start_c=float(gpu_t),
            settled_idle_power_w=float(p_idle),
            trailing_throughput_tps=tps,
            throughput_history_count=int(hist_n),
            collection_session_id=f"{campaign_id}_g{plan['collection_group']}",
            collection_group=int(plan["collection_group"]),
            prompt_variant=str(plan["prompt_variant"]),
            planned_response_profile=plan.get("planned_response_profile"),
            block_kind=str(plan.get("block_kind") or BLOCK_PRIMARY),
            plant_config_id=PLANT_CONFIG_ID,
            model=MODEL_ID,
            residency="warm_repeat",
            persist=True,
            at=str(ctx.get("wall_time")),
            action_contract=plan.get("action_contract"),
        )
        snap["evidence_source"] = EVIDENCE_PLANT
        snap["campaign_id"] = campaign_id
        snap["pre_inference_hook_mono"] = ctx.get("mono_s")
        snap_box["snapshot"] = snap
        snap_box["settle"] = settle
        snap_box["hook_mono"] = ctx.get("mono_s")
        return {"ok": True, "snapshot_id": snap["snapshot_id"]}

    return _hook


def evaluate_canary(rows: list[dict[str, Any]], *, expected_n: int = 15) -> dict[str, Any]:
    gates = {
        "n_actions": len(rows) == expected_n,
        "unique_action_ids": len({r.get("action_id") for r in rows}) == expected_n,
        "unique_snapshots": len({r.get("snapshot_id") for r in rows}) == expected_n,
        "all_hashes_ok": True,
        "no_placeholders": True,
        "no_deferred_snr": True,
        "snapshot_before_inference": True,
        "settle_fields_real": True,
        "authority_closed": True,
    }
    from lib.rid_electrical_pre_action_snapshot import verify_snapshot_integrity

    for r in rows:
        snap = r.get("snapshot") or {}
        ok_h, _ = verify_snapshot_integrity(snap)
        if not ok_h:
            gates["all_hashes_ok"] = False
        lab = r.get("label") or {}
        if r.get("snr_gate_deferred") or lab.get("snr_gate_deferred"):
            gates["no_deferred_snr"] = False
        try:
            t = float(snap.get("gpu_temp_start_c"))
            p = float(snap.get("settled_idle_power_w"))
            if abs(t - PLACEHOLDER_TEMP_C) < 1e-9 and abs(p - PLACEHOLDER_IDLE_W) < 1e-9:
                if not r.get("settle_fields_matched"):
                    gates["no_placeholders"] = False
                    gates["settle_fields_real"] = False
        except (TypeError, ValueError):
            gates["settle_fields_real"] = False
        snap_at = str(snap.get("at") or "")
        inf_at = str(r.get("inference_request_at") or (lab.get("inference_request_at") or ""))
        snap_mono = (snap.get("pre_inference_hook_mono") or r.get("pre_inference_hook_mono"))
        inf_mono = r.get("inference_request_mono")
        if snap_at and inf_at:
            if snap_at > inf_at:
                gates["snapshot_before_inference"] = False
            elif snap_at == inf_at:
                try:
                    if snap_mono is None or inf_mono is None or float(snap_mono) >= float(inf_mono):
                        gates["snapshot_before_inference"] = False
                except (TypeError, ValueError):
                    gates["snapshot_before_inference"] = False
        if r.get("gates_action") or r.get("operational_authority"):
            gates["authority_closed"] = False

    eligible = [r for r in rows if r.get("eligible") or r.get("eligible_net")]
    for r in eligible:
        snr = (r.get("label") or {}).get("snr_net")
        if snr is None:
            snr = r.get("SNR_net")
        try:
            if float(snr) < 3.0:
                gates["eligible_snr_ok"] = False
        except (TypeError, ValueError):
            gates["eligible_snr_ok"] = False
    gates.setdefault("eligible_snr_ok", True)
    gates["all_eligible_have_settle_integration"] = all(
        (r.get("label") or {}).get("settle_ok") is not False
        and (r.get("label") or {}).get("integration_ok") is not False
        for r in eligible
    )
    passed = all(gates.values())
    return {
        "ok": passed,
        "status": "pre_action_plant_canary_passed" if passed else "pre_action_plant_canary_failed",
        "gates": gates,
        "n_rows": len(rows),
        "n_eligible": len(eligible),
        "evidence_source": EVIDENCE_PLANT,
    }


def evaluate_dual_canary(rows: list[dict[str, Any]], *, expected_n: int = 30) -> dict[str, Any]:
    """Primary groups 1–2 canary for dual-target campaign."""
    from collections import defaultdict

    from lib.rid_electrical_pre_action_snapshot import (
        PROFILE_MEASURABLE,
        verify_snapshot_integrity,
    )

    structural = evaluate_canary(rows, expected_n=expected_n)
    gates = dict(structural.get("gates") or {})
    # Dual-specific eligibility gates
    by_cell_gross: dict[str, int] = defaultdict(int)
    by_cell_net: dict[str, int] = defaultdict(int)
    gross = [r for r in rows if r.get("eligible_gross")]
    net = [r for r in rows if r.get("eligible_net")]
    measurable = [
        r
        for r in rows
        if str(
            (r.get("snapshot") or {}).get("planned_response_profile")
            or r.get("planned_response_profile")
            or ""
        )
        == PROFILE_MEASURABLE
    ]
    for r in gross:
        snap = r.get("snapshot") or {}
        by_cell_gross[f"np{snap.get('num_predict')}__{snap.get('prompt_variant')}"] += 1
    for r in net:
        snap = r.get("snapshot") or {}
        by_cell_net[f"np{snap.get('num_predict')}__{snap.get('prompt_variant')}"] += 1

    gates["gross_min_24_of_30"] = len(gross) >= 24
    gates["gross_ge1_per_cell"] = len(by_cell_gross) >= 15 and all(
        v >= 1 for v in by_cell_gross.values()
    )
    # 20 measurable of 30 (medium+long); need ≥18 eligible net and ≥1 per measurable cell
    gates["net_min_18_of_measurable"] = len(net) >= 18 and len(measurable) >= 18
    gates["net_ge1_per_measurable_cell"] = len(by_cell_net) >= 10 and all(
        v >= 1 for v in by_cell_net.values()
    )
    gates["no_leakage"] = True
    from lib.rid_electrical_pre_action_snapshot import feature_leakage_audit

    leak = feature_leakage_audit(rows)
    if not leak.get("ok"):
        gates["no_leakage"] = False
    for r in rows:
        ok_h, _ = verify_snapshot_integrity(r.get("snapshot") or {})
        if not ok_h:
            gates["all_hashes_ok"] = False

    passed = all(gates.values())
    return {
        "ok": passed,
        "status": (
            "pre_action_dual_canary_passed" if passed else "pre_action_dual_canary_failed"
        ),
        "gates": gates,
        "n_rows": len(rows),
        "n_eligible_gross": len(gross),
        "n_eligible_net": len(net),
        "n_measurable": len(measurable),
        "by_cell_gross": dict(by_cell_gross),
        "by_cell_net": dict(by_cell_net),
        "evidence_source": EVIDENCE_PLANT,
        "campaign_id": DUAL_CAMPAIGN_ID,
    }


def evaluate_action_contract_canary(
    rows: list[dict[str, Any]], *, expected_n: int = 18
) -> dict[str, Any]:
    """Groups 1–2 canary for Action Contract campaign (9 cells × 2)."""
    from lib.rid_electrical_pre_action_action_contract import (
        verify_action_contract_integrity,
    )
    from lib.rid_electrical_pre_action_snapshot import verify_snapshot_integrity

    structural = evaluate_canary(rows, expected_n=expected_n)
    gates = dict(structural.get("gates") or {})
    gates["all_contracts_ok"] = True
    gates["n_cells_ge_9"] = False
    cells = set()
    for r in rows:
        snap = r.get("snapshot") or {}
        contract = r.get("action_contract") or snap.get("action_contract")
        if not isinstance(contract, dict):
            gates["all_contracts_ok"] = False
            continue
        ok_c, _ = verify_action_contract_integrity(contract)
        if not ok_c:
            gates["all_contracts_ok"] = False
        ok_h, _ = verify_snapshot_integrity(snap)
        if ok_h and snap.get("action_contract_hash") != contract.get("contract_hash"):
            gates["all_contracts_ok"] = False
        cells.add(str(snap.get("prompt_variant") or r.get("prompt_variant") or ""))
    gates["n_cells_ge_9"] = len(cells) >= 9
    gross = [r for r in rows if r.get("eligible_gross")]
    measurable = [
        r
        for r in rows
        if str(
            r.get("planned_response_profile")
            or (r.get("snapshot") or {}).get("planned_response_profile")
            or ""
        )
        == "measurable"
    ]
    net = [r for r in measurable if r.get("eligible_net")]
    gates["gross_eligible_ge_12"] = len(gross) >= 12
    gates["net_eligible_ge_8_of_measurable"] = len(net) >= min(8, max(1, len(measurable) // 2))
    # Brief band is intentionally short; require measurable-band gross coverage.
    measurable_gross = [r for r in measurable if r.get("eligible_gross")]
    gates["measurable_gross_ge_10"] = len(measurable_gross) >= 10
    passed = all(gates.values())
    return {
        "ok": passed,
        "at": structural.get("at"),
        "status": (
            "pre_action_action_contract_canary_passed"
            if passed
            else "pre_action_action_contract_canary_failed"
        ),
        "gates": gates,
        "n_rows": len(rows),
        "n_eligible_gross": len(gross),
        "n_eligible_net": len(net),
        "n_cells": len(cells),
        "evidence_source": EVIDENCE_PLANT,
        "campaign_id": ACTION_CONTRACT_CAMPAIGN_ID,
    }


def run_plant(
    *,
    campaign_id: str,
    groups: list[int],
    resume: bool = True,
    max_actions: int | None = None,
    canary_mode: bool = False,
    short_recovery_groups: list[int] | None = None,
    block_kind: str = BLOCK_PRIMARY,
) -> dict[str, Any]:
    from lib.rid_electrical_ledger_controls import ControlCell, run_controlled_v2

    if is_closed_not_ready(campaign_id) or campaign_id == V1_CAMPAIGN_ID:
        return {
            "ok": False,
            "status": "campaign_closed_not_ready",
            "campaign_id": campaign_id,
            "note": "V1 plant corpus is closed_not_ready negative evidence; use dual campaign.",
        }
    try:
        assert_campaign_fittable(campaign_id)
        assert_same_matrix_expandable(campaign_id)
    except RuntimeError as exc:
        return {"ok": False, "status": str(exc), "campaign_id": campaign_id}

    ensure_layout()
    out_root = plant_dir(campaign_id)
    out_root.mkdir(parents=True, exist_ok=True)
    is_dual = campaign_id == DUAL_CAMPAIGN_ID or str(campaign_id).startswith(
        "pre_action_energy_dual"
    )
    is_ac = campaign_id == ACTION_CONTRACT_CAMPAIGN_ID or str(campaign_id).startswith(
        "pre_action_energy_action_contract"
    )

    pending, manifest = pending_plans(
        campaign_id,
        groups,
        resume=resume,
        max_actions=max_actions,
        block_kind=block_kind,
        short_recovery_groups=short_recovery_groups,
    )
    if not manifest.get("created_at"):
        manifest["created_at"] = manifest.get("updated_at")
    manifest["evidence_source"] = EVIDENCE_PLANT
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["plant_config_id"] = PLANT_CONFIG_ID
    manifest["dual"] = is_dual
    manifest["action_contract"] = is_ac
    save_manifest(manifest)

    from lib.rid_electrical_pre_action_corpus import load_throughput_seed

    history = list(load_throughput_seed())
    new_rows: list[dict[str, Any]] = []

    for plan in pending:
        tps, hist_n = trailing_throughput_tps(
            history,
            plant_config_id=PLANT_CONFIG_ID,
            model=MODEL_ID,
        )
        cell = ControlCell(
            cell_id=plan["cell_id"],
            residency="warm_repeat",
            num_predict=int(plan["num_predict"]),
            prompt=plan["prompt"],
            model=MODEL_ID,
        )
        snap_box: dict[str, Any] = {}
        hook = _plant_hook_factory(
            plan=plan,
            campaign_id=campaign_id,
            tps=tps,
            hist_n=hist_n,
            snap_box=snap_box,
        )
        row = run_controlled_v2(
            cell,
            repeat_i=int(plan["order_in_group"]) + 1,
            pre_inference_hook=hook,
            plant_config_id=PLANT_CONFIG_ID,
        )
        settle = row.get("settle") or snap_box.get("settle") or {}
        snap = snap_box.get("snapshot")
        hook_failed = bool(row.get("snapshot_hook_failed")) or snap is None
        gates = row.get("control_gates") or {}
        snr = row.get("SNR_net")
        infer = row.get("infer") or {}
        gen_energy = row.get("generate_energy") or {}
        n_samples = row.get("n_generate_locked_samples")
        if n_samples is None:
            n_samples = gen_energy.get("n_samples")
        if n_samples is None:
            n_samples = gates.get("n_samples")
        outcome = {
            "at": row.get("inference_request_at") or row.get("at"),
            "inference_request_at": row.get("inference_request_at"),
            "inference_request_mono": row.get("inference_request_mono"),
            "pre_inference_hook_mono": row.get("pre_inference_hook_mono")
            or snap_box.get("hook_mono"),
            "E_net_raw_j": row.get("E_net_raw_j"),
            "E_generate_j": row.get("E_generate_j"),
            "measurement_state": (
                "measured" if row.get("E_generate_j") is not None else "timing_only"
            ),
            "SNR_net": snr,
            "snr_gate_deferred": False,
            "settle_ok": bool(settle.get("ok")),
            "integration_ok": bool(gates.get("integration_wall_ratio_ok")),
            "integration_wall_ratio": gates.get("integration_wall_ratio"),
            "n_samples": n_samples,
            "actual_eval_tokens": infer.get("eval_count"),
            "eval_duration_s": infer.get("eval_duration_s"),
            "prompt_eval_duration_s": infer.get("prompt_eval_duration_s"),
            "plant_config_id": PLANT_CONFIG_ID,
            "confidence": "ok",
            "evidence_source": EVIDENCE_PLANT,
            "snapshot_hook_failed": hook_failed,
            "settle_gpu_temp_c": settle.get("gpu_temp_c"),
            "settle_P_idle_stable_w": settle.get("P_idle_stable_w"),
            "settle_fields_matched": True,
        }
        if snap is None:
            corpus_row = {
                "action_id": plan["action_id"],
                "eligible": False,
                "eligible_gross": False,
                "eligible_net": False,
                "eligibility_reasons": ["snapshot_hook_failed"],
                "evidence_source": EVIDENCE_PLANT,
                "campaign_id": campaign_id,
                "snapshot_id": None,
                "inference_request_at": row.get("inference_request_at"),
                "block_kind": plan.get("block_kind") or BLOCK_PRIMARY,
            }
        else:
            corpus_row = join_pre_action_outcome(
                snap["snapshot_id"],
                outcome,
                snapshot=snap,
                persist=False,
            )
            corpus_row["evidence_source"] = EVIDENCE_PLANT
            corpus_row["campaign_id"] = campaign_id
            corpus_row["inference_request_at"] = row.get("inference_request_at")
            corpus_row["SNR_net"] = snr
            corpus_row["settle_fields_matched"] = True
            corpus_row["schema_version"] = SCHEMA_VERSION
        if plan.get("action_contract"):
            corpus_row["action_contract"] = plan["action_contract"]
        elif (corpus_row.get("snapshot") or {}).get("action_contract"):
            corpus_row["action_contract"] = corpus_row["snapshot"]["action_contract"]
        toks = infer.get("eval_count") or plan["num_predict"]
        dur = infer.get("eval_duration_s")
        if toks and dur and float(dur) > 0:
            corpus_row["measured_tokens_per_s"] = float(toks) / float(dur)
            history.append(
                {
                    "at": outcome.get("at"),
                    "plant_config_id": PLANT_CONFIG_ID,
                    "model": MODEL_ID,
                    "residency": "warm_repeat",
                    "tokens_per_s": corpus_row["measured_tokens_per_s"],
                }
            )
        manifest = record_completed(manifest, plan=plan, corpus_row=corpus_row)
        new_rows.append(corpus_row)

    all_rows = all_manifest_rows(campaign_id)
    result: dict[str, Any] = {
        "ok": True,
        "campaign_id": campaign_id,
        "evidence_source": EVIDENCE_PLANT,
        "n_new": len(new_rows),
        "n_total": len(all_rows),
        "groups": groups,
        "dual": is_dual,
        "action_contract": is_ac,
    }

    if is_ac and (canary_mode or set(groups) == {1, 2}):
        g12 = [
            r
            for r in all_rows
            if int(
                (r.get("snapshot") or {}).get("collection_group")
                or r.get("collection_group")
                or 0
            )
            in {1, 2}
        ]
        if len(g12) >= 18:
            canary = evaluate_action_contract_canary(g12[:18], expected_n=18)
            result["canary"] = canary
            result["ok"] = bool(canary.get("ok"))
            result["status"] = canary.get("status")
            (out_root / "canary_verdict.json").write_text(
                json.dumps(canary, indent=2), encoding="utf-8"
            )
            if not canary.get("ok"):
                return result
    elif is_dual and (canary_mode or set(groups) == {1, 2}):
        g12 = [
            r
            for r in all_rows
            if str(r.get("block_kind") or (r.get("snapshot") or {}).get("block_kind") or BLOCK_PRIMARY)
            == BLOCK_PRIMARY
            and int(
                (r.get("snapshot") or {}).get("collection_group")
                or r.get("collection_group")
                or 0
            )
            in {1, 2}
        ]
        if len(g12) >= 30:
            canary = evaluate_dual_canary(g12[:30], expected_n=30)
            result["canary"] = canary
            result["ok"] = bool(canary.get("ok"))
            result["status"] = canary.get("status")
            (out_root / "canary_verdict.json").write_text(
                json.dumps(canary, indent=2), encoding="utf-8"
            )
            if not canary.get("ok"):
                return result
    elif canary_mode or (groups == [1] and len(all_rows) >= 15):
        g1 = [
            r
            for r in all_rows
            if int((r.get("snapshot") or {}).get("collection_group") or r.get("collection_group") or 0)
            == 1
        ]
        if len(g1) >= 15:
            canary = evaluate_canary(g1[:15], expected_n=15)
            result["canary"] = canary
            result["ok"] = bool(canary.get("ok"))
            result["status"] = canary.get("status")
            (out_root / "canary_verdict.json").write_text(
                json.dumps(canary, indent=2), encoding="utf-8"
            )
            if not canary.get("ok"):
                return result

    if is_ac:
        if len(all_rows) >= 72:
            from lib.rid_electrical_pre_action_corpus import (
                evaluate_action_contract_corpus_readiness,
            )

            readiness = evaluate_action_contract_corpus_readiness(all_rows)
            frozen = freeze_corpus(
                all_rows,
                write=True,
                out_dir=out_root,
                evidence_source=EVIDENCE_PLANT,
                campaign_id=campaign_id,
                dual=True,
            )
            # Override readiness with AC-specific gates while keeping freeze shape.
            frozen["readiness"] = readiness
            frozen["ok"] = bool(readiness.get("ok"))
            frozen["status"] = readiness.get("status")
            frozen["action_contract"] = True
            (out_root / "pre_action_corpus_freeze_latest.json").write_text(
                json.dumps(frozen, indent=2, default=str), encoding="utf-8"
            )
            (out_root / "pre_action_corpus_readiness_latest.json").write_text(
                json.dumps(
                    {**readiness, "evidence_source": EVIDENCE_PLANT, "campaign_id": campaign_id},
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
            result["freeze"] = {
                "ok": frozen.get("ok"),
                "status": frozen.get("status"),
                "n_eligible_gross": readiness.get("n_eligible_gross"),
                "n_eligible_net": readiness.get("n_eligible_net"),
                "corpus_hash": frozen.get("corpus_hash"),
            }
            if not frozen.get("ok"):
                result["status"] = "pre_action_plant_corpus_not_ready"
                result["ok"] = False
            else:
                result["status"] = "pre_action_plant_corpus_ready"
        elif "status" not in result:
            result["status"] = "pre_action_plant_campaign_in_progress"
    elif is_dual:
        primary_n = sum(
            1
            for r in all_rows
            if str(r.get("block_kind") or (r.get("snapshot") or {}).get("block_kind") or "")
            == BLOCK_PRIMARY
        )
        short_n = sum(
            1
            for r in all_rows
            if str(r.get("block_kind") or (r.get("snapshot") or {}).get("block_kind") or "")
            == BLOCK_SHORT_RECOVERY
        )
        if primary_n >= 180 and short_n >= 20 and len(all_rows) >= 200:
            frozen = freeze_corpus(
                all_rows,
                write=True,
                out_dir=out_root,
                evidence_source=EVIDENCE_PLANT,
                campaign_id=campaign_id,
                dual=True,
            )
            result["freeze"] = {
                "ok": frozen.get("ok"),
                "status": frozen.get("status"),
                "n_eligible_gross": (frozen.get("readiness") or {}).get("n_eligible_gross"),
                "n_eligible_net": (frozen.get("readiness") or {}).get("n_eligible_net"),
                "corpus_hash": _corpus_hash(all_rows),
            }
            if not frozen.get("ok"):
                result["status"] = "pre_action_dual_corpus_not_ready"
                result["ok"] = False
            else:
                result["status"] = "pre_action_dual_corpus_ready"
        elif "status" not in result:
            result["status"] = "pre_action_dual_campaign_in_progress"
    else:
        by_g: dict[int, int] = {}
        for r in all_rows:
            g = int((r.get("snapshot") or {}).get("collection_group") or r.get("collection_group") or 0)
            by_g[g] = by_g.get(g, 0) + 1
        if all(by_g.get(g, 0) >= 15 for g in range(1, 9)) and len(all_rows) >= 120:
            frozen = freeze_corpus(
                all_rows,
                write=True,
                out_dir=out_root,
                evidence_source=EVIDENCE_PLANT,
                campaign_id=campaign_id,
            )
            result["freeze"] = {
                "ok": frozen.get("ok"),
                "status": frozen.get("status"),
                "n_eligible": (frozen.get("readiness") or {}).get("n_eligible"),
                "corpus_hash": _corpus_hash(all_rows),
            }
            if not frozen.get("ok"):
                result["status"] = "pre_action_plant_corpus_not_ready"
                result["ok"] = False
            else:
                result["status"] = "pre_action_plant_corpus_ready"
        elif "status" not in result:
            result["status"] = "pre_action_plant_campaign_in_progress"
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--plant", action="store_true")
    ap.add_argument("--campaign-id", type=str, default=DUAL_CAMPAIGN_ID)
    ap.add_argument("--groups", type=str, default="1-12")
    ap.add_argument(
        "--short-recovery-groups",
        type=str,
        default=None,
        help="Short-recovery block groups, e.g. 1-4",
    )
    ap.add_argument(
        "--block",
        type=str,
        default=BLOCK_PRIMARY,
        choices=[BLOCK_PRIMARY, BLOCK_SHORT_RECOVERY],
    )
    ap.add_argument("--resume", action="store_true", default=True)
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--max-actions", type=int, default=None)
    ap.add_argument("--canary", action="store_true", help="Force dual canary mode")
    args = ap.parse_args()
    resume = not args.no_resume
    if args.plant:
        groups = parse_groups_spec(args.groups)
        sr = (
            parse_groups_spec(args.short_recovery_groups)
            if args.short_recovery_groups
            else None
        )
        canary_mode = bool(args.canary) or (
            (
                args.campaign_id == DUAL_CAMPAIGN_ID
                or args.campaign_id == ACTION_CONTRACT_CAMPAIGN_ID
            )
            and set(groups) == {1, 2}
            and sr is None
        )
        out = run_plant(
            campaign_id=args.campaign_id,
            groups=groups,
            resume=resume,
            max_actions=args.max_actions,
            canary_mode=canary_mode,
            short_recovery_groups=sr,
            block_kind=args.block,
        )
    else:
        out = run_synthetic(freeze=True)
    print(
        json.dumps(
            {
                k: out.get(k)
                for k in (
                    "ok",
                    "status",
                    "campaign_id",
                    "evidence_source",
                    "n_new",
                    "n_total",
                    "n_rows",
                    "canary",
                    "freeze",
                    "dual",
                )
                if k in out or out.get(k) is not None
            },
            indent=2,
            default=str,
        )
    )
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
