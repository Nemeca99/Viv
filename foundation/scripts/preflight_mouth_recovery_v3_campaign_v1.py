#!/usr/bin/env python3
"""Read-only preflight for the closed V3 recovery campaign.

Checks manifest/file integrity, corpus separation, canonical evaluator status,
and the preserved tokenizer/masking audit.  It deliberately does not import a
trainer, load a model, open a lease, or change authorization state.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import FAIL, PASS, judge

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
ROOT = TREE / "mouth_training_recovery_v3_campaign_v1"
SOURCE_ROOT = TREE / "mouth_training_recovery_v3_semantic_projection_v1"
REPORT = ROOT / "PREFLIGHT_READ_ONLY.json"
EXPECTED_EVAL = {"development": (64, PASS), "blind": (32, PASS), "legacy": (64, PASS), "auditor_negative": (20, FAIL)}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    if REPORT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{REPORT}")
    findings: list[str] = []
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "CAMPAIGN_ADMITTED_TRAINING_CLOSED":
        findings.append("manifest_status")
    for key in ("training_authorized", "run_authorized", "lora_authorized", "dpo_authorized"):
        if manifest.get(key) is not False:
            findings.append(f"manifest_{key}")
    if manifest.get("lease_opened") is not False or manifest.get("gpu_steps") != 0:
        findings.append("manifest_execution_state")

    file_checks: dict[str, dict] = {}
    for name, spec in manifest.get("files", {}).items():
        path = ROOT / str(spec["path"])
        if not path.is_file():
            findings.append(f"missing_file:{name}")
            continue
        actual = sha256(path)
        file_checks[name] = {"rows": spec.get("rows"), "sha256_expected": spec.get("sha256"), "sha256_actual": actual, "hash_match": actual == spec.get("sha256")}
        if actual != spec.get("sha256"):
            findings.append(f"hash_mismatch:{name}")

    train = load_jsonl(ROOT / "train_256.jsonl")
    if len(train) != 256:
        findings.append(f"train_count:{len(train)}")
    if any(row.get("optimizer_eligible") is not True or row.get("hold_only") is not False or row.get("response_only_loss_allowed") is not True for row in train):
        findings.append("train_contract")
    if any(row.get("training_authorized") is not False or row.get("run_authorized") is not False for row in train):
        findings.append("train_authority")
    train_statuses = [judge(row["target"], axis=row["axis"], ask=row["ask"], use_cpu_sensor=False)["status"] for row in train]
    if any(status != PASS for status in train_statuses):
        findings.append("train_canonical_judge")

    eval_summary: dict[str, dict] = {}
    eval_keys: set[tuple[str, str, str]] = set()
    train_keys = {(row["pair_id"], row["ask"], row["target"]) for row in train}
    for name, (expected_count, expected_status) in EXPECTED_EVAL.items():
        rows = load_jsonl(ROOT / f"{name}.jsonl")
        statuses = [judge(row["target"], axis=row["axis"], ask=row["ask"], use_cpu_sensor=False)["status"] for row in rows]
        eval_summary[name] = {"rows": len(rows), "expected_rows": expected_count, "expected_status": expected_status, "statuses": {s: statuses.count(s) for s in sorted(set(statuses))}, "hold_only": all(row.get("hold_only") is True and row.get("optimizer_eligible") is False for row in rows)}
        if len(rows) != expected_count or any(status != expected_status for status in statuses):
            findings.append(f"eval_contract:{name}")
        if not eval_summary[name]["hold_only"]:
            findings.append(f"eval_authority:{name}")
        for row in rows:
            key = (row["pair_id"], row["ask"], row["target"])
            if key in train_keys or key in eval_keys:
                findings.append(f"overlap:{name}:{row['pair_id']}")
            eval_keys.add(key)

    token_audit = json.loads((SOURCE_ROOT / "TOKENIZATION_AUDIT.json").read_text(encoding="utf-8"))
    if token_audit.get("status") != "TOKENIZATION_AND_MASKING_PASS" or token_audit.get("rows") != 256 or token_audit.get("prompt_tokens_masked") is not True or token_audit.get("target_tokens_supervised") is not True:
        findings.append("source_tokenization_audit")
    trainer_audit = json.loads((SOURCE_ROOT / "TRAINER_CONTRACT_AUDIT.json").read_text(encoding="utf-8"))
    if trainer_audit.get("findings") != [] or trainer_audit.get("candidate", {}).get("rows") != 256:
        findings.append("source_trainer_audit")

    report = {
        "schema_version": "mouth_training_recovery_v3_campaign_preflight_v1",
        "status": "PREFLIGHT_PASS_TRAINING_CLOSED" if not findings else "PREFLIGHT_FAIL",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "campaign_root": str(ROOT).replace("\\", "/"),
        "findings": findings,
        "files": file_checks,
        "train": {"rows": len(train), "pass": train_statuses.count(PASS), "nonpass": len(train) - train_statuses.count(PASS)},
        "eval": eval_summary,
        "eval_unique_keys": len(eval_keys),
        "source_tokenization_audit": {"path": str(SOURCE_ROOT / "TOKENIZATION_AUDIT.json").replace("\\", "/"), "sha256": sha256(SOURCE_ROOT / "TOKENIZATION_AUDIT.json"), "status": token_audit.get("status")},
        "source_trainer_audit": {"path": str(SOURCE_ROOT / "TRAINER_CONTRACT_AUDIT.json").replace("\\", "/"), "sha256": sha256(SOURCE_ROOT / "TRAINER_CONTRACT_AUDIT.json"), "findings": trainer_audit.get("findings")},
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "model_loaded": False,
        "next_action": "separate_execution_authorization" if not findings else "repair_preflight_findings",
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not findings, "status": report["status"], "findings": findings, "report": str(REPORT)}))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
