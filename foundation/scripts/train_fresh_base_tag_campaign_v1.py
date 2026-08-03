#!/usr/bin/env python3
"""Governed fresh-base tag canary; no promotion or deployment authority."""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib import training_security  # noqa: E402
from models.Training.code import train_mouth_v3_targeted_patch as trainer  # noqa: E402
from scripts import train_tag_prompt_campaign_v1 as tagged  # noqa: E402

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
CHECKPOINTS = (2, 4, 8, 16)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def root_for(cid: str) -> Path:
    return CAMPAIGNS / cid


def validate(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("parent_mode") != "fresh_base" or manifest.get("parent_adapter") is not None:
        raise ValueError("fresh_base_manifest_required")
    for key in ("training_authorized", "run_authorized", "lease_opened", "gpu_steps"):
        expected = 0 if key == "gpu_steps" else False
        if manifest.get(key) != expected:
            raise ValueError(f"closed_authority_required:{key}")
    base = Path(str((manifest.get("base_model_config") or {}).get("path") or ""))
    if not base.is_file() or sha256(base) != (manifest.get("base_model_config") or {}).get("sha256"):
        raise ValueError("base_config_hash")
    for split in ("train", "development", "holdout"):
        spec = manifest["files"][split]
        path = root / spec["path"]
        if not path.is_file() or sha256(path) != spec["sha256"]:
            raise ValueError(f"file_hash:{split}")
    preflight = json.loads((root / "PREFLIGHT_READ_ONLY.json").read_text(encoding="utf-8"))
    if preflight.get("status") != "PREFLIGHT_PASS_TRAINING_CLOSED" or preflight.get("manifest_sha256") != sha256(root / "manifest.json"):
        raise ValueError("preflight_stale")
    return manifest


def authorize(root: Path, steps: int, lr: float) -> dict:
    if not tagged.training_rid_preflight().get("allowed"):
        raise PermissionError("TRAINING_RID_PREFLIGHT_DENIED")
    manifest = validate(root)
    path = root / "manifest.json"
    before = sha256(path)
    updated = dict(manifest)
    updated.update({"status": "CAMPAIGN_EXECUTION_AUTHORIZED", "training_authorized": True, "run_authorized": True, "authorization_scope": {"campaign_id": root.name, "parent_mode": "fresh_base", "optimizer_steps": steps, "learning_rate": lr, "checkpoint_steps": [s for s in CHECKPOINTS if s <= steps], "promotion_authorized": False, "deployment_authorized": False}})
    path.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    receipt = {"schema_version": "aios_fresh_base_named_authorization_v1", "campaign_id": root.name, "manifest_before_sha256": before, "manifest_after_sha256": sha256(path), "parent_mode": "fresh_base", "training_authorized": True, "run_authorized": True, "optimizer_steps": steps, "learning_rate": lr, "promotion_authorized": False, "deployment_authorized": False, "recorded_utc": utc()}
    (root / "TAG_NAMED_AUTHORIZATION.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return receipt


def run(root: Path, steps: int, lr: float) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("training_authorized") is not True or manifest.get("run_authorized") is not True:
        raise PermissionError("named_authorization_required")
    train_path = root / manifest["files"]["train"]["path"]
    run_id = f"{root.name}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    rid = tagged.training_rid_preflight()
    if not rid.get("allowed"):
        return {"ok": False, "run_id": run_id, "lease_opened": False, "gpu_steps": 0, "error": "TRAINING_RID_PREFLIGHT_DENIED", "rid_preflight": rid, "deployment_changed": False}
    lease_manifest = hashlib.sha256(json.dumps({"campaign": root.name, "train": sha256(train_path), "base": manifest["base_model_config"]["sha256"], "steps": steps, "lr": lr}, sort_keys=True).encode()).hexdigest()
    lease = training_security.begin_run_lease(stage_id=root.name, run_id=run_id, manifest_sha256=lease_manifest, source_hashes=(sha256(train_path), manifest["base_model_config"]["sha256"]), max_duration_s=2 * 60 * 60, max_disk_mib=4096, lora_rank=16, sequence_cap=384)
    result = {"ok": False, "run_id": run_id, "lease_opened": True, "gpu_steps": 0, "deployment_changed": False, "parent_mode": "fresh_base"}
    prepared = None
    try:
        import torch
        from peft import LoraConfig, get_peft_model
        from transformers import AutoTokenizer
        try:
            torch.set_num_threads(1)
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
        tokenizer = AutoTokenizer.from_pretrained(str(trainer.LOCAL_BASE), trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        rows = [json.loads(line) for line in train_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        encoded = tagged.encode_rows(rows, tokenizer)
        base = trainer.load_local_qwen_causal_lm(torch=torch).to("cuda")
        base.config.use_cache = False
        model = get_peft_model(base, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM", target_modules=list(trainer.LORA_TARGETS), ensure_weight_tying=True))
        model.enable_input_require_grads()
        model.gradient_checkpointing_enable()
        model.train()
        optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=0.0)
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda step: max(0.0, 1.0 - min(1.0, step / max(1, steps))))
        prepared = {"tokenizer": tokenizer, "model": model, "optimizer": optimizer, "scheduler": scheduler, "anchor_state": {}, "anchor_strength": 0.0, "encoded": encoded, "train_rows": rows, "learning_rate": lr, "gradient_accumulation": 1, "parent_adapter": None, "train_jsonl_sha256": sha256(train_path), "forward_executed": False, "backward_executed": False, "optimizer_steps_executed": 0}
        trained = trainer.train_under_external_lease(lease=lease, prepared=prepared, max_steps=steps, checkpoint_steps=tuple(s for s in CHECKPOINTS if s <= steps), gradient_accumulation=1, seed=42, commit=False)
        result.update(trained)
        prepared["model"] = None; prepared["optimizer"] = None; prepared["scheduler"] = None
        del prepared; prepared = None; gc.collect(); torch.cuda.empty_cache()
        if not result.get("ok"):
            lease.quarantine("fresh_base_training_failed", str(result.get("error") or "unknown"))
            return result
        commit = lease.commit()
        result["security_commit"] = commit
        result["ok"] = bool(commit.get("allowed"))
        result["gpu_steps"] = steps if result["ok"] else int(result.get("optimizer_steps", 0))
        if result["ok"]:
            result["published_run"] = str(lease.final_root).replace("\\", "/")
        return result
    except Exception as exc:
        try:
            lease.quarantine("fresh_base_campaign_failure", f"{type(exc).__name__}:{exc}")
        except Exception:
            pass
        return {**result, "error": f"{type(exc).__name__}:{exc}", "quarantined": True}


def close_manifest(root: Path, result: dict) -> None:
    """Close execution authority while retaining the immutable run evidence."""
    path = root / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update({
        "status": "CAMPAIGN_EXECUTED_NO_PROMOTION" if result.get("ok") else "CAMPAIGN_EXECUTED_QUARANTINED",
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": int(result.get("gpu_steps") or 0),
        "promotion_allowed": False,
        "deployment_changed": False,
        "next_action": "evaluate_and_retain_or_reject_no_promotion",
    })
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--steps", type=int, default=2)
    parser.add_argument("--lr", type=float, default=1e-6)
    args = parser.parse_args()
    if args.steps < 1 or args.steps > 16:
        raise ValueError("fresh_base_canary_steps_must_be_1_to_16")
    root = root_for(args.campaign_id)
    if args.authorize:
        print(json.dumps(authorize(root, args.steps, args.lr), indent=2, sort_keys=True))
    if args.execute:
        result = run(root, args.steps, args.lr)
        close_manifest(root, result)
        (root / "EXECUTION_REPORT.json").write_text(json.dumps({"schema_version": "aios_fresh_base_execution_report_v1", "recorded_utc": utc(), "campaign_id": root.name, "result": result, "promotion_allowed": False, "deployment_changed": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
