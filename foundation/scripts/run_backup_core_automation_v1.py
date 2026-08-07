#!/usr/bin/env python3
"""Run the local-first AIOS backup_core automation once and write a receipt.

Default profile ``safe`` copies sovereign code/config/docs/audit + UML evidence
into the governed content-addressed vault. Weight packs under models/gpu, *.pt /
*.pth / *.gguf / *.safetensors, and test_training/runs are denied unless the
operator explicitly passes ``--catalog-models`` (hash catalog only; still no
weight copy).

This script never starts AIOS, never restores live files, never deletes, and
never replicates off-disk.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_adapter_backup import create_automation, plan_automation  # noqa: E402
from lib.backup_core import RECEIPTS_ROOT, verify_snapshot  # noqa: E402


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_receipt(stamp: str, payload: dict) -> Path:
    folder = RECEIPTS_ROOT / stamp
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "RECEIPT.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (folder / "RECEIPT.md").write_text(
        "\n".join(
            [
                f"# backup_core automation receipt `{stamp}`",
                "",
                f"- ok: `{payload.get('ok')}`",
                f"- profile: `{payload.get('profile')}`",
                f"- mode: `{payload.get('mode')}`",
                f"- snapshot_id: `{payload.get('snapshot_id')}`",
                f"- copied_items: `{payload.get('copied_items')}`",
                f"- logical_bytes: `{payload.get('logical_bytes')}`",
                f"- new_object_bytes: `{payload.get('new_object_bytes')}`",
                f"- skipped_count: `{payload.get('skipped_count')}`",
                f"- deny_weight_packs: `{payload.get('deny_weight_packs')}`",
                f"- catalog_models: `{payload.get('catalog_models')}`",
                f"- aios_runtime_started: `{payload.get('aios_runtime_started')}`",
                f"- manifest_path: `{payload.get('manifest_path')}`",
                "",
                "## Exclusion counts",
                "",
                "```json",
                json.dumps(payload.get("exclusion_counts") or {}, indent=2),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("safe", "uml_lane", "legacy_default"),
        default="safe",
        help="Automation include set. Default: safe (code+UML, no openaster weight trees).",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Expand and plan only; do not authorize or write vault objects.",
    )
    parser.add_argument(
        "--catalog-models",
        action="store_true",
        help="Operator gate: hash-catalog immutable GGUF/HF bases (still no weight copy).",
    )
    parser.add_argument(
        "--trigger",
        default="backup_core_automation_v1",
        help="Snapshot trigger label recorded in the vault manifest.",
    )
    args = parser.parse_args()
    stamp = _utc_stamp()
    trigger = f"{args.trigger}:{args.profile}:{stamp}"

    if args.plan_only:
        plan = plan_automation(
            trigger=trigger,
            profile=args.profile,
            catalog_models=args.catalog_models,
        )
        receipt = {
            "schema_version": "viv_backup_automation_receipt_v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "stamp": stamp,
            "mode": "plan_only",
            "ok": bool(plan.get("ok")),
            "profile": args.profile,
            "trigger": trigger,
            "snapshot_id": None,
            "manifest_path": None,
            "copied_items": plan.get("file_count"),
            "logical_bytes": plan.get("logical_bytes"),
            "new_object_bytes": 0,
            "skipped_count": plan.get("skipped_count"),
            "exclusion_counts": plan.get("exclusion_counts"),
            "deny_weight_packs": True,
            "catalog_models": bool(args.catalog_models),
            "aios_runtime_started": False,
            "plan": plan,
        }
        path = _write_receipt(stamp, receipt)
        print(json.dumps({"ok": receipt["ok"], "receipt": str(path).replace("\\", "/"), **{k: receipt[k] for k in ("mode", "profile", "copied_items", "logical_bytes", "skipped_count", "exclusion_counts")}}, indent=2))
        return 0 if receipt["ok"] else 1

    result = create_automation(
        trigger=trigger,
        profile=args.profile,
        catalog_models=args.catalog_models,
    )
    plan = (result.get("evidence") or {}).get("plan") or {}
    snapshot = (result.get("evidence") or {}).get("snapshot") or {}
    snapshot_id = snapshot.get("snapshot_id")
    verification = None
    if snapshot_id:
        try:
            verification = verify_snapshot(str(snapshot_id), verify_catalog=False)
        except Exception as exc:  # noqa: BLE001 - receipt must record failure
            verification = {"ok": False, "error": str(exc)}
    receipt = {
        "schema_version": "viv_backup_automation_receipt_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stamp": stamp,
        "mode": "execute",
        "ok": bool(result.get("ok")) and bool((verification or {}).get("ok")),
        "profile": args.profile,
        "trigger": trigger,
        "snapshot_id": snapshot_id,
        "manifest_path": snapshot.get("manifest_path"),
        "copied_items": snapshot.get("copied_items"),
        "catalog_items": snapshot.get("catalog_items"),
        "logical_bytes": snapshot.get("logical_bytes"),
        "new_object_bytes": snapshot.get("new_object_bytes"),
        "decision_id": snapshot.get("decision_id"),
        "skipped_count": plan.get("skipped_count"),
        "exclusion_counts": plan.get("exclusion_counts"),
        "deny_weight_packs": True,
        "catalog_models": bool(args.catalog_models),
        "aios_runtime_started": False,
        "live_restore_performed": False,
        "deletion_performed": False,
        "external_replication": "unconfigured",
        "plan_summary": {
            "root_count": plan.get("root_count"),
            "file_count": plan.get("file_count"),
            "logical_bytes": plan.get("logical_bytes"),
            "uml_roots": plan.get("uml_roots"),
        },
        "verification": verification,
        "error": None if result.get("ok") else snapshot.get("error") or plan,
    }
    path = _write_receipt(stamp, receipt)
    print(
        json.dumps(
            {
                "ok": receipt["ok"],
                "receipt": str(path).replace("\\", "/"),
                "snapshot_id": snapshot_id,
                "manifest_path": snapshot.get("manifest_path"),
                "copied_items": snapshot.get("copied_items"),
                "logical_bytes": snapshot.get("logical_bytes"),
                "new_object_bytes": snapshot.get("new_object_bytes"),
                "skipped_count": plan.get("skipped_count"),
                "exclusion_counts": plan.get("exclusion_counts"),
                "deny_weight_packs": True,
                "aios_runtime_started": False,
            },
            indent=2,
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
