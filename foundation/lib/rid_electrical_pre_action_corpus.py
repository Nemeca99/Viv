#!/usr/bin/env python3
"""Pre-action energy corpus assembly, group splits, and readiness gate."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_cost_decomposition import PROMPT_TEXT, prompt_for_variant
from lib.rid_electrical_pre_action_baseline import TRAILING_WINDOW, trailing_throughput_tps
from lib.rid_electrical_pre_action_snapshot import (
    MODEL_ID,
    feature_leakage_audit,
    required_features_present,
    verify_snapshot_integrity,
)
from lib.rid_electrical_predictor import PLANT_CONFIG_ID

CAMPAIGN = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
CORPUS_DIR = CAMPAIGN / "pre_action_corpus"
FREEZE_JSON = CAMPAIGN / "pre_action_corpus_freeze_latest.json"
FREEZE_MD = CAMPAIGN / "pre_action_corpus_freeze_latest.md"
READINESS_JSON = CAMPAIGN / "pre_action_corpus_readiness_latest.json"
READINESS_MD = CAMPAIGN / "pre_action_corpus_readiness_latest.md"
THROUGHPUT_SEED_JSON = CAMPAIGN / "pre_action_throughput_seed_latest.json"

NUM_PREDICT_GRID = (258, 309, 360, 412, 464)
PROMPT_VARIANTS = ("short", "medium", "long")
N_COLLECTION_GROUPS = 8
TRAIN_GROUPS = (1, 2, 3, 4, 5)
SELECT_GROUPS = (6,)
HOLDOUT_GROUPS = (7, 8)
MIN_ELIGIBLE = 100
MIN_REPEATS_PER_CELL = 6

# Dual-target campaign (pre_action_energy_dual_v1_plant_v1)
DUAL_N_PRIMARY_GROUPS = 12
DUAL_N_SHORT_RECOVERY_GROUPS = 4
DUAL_PRIMARY_TRAIN = (1, 2, 3, 4, 5, 6, 7)
DUAL_PRIMARY_SELECT = (8, 9)
DUAL_PRIMARY_HOLDOUT = (10, 11, 12)
DUAL_SHORT_TRAIN = (1, 2)
DUAL_SHORT_SELECT = (3,)
DUAL_SHORT_HOLDOUT = (4,)
DUAL_MIN_GROSS_ELIGIBLE = 170
DUAL_MIN_NET_ELIGIBLE = 100
DUAL_MIN_GROSS_MEDIUM_LONG = 8
DUAL_MIN_GROSS_SHORT = 10
DUAL_MIN_NET_MEASURABLE_CELL = 8
DUAL_HOLDOUT_MIN_PER_CELL = 2
BLOCK_PRIMARY = "primary"
BLOCK_SHORT_RECOVERY = "short_recovery"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def cell_id(num_predict: int, prompt_variant: str) -> str:
    return f"np{int(num_predict)}__{prompt_variant}"


def collection_plan(*, n_groups: int = N_COLLECTION_GROUPS) -> list[dict[str, Any]]:
    """Deterministic rotated Cartesian product across groups."""
    from lib.rid_electrical_pre_action_snapshot import profile_from_prompt_variant

    base = [
        {
            "num_predict": npv,
            "prompt_variant": pv,
            "prompt": prompt_for_variant(pv),
            "cell_id": cell_id(npv, pv),
            "planned_response_profile": profile_from_prompt_variant(pv),
            "block_kind": BLOCK_PRIMARY,
        }
        for npv in NUM_PREDICT_GRID
        for pv in PROMPT_VARIANTS
    ]
    plans: list[dict[str, Any]] = []
    for g in range(1, n_groups + 1):
        rotated = base[g - 1 :] + base[: g - 1]
        for order_i, cell in enumerate(rotated):
            plans.append(
                {
                    **cell,
                    "collection_group": g,
                    "order_in_group": order_i,
                    "action_id": f"pre_action_g{g}_{cell['cell_id']}_o{order_i}",
                }
            )
    return plans


def dual_primary_collection_plan(
    *, n_groups: int = DUAL_N_PRIMARY_GROUPS
) -> list[dict[str, Any]]:
    return collection_plan(n_groups=n_groups)


def dual_short_recovery_plan(
    *, n_groups: int = DUAL_N_SHORT_RECOVERY_GROUPS
) -> list[dict[str, Any]]:
    """Four predeclared short-only rotated groups (5 cells each) = 20 actions."""
    from lib.rid_electrical_pre_action_snapshot import PROFILE_SHORT

    base = [
        {
            "num_predict": npv,
            "prompt_variant": "short",
            "prompt": prompt_for_variant("short"),
            "cell_id": cell_id(npv, "short"),
            "planned_response_profile": PROFILE_SHORT,
            "block_kind": BLOCK_SHORT_RECOVERY,
        }
        for npv in NUM_PREDICT_GRID
    ]
    plans: list[dict[str, Any]] = []
    for g in range(1, n_groups + 1):
        rotated = base[g - 1 :] + base[: g - 1]
        for order_i, cell in enumerate(rotated):
            plans.append(
                {
                    **cell,
                    "collection_group": g,
                    "order_in_group": order_i,
                    "action_id": (
                        f"pre_action_sr_g{g}_{cell['cell_id']}_o{order_i}"
                    ),
                }
            )
    return plans


def dual_full_collection_plan() -> list[dict[str, Any]]:
    return dual_primary_collection_plan() + dual_short_recovery_plan()


def dual_split_bucket(row: Mapping[str, Any]) -> str | None:
    """Return 'train'|'select'|'holdout' for a dual campaign row."""
    snap = row.get("snapshot") if isinstance(row.get("snapshot"), Mapping) else row
    block = str(
        (snap or {}).get("block_kind")
        or row.get("block_kind")
        or BLOCK_PRIMARY
    )
    try:
        g = int((snap or {}).get("collection_group") or row.get("collection_group") or 0)
    except (TypeError, ValueError):
        return None
    if block == BLOCK_SHORT_RECOVERY:
        if g in DUAL_SHORT_TRAIN:
            return "train"
        if g in DUAL_SHORT_SELECT:
            return "select"
        if g in DUAL_SHORT_HOLDOUT:
            return "holdout"
        return None
    if g in DUAL_PRIMARY_TRAIN:
        return "train"
    if g in DUAL_PRIMARY_SELECT:
        return "select"
    if g in DUAL_PRIMARY_HOLDOUT:
        return "holdout"
    return None


def split_dual_rows_by_group(
    rows: Sequence[Mapping[str, Any]],
    *,
    head: str = "gross",
) -> dict[str, list[dict[str, Any]]]:
    train, select, holdout = [], [], []
    for r in rows:
        if head == "gross":
            if not r.get("eligible_gross"):
                continue
        else:
            if not (r.get("eligible_net") or (r.get("eligible") and "eligible_net" not in r)):
                continue
        bucket = dual_split_bucket(r)
        if bucket == "train":
            train.append(dict(r))
        elif bucket == "select":
            select.append(dict(r))
        elif bucket == "holdout":
            holdout.append(dict(r))
    return {"train": train, "select": select, "holdout": holdout}

def shadow_collection_plan(
    *,
    n_groups: int = 4,
    prompt_variants: Sequence[str] = ("shadow_a", "shadow_b", "shadow_c"),
    prompt_texts: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Four blocks × five num_predict × three held-out prompt variants = 60."""
    from lib.rid_electrical_pre_action_snapshot import (
        PROFILE_MEASURABLE,
        PROFILE_SHORT,
    )

    texts = dict(prompt_texts or {})
    for i, pv in enumerate(prompt_variants):
        texts.setdefault(
            pv,
            f"Shadow held-out prompt variant {pv}: summarize local GPU energy accounting briefly ({i}).",
        )
    # Predeclared profile routing (not fitted): first variant short, others measurable.
    profile_map = {
        prompt_variants[0]: PROFILE_SHORT,
        **{pv: PROFILE_MEASURABLE for pv in prompt_variants[1:]},
    }
    base = [
        {
            "num_predict": npv,
            "prompt_variant": pv,
            "prompt": texts[pv],
            "cell_id": cell_id(npv, pv),
            "planned_response_profile": profile_map.get(pv, PROFILE_MEASURABLE),
            "block_kind": "shadow",
        }
        for npv in NUM_PREDICT_GRID
        for pv in prompt_variants
    ]
    plans: list[dict[str, Any]] = []
    for g in range(1, n_groups + 1):
        rotated = base[g - 1 :] + base[: g - 1]
        for order_i, cell in enumerate(rotated):
            plans.append(
                {
                    **cell,
                    "collection_group": g,
                    "order_in_group": order_i,
                    "action_id": f"pre_action_shadow_g{g}_{cell['cell_id']}_o{order_i}",
                    "shadow": True,
                }
            )
    return plans


