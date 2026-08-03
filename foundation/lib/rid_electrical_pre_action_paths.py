#!/usr/bin/env python3
"""Artifact paths for pre_action_energy_v1 synthetic vs plant evidence."""
from __future__ import annotations

from pathlib import Path

from lib.paths import AUTO_ARTIFACTS

LEDGER_CAMPAIGN = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
PRE_ACTION_ROOT = LEDGER_CAMPAIGN / "pre_action"
SYNTHETIC_DIR = PRE_ACTION_ROOT / "synthetic"
PLANT_ROOT = PRE_ACTION_ROOT / "plant"

EVIDENCE_SYNTHETIC = "synthetic_harness_only"
EVIDENCE_PLANT = "plant"
SCHEMA_VERSION_V1 = "PreActionSnapshotV1"
SCHEMA_VERSION = "PreActionSnapshotV2"
SCHEMA_VERSION_V2 = SCHEMA_VERSION
DUAL_CAMPAIGN_ID = "pre_action_energy_dual_v1_plant_v1"
V1_CAMPAIGN_ID = "pre_action_energy_v1_plant_v1"


def plant_dir(campaign_id: str) -> Path:
    return PLANT_ROOT / str(campaign_id)


def ensure_layout() -> None:
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    PLANT_ROOT.mkdir(parents=True, exist_ok=True)
