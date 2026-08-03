#!/usr/bin/env python3
"""Resumable plant campaign manifests for pre_action energy campaigns."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from lib.rid_electrical_pre_action_campaign_status import (
    ACTION_CONTRACT_CAMPAIGN_ID,
    DUAL_CAMPAIGN_ID,
    assert_campaign_fittable,
)
from lib.rid_electrical_pre_action_action_contract import (
    action_contract_plans_for_groups,
)
from lib.rid_electrical_pre_action_corpus import (
    BLOCK_PRIMARY,
    BLOCK_SHORT_RECOVERY,
    collection_plan,
    dual_full_collection_plan,
    dual_primary_collection_plan,
    dual_short_recovery_plan,
)
from lib.rid_electrical_pre_action_paths import EVIDENCE_PLANT, ensure_layout, plant_dir


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_groups_spec(spec: str) -> list[int]:
    """Parse '1' or '2-8' or '1,3,5' into sorted unique group ints."""
    out: set[int] = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo, hi = int(a), int(b)
            if hi < lo:
                lo, hi = hi, lo
            out.update(range(lo, hi + 1))
        else:
            out.add(int(part))
    return sorted(out)


def action_key(
    *,
    campaign_id: str,
    collection_group: int,
    cell_id: str,
    action_id: str,
    block_kind: str = BLOCK_PRIMARY,
) -> str:
    return (
        f"{campaign_id}|{block_kind}|g{int(collection_group)}|{cell_id}|{action_id}"
    )


def manifest_path(campaign_id: str) -> Path:
    return plant_dir(campaign_id) / "campaign_manifest.json"


def load_manifest(campaign_id: str) -> dict[str, Any]:
    path = manifest_path(campaign_id)
    if not path.exists():
        return {
            "ok": True,
            "campaign_id": campaign_id,
            "evidence_source": EVIDENCE_PLANT,
            "completed_keys": {},
            "rows": [],
            "created_at": _utc(),
            "updated_at": _utc(),
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(manifest: dict[str, Any]) -> Path:
    ensure_layout()
    cid = str(manifest["campaign_id"])
    d = plant_dir(cid)
    d.mkdir(parents=True, exist_ok=True)
    manifest["updated_at"] = _utc()
    path = manifest_path(cid)
    path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return path


def plans_for_groups(groups: Sequence[int]) -> list[dict[str, Any]]:
    gset = set(int(g) for g in groups)
    return [p for p in collection_plan() if int(p["collection_group"]) in gset]


def dual_plans_for_spec(
    *,
    primary_groups: Sequence[int] | None = None,
    short_recovery_groups: Sequence[int] | None = None,
) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    if primary_groups:
        gset = set(int(g) for g in primary_groups)
        plans.extend(
            p
            for p in dual_primary_collection_plan()
            if int(p["collection_group"]) in gset
        )
    if short_recovery_groups:
        gset = set(int(g) for g in short_recovery_groups)
        plans.extend(
            p
            for p in dual_short_recovery_plan()
            if int(p["collection_group"]) in gset
        )
    return plans


def pending_plans(
    campaign_id: str,
    groups: Sequence[int],
    *,
    resume: bool = True,
    max_actions: int | None = None,
    block_kind: str = BLOCK_PRIMARY,
    short_recovery_groups: Sequence[int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if campaign_id == DUAL_CAMPAIGN_ID or str(campaign_id).startswith(
        "pre_action_energy_dual"
    ):
        assert_campaign_fittable(campaign_id)
        if short_recovery_groups is not None or block_kind == BLOCK_SHORT_RECOVERY:
            if block_kind == BLOCK_SHORT_RECOVERY:
                plans = dual_plans_for_spec(
                    short_recovery_groups=groups,
                )
            else:
                plans = dual_plans_for_spec(
                    primary_groups=groups,
                    short_recovery_groups=short_recovery_groups,
                )
        else:
            plans = dual_plans_for_spec(primary_groups=groups)
    elif (
        campaign_id == ACTION_CONTRACT_CAMPAIGN_ID
        or str(campaign_id).startswith("pre_action_energy_action_contract")
    ):
        assert_campaign_fittable(campaign_id)
        plans = action_contract_plans_for_groups(groups)
    else:
        plans = plans_for_groups(groups)
    manifest = load_manifest(campaign_id)
    completed = set((manifest.get("completed_keys") or {}).keys())
    pending = []
    for p in plans:
        key = action_key(
            campaign_id=campaign_id,
            collection_group=int(p["collection_group"]),
            cell_id=str(p["cell_id"]),
            action_id=str(p["action_id"]),
            block_kind=str(p.get("block_kind") or BLOCK_PRIMARY),
        )
        p = {**p, "resume_key": key}
        if resume and key in completed:
            continue
        pending.append(p)
    if max_actions is not None:
        pending = pending[: int(max_actions)]
    return pending, manifest


def record_completed(
    manifest: dict[str, Any],
    *,
    plan: dict[str, Any],
    corpus_row: dict[str, Any],
) -> dict[str, Any]:
    key = str(
        plan.get("resume_key")
        or action_key(
            campaign_id=str(manifest["campaign_id"]),
            collection_group=int(plan["collection_group"]),
            cell_id=str(plan["cell_id"]),
            action_id=str(plan["action_id"]),
            block_kind=str(plan.get("block_kind") or BLOCK_PRIMARY),
        )
    )
    completed = dict(manifest.get("completed_keys") or {})
    if key in completed:
        raise ValueError(f"duplicate_resume_key:{key}")
    completed[key] = {
        "at": _utc(),
        "snapshot_id": corpus_row.get("snapshot_id"),
        "eligible": corpus_row.get("eligible"),
        "eligible_gross": corpus_row.get("eligible_gross"),
        "eligible_net": corpus_row.get("eligible_net"),
        "action_id": plan.get("action_id"),
    }
    manifest["completed_keys"] = completed
    rows = list(manifest.get("rows") or [])
    rows.append(corpus_row)
    manifest["rows"] = rows
    save_manifest(manifest)
    return manifest


def all_manifest_rows(campaign_id: str) -> list[dict[str, Any]]:
    return list(load_manifest(campaign_id).get("rows") or [])
