#!/usr/bin/env python3
"""Apply pre_action_energy_v1 readiness fields — plant evidence only.

Synthetic harness artifacts cannot promote plant readiness flags.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS
import lib.rid_electrical_policy as _policy
from lib.rid_electrical_pre_action_paths import (
    EVIDENCE_PLANT,
    EVIDENCE_SYNTHETIC,
    PLANT_ROOT,
    SYNTHETIC_DIR,
    ensure_layout,
)

CAMPAIGN = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
MONITOR_LOCK = CAMPAIGN / "PRE_ACTION_TRAINING_READINESS_MONITOR_LOCK.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _latest_plant_artifact(name: str) -> dict[str, Any] | None:
    """Prefer newest plant/<campaign_id>/<name> with evidence_source=plant.

    Skips campaigns locked closed_not_ready.
    """
    from lib.rid_electrical_pre_action_campaign_status import is_closed_not_ready

    ensure_layout()
    if not PLANT_ROOT.exists():
        return None
    candidates: list[tuple[float, dict[str, Any]]] = []
    for path in PLANT_ROOT.glob(f"*/{name}"):
        campaign_id = path.parent.name
        if is_closed_not_ready(campaign_id):
            continue
        data = _read_json(path)
        if not data:
            continue
        if str(data.get("evidence_source") or "") != EVIDENCE_PLANT:
            continue
        candidates.append((path.stat().st_mtime, data))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def sync_pre_action_readiness_from_artifacts() -> dict[str, Any]:
    """Update readiness flags from plant artifacts only; learning stays withheld."""
    els = _policy.ENERGY_LEARNING_STATE
    monitor_ok = False
    mon = _read_json(MONITOR_LOCK)
    if mon:
        monitor_ok = bool(mon.get("ok"))

    readiness = _latest_plant_artifact("pre_action_corpus_readiness_latest.json")
    corpus_ready = bool(
        readiness
        and str(readiness.get("status") or "")
        in {"pre_action_corpus_ready", "pre_action_dual_corpus_ready"}
        and str(readiness.get("evidence_source") or "") == EVIDENCE_PLANT
    )

    train = _latest_plant_artifact("pre_action_offline_train_latest.json")
    offline = bool(
        train
        and str(train.get("status") or "")
        in {
            "pre_action_offline_candidate_for_shadow",
            "pre_action_energy_v1_plant_candidate_for_shadow",
            "pre_action_energy_dual_heads_trained",
            "pre_action_energy_dual_gross_candidate_for_shadow",
            "pre_action_energy_dual_net_candidate_for_shadow",
        }
        and str(train.get("evidence_source") or "") == EVIDENCE_PLANT
    )
    # Also accept if either dual head passed
    if train and not offline and str(train.get("evidence_source") or "") == EVIDENCE_PLANT:
        g = train.get("gross") or {}
        n = train.get("net") or {}
        offline = bool(
            (g.get("admission") or {}).get("passed")
            or (n.get("admission") or {}).get("passed")
        )

    shadow = _latest_plant_artifact("pre_action_shadow_validation_latest.json")
    shadow_ok = bool(
        shadow
        and str(shadow.get("status") or "")
        == "pre_action_energy_shadow_validated_candidate_for_separate_review"
        and str(shadow.get("evidence_source") or "") == EVIDENCE_PLANT
    )

    # Explicitly ignore synthetic harness paths
    syn_ready = _read_json(SYNTHETIC_DIR / "pre_action_corpus_readiness_latest.json")
    synthetic_ignored = bool(
        syn_ready and str(syn_ready.get("evidence_source") or "") == EVIDENCE_SYNTHETIC
    )

    els["pre_action_training_readiness"] = bool(monitor_ok)
    els["pre_action_corpus_ready"] = corpus_ready
    els["pre_action_offline_candidate"] = offline
    els["pre_action_shadow_validated"] = shadow_ok
    els["pre_action_model_id"] = "pre_action_energy_dual_v1"
    els["learning_admission_withheld"] = True
    _policy.LEARNING_ADMISSION_WITHHELD = True
    _policy.LEARNING_ADMISSION_GRANTED = False
    return {
        "ok": True,
        "pre_action_training_readiness": els["pre_action_training_readiness"],
        "pre_action_corpus_ready": els["pre_action_corpus_ready"],
        "pre_action_offline_candidate": els["pre_action_offline_candidate"],
        "pre_action_shadow_validated": els["pre_action_shadow_validated"],
        "synthetic_ignored": synthetic_ignored,
        "learning_admission_withheld": True,
        "learning_admission_granted": False,
    }
