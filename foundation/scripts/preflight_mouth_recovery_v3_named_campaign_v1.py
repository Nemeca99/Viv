#!/usr/bin/env python3
"""Read-only preflight for a named V3 recovery campaign.

Unlike the historical V1 preflight, this command is parameterized by campaign
root and emits the exact receipt shape consumed by the V3 named authorizer.
It never changes campaign authority, opens a lease, loads a model, or trains.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import FAIL, PASS, judge  # noqa: E402


EXPECTED_EVAL = {
    "development": (64, PASS),
    "blind": (32, PASS),
    "legacy": (64, PASS),
    "auditor_negative": (20, FAIL),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    root = args.campaign_root.resolve()
    source_root = args.source_root.resolve()
    report_path = (args.report or (root / "PREFLIGHT_READ_ONLY_NAMED.json")).resolve()
    if report_path.exists():
        raise FileExistsError(f"refuse_to_overwrite:{report_path}")

    findings: list[str] = []
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "CAMPAIGN_ADMITTED_TRAINING_CLOSED":
        findings.append("manifest_status")
    for key in ("training_authorized", "run_authorized", "lora_authorized", "dpo_authorized"):
        if manifest.get(key) is not False:
            findings.append(f"manifest_{key}")
    if manifest.get("lease_opened") is not False or manifest.get("gpu_steps") != 0:
        findings.append("manifest_execution_state")

    file_checks: dict[str, dict] = {}
    for name, spec in (manifest.get("files") or {}).items():
        path = root / str(spec["path"])
        if not path.is_file():
            findings.append(f"missing_file:{name}")
            continue
        rows = load_jsonl(path)
        actual = sha256(path)
        check = {
            "rows": len(rows),
            "rows_expected": spec.get("rows"),
            "sha256_expected": spec.get("sha256"),
            "sha256_actual": actual,
            "hash_match": actual == spec.get("sha256"),
        }
        file_checks[name] = check
        if len(rows) != spec.get("rows"):
            findings.append(f"row_count:{name}")
        if actual != spec.get("sha256"):
            findings.append(f"hash_mismatch:{name}")

    train_spec = (manifest.get("files") or {}).get("train") or {}
    train_path = root / str(train_spec.get("path") or "train_256.jsonl")
    train = load_jsonl(train_path)
    expected_train_rows = int(train_spec.get("rows") or manifest.get("train_rows") or 0)
    if len(train) != expected_train_rows:
        findings.append(f"train_count:{len(train)}:{expected_train_rows}")
    if any(
        row.get("optimizer_eligible") is not True
        or row.get("hold_only") is not False
        or row.get("response_only_loss_allowed") is not True
        or row.get("training_authorized") is not False
        or row.get("run_authorized") is not False
        for row in train
    ):
        findings.append("train_contract_or_authority")
    train_keys = {(row.get("pair_id"), row.get("ask"), row.get("target")) for row in train}
    eval_keys: set[tuple[object, object, object]] = set()
    eval_summary: dict[str, dict] = {}
    for name, (expected_rows, expected_status) in EXPECTED_EVAL.items():
        rows = load_jsonl(root / f"{name}.jsonl")
        statuses = [judge(row["target"], axis=row["axis"], ask=row["ask"], use_cpu_sensor=False)["status"] for row in rows]
        eval_summary[name] = {
            "rows": len(rows),
            "expected_rows": expected_rows,
            "expected_status": expected_status,
            "status_counts": {status: statuses.count(status) for status in sorted(set(statuses))},
            "hold_only": all(row.get("hold_only") is True and row.get("optimizer_eligible") is False for row in rows),
        }
        if len(rows) != expected_rows or any(status != expected_status for status in statuses):
            findings.append(f"eval_contract:{name}")
        if not eval_summary[name]["hold_only"]:
            findings.append(f"eval_authority:{name}")
        for row in rows:
            key = (row.get("pair_id"), row.get("ask"), row.get("target"))
            if key in train_keys or key in eval_keys:
                findings.append(f"overlap:{name}:{row.get('pair_id')}")
            eval_keys.add(key)

    source = manifest.get("source_train_candidate") or {}
    source_path = Path(str(source.get("path")))
    if not source_path.is_file() or sha256(source_path) != source.get("sha256"):
        findings.append("source_train_hash")
    refinement = manifest.get("source_train_refinement")
    if refinement is not None:
        refinement_path = Path(str(refinement.get("path")))
        if not refinement_path.is_file() or sha256(refinement_path) != refinement.get("sha256"):
            findings.append("source_train_refinement_hash")
    parent = FOUNDATION / "models/Training/runs/openaster_stage1_gen_smoke_16_20260730T004859Z/adapter/adapter_model.safetensors"
    if not parent.is_file():
        findings.append("parent_adapter_missing")
    report = {
        "schema_version": "mouth_training_recovery_v3_named_preflight_v1",
        "status": "PREFLIGHT_PASS_TRAINING_CLOSED" if not findings else "PREFLIGHT_FAIL",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "campaign_root": str(root).replace("\\", "/"),
        "source_root": str(source_root).replace("\\", "/"),
        "manifest_sha256": sha256(root / "manifest.json"),
        "findings": findings,
        "files": file_checks,
        "eval": eval_summary,
        "eval_unique_keys": len(eval_keys),
        "parent_adapter": str(parent).replace("\\", "/"),
        "train_rows": len(train),
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "model_loaded": False,
        "next_action": "separate_execution_authorization" if not findings else "repair_preflight_findings",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not findings, "status": report["status"], "findings": findings, "report": str(report_path)}))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