def build_throughput_seed_from_controlled(
    controlled_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Freeze chronological throughput seed; never use as train/holdout labels."""
    seed_rows: list[dict[str, Any]] = []
    for r in controlled_rows:
        tps = r.get("tokens_per_s")
        if tps is None:
            toks = r.get("actual_eval_tokens") or r.get("eval_count")
            dur = r.get("eval_duration_s")
            try:
                if toks is not None and dur is not None and float(dur) > 0:
                    tps = float(toks) / float(dur)
            except (TypeError, ValueError):
                tps = None
        try:
            tv = float(tps) if tps is not None else None
        except (TypeError, ValueError):
            continue
        if tv is None or not math.isfinite(tv) or tv <= 0:
            continue
        seed_rows.append(
            {
                "at": r.get("at"),
                "plant_config_id": r.get("plant_config_id") or PLANT_CONFIG_ID,
                "model": r.get("model") or MODEL_ID,
                "residency": r.get("residency") or r.get("residency_state") or "warm_repeat",
                "tokens_per_s": tv,
                "actual_eval_tokens": r.get("actual_eval_tokens") or r.get("eval_count"),
                "eval_duration_s": r.get("eval_duration_s"),
                "seed_only": True,
                "eligible_for_training": False,
            }
        )
    # chronological
    seed_rows.sort(key=lambda x: str(x.get("at") or ""))
    payload = {
        "ok": True,
        "at": _utc(),
        "n_seed": len(seed_rows),
        "note": "Throughput history seed only; excluded from train/holdout.",
        "rows": seed_rows,
    }
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    THROUGHPUT_SEED_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_throughput_seed() -> list[dict[str, Any]]:
    if not THROUGHPUT_SEED_JSON.exists():
        return []
    data = json.loads(THROUGHPUT_SEED_JSON.read_text(encoding="utf-8"))
    return list(data.get("rows") or [])


def annotate_trailing_throughput(
    corpus_rows: list[dict[str, Any]],
    *,
    seed: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Fill trailing throughput from seed + past eligible measured throughputs."""
    seed_rows = list(seed if seed is not None else load_throughput_seed())
    history: list[dict[str, Any]] = list(seed_rows)
    out: list[dict[str, Any]] = []
    for row in sorted(corpus_rows, key=lambda r: str((r.get("snapshot") or {}).get("at") or "")):
        snap = dict(row.get("snapshot") or {})
        tps, hist_n = trailing_throughput_tps(
            history,
            plant_config_id=str(snap.get("plant_config_id") or PLANT_CONFIG_ID),
            model=str(snap.get("model") or MODEL_ID),
            residency=str(snap.get("residency") or "warm_repeat"),
        )
        snap["trailing_throughput_tps"] = tps
        snap["throughput_history_count"] = hist_n
        # recompute hash would break immutability — trailing must be captured at snapshot time.
        # For post-hoc annotation of synthetic rows only, update features copy.
        feats = dict(row.get("features") or {})
        if tps is not None:
            feats["trailing_throughput_tps"] = float(tps)
            feats["throughput_history_count"] = float(hist_n)
        new_row = {**row, "snapshot": snap, "features": feats or row.get("features")}
        out.append(new_row)
        # Append measured throughput to history for subsequent rows (past-only)
        lab = row.get("label") or {}
        outcome_tps = row.get("measured_tokens_per_s")
        if outcome_tps is None and row.get("eval_duration_s") and row.get("actual_eval_tokens"):
            try:
                outcome_tps = float(row["actual_eval_tokens"]) / float(row["eval_duration_s"])
            except (TypeError, ValueError, ZeroDivisionError):
                outcome_tps = None
        if outcome_tps is not None and row.get("eligible"):
            history.append(
                {
                    "at": lab.get("outcome_at") or snap.get("at"),
                    "plant_config_id": snap.get("plant_config_id") or PLANT_CONFIG_ID,
                    "model": snap.get("model") or MODEL_ID,
                    "residency": snap.get("residency") or "warm_repeat",
                    "tokens_per_s": float(outcome_tps),
                }
            )
    return out


def evaluate_corpus_readiness(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Corpus readiness gate for offline training (legacy single-target)."""
    eligible = [r for r in rows if r.get("eligible") or r.get("eligible_net")]
    by_cell: dict[str, int] = defaultdict(int)
    by_group: dict[int, int] = defaultdict(int)
    hash_ok = 0
    feat_ok = 0
    inversions = 0
    for r in eligible:
        snap = r.get("snapshot") or {}
        pv = snap.get("prompt_variant") or "unknown"
        npv = snap.get("num_predict")
        by_cell[cell_id(int(npv or 0), str(pv))] += 1
        g = snap.get("collection_group")
        if g is not None:
            by_group[int(g)] += 1
        ok_h, _ = verify_snapshot_integrity(snap)
        if ok_h:
            hash_ok += 1
        ok_f, _ = required_features_present(snap)
        if ok_f and r.get("features"):
            feat_ok += 1
        lab = r.get("label") or {}
        if str(lab.get("outcome_at") or "") and str(snap.get("at") or ""):
            if str(lab["outcome_at"]) < str(snap["at"]):
                inversions += 1

    cells_needed = [cell_id(npv, pv) for npv in NUM_PREDICT_GRID for pv in PROMPT_VARIANTS]
    cell_ok = all(by_cell.get(c, 0) >= MIN_REPEATS_PER_CELL for c in cells_needed)
    groups_present = sorted(by_group.keys())
    overlap = False  # groups are labels; overlap would be same action_id in multiple — check ids
    ids = [str(r.get("action_id") or r.get("snapshot_id")) for r in eligible]
    overlap = len(ids) != len(set(ids))

    leak = feature_leakage_audit(list(rows))
    n_elig = len(eligible)
    feat_cov = (feat_ok / n_elig) if n_elig else 0.0
    hash_cov = (hash_ok / n_elig) if n_elig else 0.0

    gates = {
        "min_eligible": n_elig >= MIN_ELIGIBLE,
        "min_repeats_per_cell": cell_ok,
        "feature_coverage_100": feat_cov >= 1.0 - 1e-12,
        "hash_coverage_100": hash_cov >= 1.0 - 1e-12,
        "no_timestamp_inversion": inversions == 0,
        "no_group_overlap": not overlap,
        "no_feature_leakage": bool(leak.get("ok")),
        "split_groups_present": set(TRAIN_GROUPS).issubset(by_group.keys())
        and set(SELECT_GROUPS).issubset(by_group.keys())
        and set(HOLDOUT_GROUPS).issubset(by_group.keys()),
    }
    ready = all(gates.values())
    split = {
        "train_groups": list(TRAIN_GROUPS),
        "select_groups": list(SELECT_GROUPS),
        "holdout_groups": list(HOLDOUT_GROUPS),
        "by_group_eligible": dict(by_group),
    }
    report = {
        "ok": ready,
        "at": _utc(),
        "status": "pre_action_corpus_ready" if ready else "pre_action_corpus_not_ready",
        "n_rows": len(rows),
        "n_eligible": n_elig,
        "by_cell": dict(by_cell),
        "gates": gates,
        "split": split,
        "leakage_audit": leak,
        "feature_coverage": feat_cov,
        "hash_coverage": hash_cov,
        "timestamp_inversions": inversions,
        "authority": {
            "operational_authority": False,
            "learning_admission_withheld": True,
            "auto_admit": False,
        },
    }
    return report


def evaluate_dual_corpus_readiness(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Dual gross/net readiness gates for pre_action_energy_dual_v1_plant_v1."""
    gross = [r for r in rows if r.get("eligible_gross")]
    net = [r for r in rows if r.get("eligible_net")]
    by_cell_gross: dict[str, int] = defaultdict(int)
    by_cell_net: dict[str, int] = defaultdict(int)
    holdout_gross: dict[str, int] = defaultdict(int)
    holdout_net: dict[str, int] = defaultdict(int)
    inversions = 0
    hash_ok = 0
    feat_ok = 0

    def _cell(r: Mapping[str, Any]) -> str:
        snap = r.get("snapshot") or {}
        return cell_id(int(snap.get("num_predict") or 0), str(snap.get("prompt_variant") or "unknown"))

    for r in rows:
        snap = r.get("snapshot") or {}
        ok_h, _ = verify_snapshot_integrity(snap)
        if ok_h:
            hash_ok += 1
        ok_f, _ = required_features_present(snap)
        if ok_f and r.get("features"):
            feat_ok += 1
        lab = r.get("label") or {}
        if str(lab.get("outcome_at") or "") and str(snap.get("at") or ""):
            if str(lab["outcome_at"]) < str(snap["at"]):
                inversions += 1

    for r in gross:
        c = _cell(r)
        by_cell_gross[c] += 1
        if dual_split_bucket(r) == "holdout":
            holdout_gross[c] += 1
    for r in net:
        c = _cell(r)
        by_cell_net[c] += 1
        if dual_split_bucket(r) == "holdout":
            holdout_net[c] += 1

    medium_long_ok = all(
        by_cell_gross.get(cell_id(npv, pv), 0) >= DUAL_MIN_GROSS_MEDIUM_LONG
        for npv in NUM_PREDICT_GRID
        for pv in ("medium", "long")
    )
    short_ok = all(
        by_cell_gross.get(cell_id(npv, "short"), 0) >= DUAL_MIN_GROSS_SHORT
        for npv in NUM_PREDICT_GRID
    )
    measurable_cells = [
        cell_id(npv, pv) for npv in NUM_PREDICT_GRID for pv in ("medium", "long")
    ]
    net_cell_ok = all(
        by_cell_net.get(c, 0) >= DUAL_MIN_NET_MEASURABLE_CELL for c in measurable_cells
    )
    holdout_gross_ok = all(
        holdout_gross.get(cell_id(npv, pv), 0) >= DUAL_HOLDOUT_MIN_PER_CELL
        for npv in NUM_PREDICT_GRID
        for pv in PROMPT_VARIANTS
    )
    holdout_net_ok = all(
        holdout_net.get(c, 0) >= DUAL_HOLDOUT_MIN_PER_CELL for c in measurable_cells
    )

    ids = [str(r.get("action_id") or r.get("snapshot_id")) for r in rows]
    overlap = len(ids) != len(set(ids))
    leak = feature_leakage_audit(list(rows))
    n = len(rows) or 1
    feat_cov = feat_ok / n
    hash_cov = hash_ok / n

    # Split presence: need eligible rows in each split bucket for each head
    buckets_gross = {dual_split_bucket(r) for r in gross}
    buckets_net = {dual_split_bucket(r) for r in net}

    gates = {
        "gross_min_eligible": len(gross) >= DUAL_MIN_GROSS_ELIGIBLE,
        "gross_min_medium_long_cell": medium_long_ok,
        "gross_min_short_cell": short_ok,
        "gross_holdout_min_per_cell": holdout_gross_ok,
        "net_min_eligible": len(net) >= DUAL_MIN_NET_ELIGIBLE,
        "net_min_measurable_cell": net_cell_ok,
        "net_holdout_min_per_cell": holdout_net_ok,
        "feature_coverage_100": feat_cov >= 1.0 - 1e-12,
        "hash_coverage_100": hash_cov >= 1.0 - 1e-12,
        "no_timestamp_inversion": inversions == 0,
        "no_group_overlap": not overlap,
        "no_feature_leakage": bool(leak.get("ok")),
        "split_buckets_present_gross": {"train", "select", "holdout"}.issubset(
            buckets_gross
        ),
        "split_buckets_present_net": {"train", "select", "holdout"}.issubset(
            buckets_net
        ),
    }
    ready = all(gates.values())
    return {
        "ok": ready,
        "at": _utc(),
        "status": (
            "pre_action_dual_corpus_ready"
            if ready
            else "pre_action_dual_corpus_not_ready"
        ),
        "n_rows": len(rows),
        "n_eligible_gross": len(gross),
        "n_eligible_net": len(net),
        "by_cell_gross": dict(by_cell_gross),
        "by_cell_net": dict(by_cell_net),
        "gates": gates,
        "split": {
            "primary_train": list(DUAL_PRIMARY_TRAIN),
            "primary_select": list(DUAL_PRIMARY_SELECT),
            "primary_holdout": list(DUAL_PRIMARY_HOLDOUT),
            "short_recovery_train": list(DUAL_SHORT_TRAIN),
            "short_recovery_select": list(DUAL_SHORT_SELECT),
            "short_recovery_holdout": list(DUAL_SHORT_HOLDOUT),
        },
        "leakage_audit": leak,
        "feature_coverage": feat_cov,
        "hash_coverage": hash_cov,
        "timestamp_inversions": inversions,
        "authority": {
            "operational_authority": False,
            "learning_admission_withheld": True,
            "auto_admit": False,
        },
    }

def evaluate_action_contract_corpus_readiness(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Readiness for Action Contract campaign (task×band grid; never dual merge)."""
    from lib.rid_electrical_pre_action_action_contract import (
        TASK_TYPES,
        TOKEN_BANDS,
        action_contract_cell_id,
        action_contract_split_bucket,
        verify_action_contract_integrity,
    )

    gross = [r for r in rows if r.get("eligible_gross")]
    net = [r for r in rows if r.get("eligible_net")]
    contracts_ok = True
    cells: dict[str, int] = {}
    buckets = set()
    for r in rows:
        snap = r.get("snapshot") if isinstance(r.get("snapshot"), Mapping) else {}
        contract = r.get("action_contract") or (snap or {}).get("action_contract")
        if not isinstance(contract, Mapping):
            contracts_ok = False
            continue
        ok_c, _ = verify_action_contract_integrity(contract)
        if not ok_c:
            contracts_ok = False
        cell = action_contract_cell_id(
            str(contract.get("task_type") or ""),
            str(contract.get("planned_eval_token_band") or ""),
        )
        cells[cell] = cells.get(cell, 0) + 1
        b = action_contract_split_bucket(r)
        if b:
            buckets.add(b)
    needed = [
        action_contract_cell_id(t, b) for t in TASK_TYPES for b in TOKEN_BANDS
    ]
    cells_covered = all(cells.get(c, 0) >= 6 for c in needed)
    gates = {
        "n_rows_ge_72": len(rows) >= 72,
        "n_eligible_gross_ge_48": len(gross) >= 48,
        "n_eligible_net_ge_24": len(net) >= 24,
        "all_contracts_ok": contracts_ok,
        "all_cells_ge_6": cells_covered,
        "split_buckets_present": {"train", "select", "holdout"}.issubset(buckets),
        "never_merge_dual_v1": True,
    }
    ok = all(gates.values())
    return {
        "ok": ok,
        "status": (
            "pre_action_corpus_ready"
            if ok
            else "pre_action_corpus_not_ready"
        ),
        "gates": gates,
        "n_rows": len(rows),
        "n_eligible_gross": len(gross),
        "n_eligible_net": len(net),
        "by_cell": cells,
        "authority": {
            "operational_authority": False,
            "learning_admission_withheld": True,
            "auto_admit": False,
            "auto_refit": False,
            "master_routing_authorized": False,
            "gates_action": False,
        },
    }


def freeze_corpus(
    rows: Sequence[Mapping[str, Any]],
    *,
    write: bool = True,
    out_dir: Path | None = None,
    evidence_source: str | None = None,
    campaign_id: str | None = None,
    dual: bool = False,
) -> dict[str, Any]:
    readiness = (
        evaluate_dual_corpus_readiness(rows)
        if dual
        else evaluate_corpus_readiness(rows)
    )
    ev = evidence_source or "unspecified"
    payload = {
        "ok": bool(readiness.get("ok")),
        "at": _utc(),
        "status": readiness.get("status"),
        "readiness": readiness,
        "n_rows": len(rows),
        "rows": list(rows),
        "evidence_source": ev,
        "campaign_id": campaign_id,
        "schema_version": "PreActionSnapshotV2",
        "plant_config_id": PLANT_CONFIG_ID,
        "dual": bool(dual),
        "note": (
            "Existing controlled artifacts may seed throughput only; "
            "train/holdout rows require immutable PreActionSnapshotV2. "
            "Synthetic harness evidence cannot promote plant readiness. "
            "V1 closed_not_ready campaigns are excluded from fitting."
        ),
        "authority": readiness.get("authority"),
    }
    # corpus hash excluding bulky nested redundancy: hash row snapshot_ids + labels
    import hashlib

    digest_src = json.dumps(
        [
            {
                "snapshot_id": r.get("snapshot_id"),
                "action_id": r.get("action_id"),
                "eligible": r.get("eligible"),
                "eligible_gross": r.get("eligible_gross"),
                "eligible_net": r.get("eligible_net"),
                "y_net": (r.get("label") or {}).get("E_net_raw_j"),
                "y_gross": (r.get("label") or {}).get("E_generate_j"),
            }
            for r in rows
        ],
        sort_keys=True,
        default=str,
    )
    payload["corpus_hash"] = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()
    if write:
        dest = out_dir or CAMPAIGN
        dest.mkdir(parents=True, exist_ok=True)
        freeze_json = dest / "pre_action_corpus_freeze_latest.json"
        freeze_md = dest / "pre_action_corpus_freeze_latest.md"
        ready_json = dest / "pre_action_corpus_readiness_latest.json"
        ready_md = dest / "pre_action_corpus_readiness_latest.md"
        freeze_json.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        freeze_md.write_text(
            "\n".join(
                [
                    "# Pre-action corpus freeze",
                    "",
                    f"- status: {payload['status']}",
                    f"- evidence_source: {ev}",
                    f"- campaign_id: {campaign_id}",
                    f"- dual: {dual}",
                    f"- n_eligible_gross: {readiness.get('n_eligible_gross', readiness.get('n_eligible'))}",
                    f"- n_eligible_net: {readiness.get('n_eligible_net', readiness.get('n_eligible'))}",
                    f"- ready: {payload['ok']}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        ready_payload = {**readiness, "evidence_source": ev, "campaign_id": campaign_id}
        ready_json.write_text(json.dumps(ready_payload, indent=2, default=str), encoding="utf-8")
        ready_md.write_text(
            "\n".join(
                [
                    "# Pre-action corpus readiness",
                    "",
                    f"- status: {readiness.get('status')}",
                    f"- evidence_source: {ev}",
                    f"- gates: `{readiness.get('gates')}`",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    return payload

def split_rows_by_group(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    train, select, holdout = [], [], []
    for r in rows:
        if not r.get("eligible"):
            continue
        g = int((r.get("snapshot") or {}).get("collection_group") or 0)
        if g in TRAIN_GROUPS:
            train.append(dict(r))
        elif g in SELECT_GROUPS:
            select.append(dict(r))
        elif g in HOLDOUT_GROUPS:
            holdout.append(dict(r))
    return {"train": train, "select": select, "holdout": holdout}


def synthesize_ready_corpus(
    *,
    n_groups: int = N_COLLECTION_GROUPS,
    seed_tps: float = 103.0,
    noise_j: float = 5.0,
) -> list[dict[str, Any]]:
    """Deterministic synthetic corpus for unit tests / dry-run freeze (not plant evidence)."""
    from lib.rid_electrical_pre_action_snapshot import (
        LOCKED_MODEL_CONFIG_HASH,
        capture_pre_action_snapshot,
        compute_snapshot_hash,
        extract_feature_vector,
    )
    from lib.rid_electrical_predictor import ALPHA, BETA

    plans = collection_plan(n_groups=n_groups)
    # Pre-seed history at 103.2 so all grid num_predict stay in [2.5, 4.5] s.
    seed = [
        {
            "at": f"2026-07-01T00:{i:02d}:00+00:00",
            "plant_config_id": PLANT_CONFIG_ID,
            "model": MODEL_ID,
            "residency": "warm_repeat",
            "tokens_per_s": 103.2,
        }
        for i in range(30)
    ]
    build_throughput_seed_from_controlled(seed)

    rows: list[dict[str, Any]] = []
    history = list(seed)
    for i, plan in enumerate(plans):
        tps, hist_n = trailing_throughput_tps(
            history,
            plant_config_id=PLANT_CONFIG_ID,
            model=MODEL_ID,
        )
        assert tps is not None and hist_n >= 5
        ts = f"2026-07-20T{i // 60:02d}:{i % 60:02d}:00+00:00"
        snap = capture_pre_action_snapshot(
            action_id=plan["action_id"],
            num_predict=plan["num_predict"],
            prompt=plan["prompt"],
            gpu_temp_start_c=45.0 + (i % 10) * 0.3,
            settled_idle_power_w=55.0,
            trailing_throughput_tps=tps,
            throughput_history_count=hist_n,
            collection_session_id=f"synth_group_{plan['collection_group']}",
            collection_group=plan["collection_group"],
            prompt_variant=plan["prompt_variant"],
            planned_response_profile=plan.get("planned_response_profile"),
            block_kind=plan.get("block_kind") or BLOCK_PRIMARY,
            persist=False,
            at=ts,
        )
        assert snap["model_config_hash"] == LOCKED_MODEL_CONFIG_HASH
        t_hat = plan["num_predict"] / float(tps)
        if not (2.5 <= t_hat <= 4.5):
            tps = plan["num_predict"] / 3.5
            snap["trailing_throughput_tps"] = tps
            snap["snapshot_hash"] = compute_snapshot_hash(snap)
            t_hat = plan["num_predict"] / float(tps)
        y_net = float(ALPHA) + float(BETA) * t_hat + ((i % 7) - 3) * noise_j * 0.2
        y_gross = y_net + 55.0 * t_hat
        outcome_at = f"2026-07-20T{i // 60:02d}:{i % 60:02d}:05+00:00"
        feats = extract_feature_vector(snap)
        profile = str(snap.get("planned_response_profile") or "unknown")
        eligible_net = profile == "measurable"
        row = {
            "schema_version": "PreActionCorpusRowV2",
            "snapshot_id": snap["snapshot_id"],
            "action_id": snap["action_id"],
            "collection_session_id": snap["collection_session_id"],
            "day_id": snap["day_id"],
            "collection_group": plan["collection_group"],
            "block_kind": plan.get("block_kind") or BLOCK_PRIMARY,
            "planned_response_profile": profile,
            "snapshot": snap,
            "features": feats,
            "label": {
                "y_gross": "E_generate",
                "y_net": "E_net_raw",
                "y": "E_net_raw",
                "E_generate_j": y_gross,
                "E_net_raw_j": y_net,
                "measurement_state": "measured",
                "snr_net": 8.0,
                "settle_ok": True,
                "integration_ok": True,
                "n_samples": 20,
                "outcome_at": outcome_at,
                "eligible_gross": True,
                "eligible_net": eligible_net,
            },
            "eligible_gross": True,
            "eligible_net": eligible_net,
            "eligible": True,
            "eligibility_reasons": [],
            "confidence": "ok",
            "measured_tokens_per_s": float(tps) * (1.0 + ((i % 5) - 2) * 0.01),
            "eval_duration_s": t_hat,
            "actual_eval_tokens": plan["num_predict"],
            "synthetic": True,
            "evidence_source": "synthetic_harness_only",
        }
        rows.append(row)
        history.append(
            {
                "at": outcome_at,
                "plant_config_id": PLANT_CONFIG_ID,
                "model": MODEL_ID,
                "residency": "warm_repeat",
                "tokens_per_s": row["measured_tokens_per_s"],
            }
        )
    return rows


def synthesize_signal_corpus_for_admission() -> list[dict[str, Any]]:
    """Synthetic rows where GPU start temp adds signal baseline cannot see."""
    rows = synthesize_ready_corpus()
    from lib.rid_electrical_predictor import ALPHA, BETA
    from lib.rid_electrical_pre_action_snapshot import (
        compute_snapshot_hash,
        prompt_stats,
    )

    # Hold prompt features constant so the identifiable extra signal is temperature.
    fixed_prompt = "Explain GPU power draw briefly."
    stats = prompt_stats(fixed_prompt)
    out = []
    for i, r in enumerate(rows):
        snap = dict(r["snapshot"])
        feats = dict(r["features"] or {})
        temp = 47.0 + ((i % 15) - 7)
        snap["gpu_temp_start_c"] = temp
        snap["prompt_utf8_bytes"] = stats["prompt_utf8_bytes"]
        snap["prompt_word_count"] = stats["prompt_word_count"]
        snap["prompt_message_count"] = stats["prompt_message_count"]
        snap["throughput_history_count"] = 20
        snap["settled_idle_power_w"] = 55.0
        # keep original prompt_variant label for cell coverage accounting
        feats["gpu_temp_start_c"] = float(temp)
        feats["prompt_utf8_bytes"] = float(stats["prompt_utf8_bytes"])
        feats["prompt_word_count"] = float(stats["prompt_word_count"])
        feats["prompt_message_count"] = float(stats["prompt_message_count"])
        feats["throughput_history_count"] = 20.0
        feats["settled_idle_power_w"] = 55.0
        snap["snapshot_hash"] = compute_snapshot_hash(snap)
        tps = float(feats["trailing_throughput_tps"])
        t_hat = float(feats["num_predict"]) / tps
        y = float(ALPHA) + float(BETA) * t_hat + 8.0 * (temp - 47.0)
        lab = dict(r["label"])
        lab["E_net_raw_j"] = y
        out.append({**r, "snapshot": snap, "features": feats, "label": lab})
    return out


def build_throughput_seed_from_sessions() -> dict[str, Any]:
    """Scan controlled session artifacts for throughput seed rows."""
    sessions = AUTO_ARTIFACTS / "rid_electrical" / "sessions"
    rows: list[dict[str, Any]] = []
    if sessions.exists():
        for path in sessions.rglob("controlled_action_v2.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            infer = data.get("infer") or data
            toks = infer.get("eval_count") or data.get("actual_eval_tokens")
            dur = infer.get("eval_duration_s") or data.get("eval_duration_s")
            rows.append(
                {
                    "at": data.get("at"),
                    "plant_config_id": data.get("plant_config_id") or PLANT_CONFIG_ID,
                    "model": data.get("model") or MODEL_ID,
                    "residency": data.get("residency") or "warm_repeat",
                    "actual_eval_tokens": toks,
                    "eval_duration_s": dur,
                    "tokens_per_s": (
                        float(toks) / float(dur)
                        if toks is not None and dur is not None and float(dur) > 0
                        else None
                    ),
                }
            )
    return build_throughput_seed_from_controlled(rows)
