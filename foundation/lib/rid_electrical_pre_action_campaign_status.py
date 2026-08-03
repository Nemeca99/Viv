#!/usr/bin/env python3
"""Plant campaign status locks (closed / not-justified exclusion)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from lib.rid_electrical_pre_action_paths import EVIDENCE_PLANT, plant_dir

V1_CAMPAIGN_ID = "pre_action_energy_v1_plant_v1"
DUAL_CAMPAIGN_ID = "pre_action_energy_dual_v1_plant_v1"
ACTION_CONTRACT_CAMPAIGN_ID = "pre_action_energy_action_contract_v1_plant_v1"
STATUS_LOCK_NAME = "CAMPAIGN_STATUS_LOCK.json"
CLOSED_NOT_READY = "closed_not_ready"
DUAL_TRAINING_NOT_JUSTIFIED = "dual_target_training_not_justified"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def status_lock_path(campaign_id: str) -> Path:
    return plant_dir(campaign_id) / STATUS_LOCK_NAME


def load_campaign_status(campaign_id: str) -> dict[str, Any] | None:
    path = status_lock_path(campaign_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def is_closed_not_ready(campaign_id: str) -> bool:
    lock = load_campaign_status(campaign_id)
    if not lock:
        return False
    return str(lock.get("status") or "") == CLOSED_NOT_READY


def is_same_matrix_expansion_forbidden(campaign_id: str) -> bool:
    lock = load_campaign_status(campaign_id)
    if not lock:
        return False
    return bool(lock.get("excluded_from_refit_same_matrix"))


def assert_campaign_fittable(campaign_id: str) -> None:
    """Raise if campaign is locked closed_not_ready or excluded from fitting."""
    cid = str(campaign_id or "")
    if not cid:
        raise ValueError("campaign_id_required")
    if is_closed_not_ready(cid):
        raise RuntimeError(f"campaign_closed_not_ready:{cid}")
    lock = load_campaign_status(cid)
    if lock and bool(lock.get("excluded_from_fitting")):
        raise RuntimeError(f"campaign_excluded_from_fitting:{cid}")


def assert_same_matrix_expandable(campaign_id: str) -> None:
    """Raise if campaign forbids further same-matrix collection."""
    if is_same_matrix_expansion_forbidden(campaign_id):
        raise RuntimeError(f"campaign_same_matrix_expansion_forbidden:{campaign_id}")


def write_status_lock(
    campaign_id: str,
    *,
    status: str,
    corpus_hash: str,
    n_rows: int,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    dest = plant_dir(campaign_id)
    dest.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "ok": True,
        "at": _utc(),
        "campaign_id": campaign_id,
        "evidence_source": EVIDENCE_PLANT,
        "status": status,
        "corpus_hash": corpus_hash,
        "n_rows": int(n_rows),
        "authority": {
            "operational_authority": False,
            "learning_admission_withheld": True,
            "auto_admit": False,
            "auto_refit": False,
            "master_routing_authorized": False,
            "gates_action": False,
        },
    }
    if extra:
        payload.update(dict(extra))
    path = status_lock_path(campaign_id)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["artifact"] = str(path).replace("\\", "/")
    return payload


def write_closed_not_ready_lock(
    campaign_id: str,
    *,
    corpus_hash: str,
    n_rows: int,
    n_eligible: int,
    gates: Mapping[str, Any],
    ineligibility_tallies: Mapping[str, int],
    readiness_status: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    base_extra: dict[str, Any] = {
        "excluded_from_fitting": True,
        "n_eligible": int(n_eligible),
        "readiness_status": readiness_status,
        "gates": dict(gates),
        "ineligibility_tallies": dict(ineligibility_tallies),
        "note": (
            "Negative design evidence only. Never merge rows into later campaigns "
            "or use for offline train / shadow admission."
        ),
    }
    if extra:
        base_extra.update(dict(extra))
    return write_status_lock(
        campaign_id,
        status=CLOSED_NOT_READY,
        corpus_hash=corpus_hash,
        n_rows=n_rows,
        extra=base_extra,
    )


def write_dual_training_not_justified_lock() -> dict[str, Any]:
    """Freeze dual cycle: defensible negative; forbid same-matrix expansion."""
    root = plant_dir(DUAL_CAMPAIGN_ID)
    freeze_path = root / "pre_action_corpus_freeze_latest.json"
    ready_path = root / "pre_action_corpus_readiness_latest.json"
    train_path = root / "pre_action_offline_train_latest.json"
    corpus_hash = ""
    n_rows = 200
    n_gross = 0
    n_net = 0
    readiness_status = ""
    gates: dict[str, Any] = {}
    head_admissions: dict[str, Any] = {}
    if freeze_path.exists():
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        corpus_hash = str(freeze.get("corpus_hash") or "")
    if ready_path.exists():
        ready = json.loads(ready_path.read_text(encoding="utf-8"))
        n_rows = int(ready.get("n_rows") or n_rows)
        n_gross = int(ready.get("n_eligible_gross") or 0)
        n_net = int(ready.get("n_eligible_net") or 0)
        readiness_status = str(ready.get("status") or "")
        gates = dict(ready.get("gates") or {})
    if train_path.exists():
        train = json.loads(train_path.read_text(encoding="utf-8"))
        for head in ("gross", "net"):
            h = train.get(head) or {}
            head_admissions[head] = {
                "status": h.get("status"),
                "gates": (h.get("admission") or {}).get("gates"),
                "holdout_candidate_metrics": h.get("holdout_candidate_metrics"),
                "holdout_baseline_metrics": h.get("holdout_baseline_metrics"),
            }
    if not corpus_hash:
        corpus_hash = (
            "cf956ff162a5e703ae7e3697ed9774dfb0c92ba430375fa3d2d8bd110fc52591"
        )
    return write_status_lock(
        DUAL_CAMPAIGN_ID,
        status=DUAL_TRAINING_NOT_JUSTIFIED,
        corpus_hash=corpus_hash,
        n_rows=n_rows,
        extra={
            "excluded_from_fitting": False,
            "excluded_from_refit_same_matrix": True,
            "n_eligible_gross": n_gross,
            "n_eligible_net": n_net,
            "readiness_status": readiness_status,
            "readiness_gates": gates,
            "head_admissions": head_admissions,
            "interpretation": "missing_action_contract_workload",
            "next_scientific_question": "action_contract_workload_predictability",
            "successor_campaign_id": ACTION_CONTRACT_CAMPAIGN_ID,
            "note": (
                "Defensible offline negative: RMSE improved vs baseline but "
                "admission failed. Do not expand the same 15-cell matrix. "
                "Next question is pre-action Action Contract workload demand."
            ),
        },
    )


def write_v1_closed_not_ready_lock() -> dict[str, Any]:
    """Lock the failed single-target plant V1 corpus as negative evidence."""
    root = plant_dir(V1_CAMPAIGN_ID)
    freeze_path = root / "pre_action_corpus_freeze_latest.json"
    ready_path = root / "pre_action_corpus_readiness_latest.json"
    manifest_path = root / "campaign_manifest.json"
    corpus_hash = ""
    n_rows = 120
    n_eligible = 84
    gates: dict[str, Any] = {}
    readiness_status = "pre_action_corpus_not_ready"
    if freeze_path.exists():
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        corpus_hash = str(freeze.get("corpus_hash") or "")
        readiness_status = str(freeze.get("status") or readiness_status)
    if ready_path.exists():
        ready = json.loads(ready_path.read_text(encoding="utf-8"))
        n_rows = int(ready.get("n_rows") or n_rows)
        n_eligible = int(ready.get("n_eligible") or n_eligible)
        gates = dict(ready.get("gates") or {})
        readiness_status = str(ready.get("status") or readiness_status)
    tallies: dict[str, int] = {}
    if manifest_path.exists():
        rows = list(
            (json.loads(manifest_path.read_text(encoding="utf-8")).get("rows") or [])
        )
        for r in rows:
            for reason in r.get("eligibility_reasons") or []:
                key = str(reason)
                tallies[key] = tallies.get(key, 0) + 1
    if not corpus_hash:
        corpus_hash = (
            "22476428a9eb903fbb4390a2792766bef52c866e35d43cfd48d710607af8132a"
        )
    return write_closed_not_ready_lock(
        V1_CAMPAIGN_ID,
        corpus_hash=corpus_hash,
        n_rows=n_rows,
        n_eligible=n_eligible,
        gates=gates,
        ineligibility_tallies=tallies,
        readiness_status=readiness_status,
        extra={
            "failure_summary": {
                "min_eligible_failed": n_eligible < 100,
                "short_cells_snr_starved": True,
                "primary_reasons": ["snr_net_below_3", "integration_failed"],
            },
            "successor_campaign_id": DUAL_CAMPAIGN_ID,
        },
    )
