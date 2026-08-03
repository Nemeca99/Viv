#!/usr/bin/env python3
"""Governed canary runner for the closed per-tag prompt campaign.

The runner consumes the canonical tagged prompt rows, masks prompt tokens, and
delegates optimizer/checkpoint mechanics to the existing single-lease trainer.
It has no implicit authorization and never changes the live adapter.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
import time
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib import training_security  # noqa: E402
from voice_core.acronym_registry import APPROVED_ACRONYMS  # noqa: E402
from models.Training.code import train_mouth_v3_targeted_patch as trainer  # noqa: E402

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
LOCAL_BASE = trainer.LOCAL_BASE
DEFAULT_STEPS = 4
CHECKPOINT_LADDER = (2, 4, 8, 16, 32, 64, 96, 128)
DEFAULT_LR = 1.0e-5
GRADIENT_ACCUMULATION = 1
SEQUENCE_CAP = 384
TRAINING_SOFT_FLOOR = 0.25
TARGET_MODULES = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj", "lm_head")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def campaign_root(campaign_id: str) -> Path:
    return CAMPAIGNS / campaign_id


def checkpoints_for_steps(steps: int) -> tuple[int, ...]:
    return tuple(step for step in CHECKPOINT_LADDER if step <= steps)


def resolve_trainable_target_modules(manifest: dict[str, Any]) -> list[str] | None:
    """Resolve an explicit, manifest-bound LoRA scope.

    ``None`` preserves the historical all-target behavior.  A non-empty list
    is a governed restriction used by interface experiments such as lm_head
    continuation; it cannot be supplied only at execution time.
    """
    options = manifest.get("training_options") or {}
    requested = options.get("trainable_target_modules")
    if requested is None:
        return None
    if not isinstance(requested, list) or not requested or any(item not in TARGET_MODULES for item in requested):
        raise ValueError("training_target_module_scope_invalid")
    return list(dict.fromkeys(str(item) for item in requested))


def resolve_top1_options(manifest: dict[str, Any]) -> tuple[float, float]:
    options = manifest.get("training_options") or {}
    weight = float(options.get("top1_margin_weight") or 0.0)
    margin = float(options.get("top1_margin") if options.get("top1_margin") is not None else 0.2)
    if weight < 0.0 or margin < 0.0:
        raise ValueError("top1_margin_options_invalid")
    return weight, margin


def choose_gradient_accumulation(row_count: int, steps: int, requested: int = 0) -> int:
    """Cover the admitted training corpus during a bounded canary.

    The old fixed value of one meant a 36-row corpus touched only four or
    sixteen rows in short canaries. Automatic accumulation keeps the canary
    step count comparable while ensuring every admitted row contributes at
    least once per optimizer cycle.
    """
    if row_count <= 0 or steps <= 0:
        raise ValueError("gradient_coverage_inputs_invalid")
    if requested < 0:
        raise ValueError("gradient_accumulation_must_be_nonnegative")
    return requested if requested else max(1, (row_count + steps - 1) // steps)


def training_rid_preflight() -> dict[str, Any]:
    """Fail closed before authorization or GPU work when live RID is unusable."""
    try:
        # Use the exact Python authority source used by BEGIN_RUN/COMMIT_RUN;
        # the display feed is evidence but is not the lease's measurement.
        from lib.training_security import fresh_master_s_n

        s_n, evidence = fresh_master_s_n()
        if s_n < TRAINING_SOFT_FLOOR:
            return {"allowed": False, "reason": "master_s_n_below_training_soft_floor", "master_s_n": s_n, "training_soft_floor": TRAINING_SOFT_FLOOR, "authority": evidence}
        return {"allowed": True, "master_s_n": s_n, "training_soft_floor": TRAINING_SOFT_FLOOR, "authority": evidence}
    except Exception as exc:  # fail closed
        return {"allowed": False, "reason": f"live_rid_preflight_error:{type(exc).__name__}:{exc}"}


def wait_for_commit_stability(timeout_s: float = 30.0, poll_s: float = 1.0) -> dict[str, Any]:
    """Wait briefly for post-training load to settle, still failing closed."""
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {"allowed": False, "reason": "stability_wait_not_started"}
    while time.monotonic() < deadline:
        last = training_rid_preflight()
        if last.get("allowed"):
            return {"allowed": True, "waited_s": round(timeout_s - max(0.0, deadline - time.monotonic()), 3), "evidence": last}
        time.sleep(poll_s)
    return {"allowed": False, "waited_s": round(timeout_s, 3), "evidence": last}


def validate_closed(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    findings: list[str] = []
    for key in ("training_authorized", "run_authorized", "lease_opened", "gpu_steps"):
        expected = False if key != "gpu_steps" else 0
        if manifest.get(key) != expected:
            findings.append(f"authority:{key}")
    for name, spec in (manifest.get("files") or {}).items():
        path = root / str(spec["path"])
        if not path.is_file() or sha256(path) != spec.get("sha256"):
            findings.append(f"file_hash:{name}")
    train = load_jsonl(root / "train.jsonl")
    expected_train_rows = int((manifest.get("rows") or {}).get("train") or 0)
    if len(train) != expected_train_rows:
        findings.append(f"train_rows:{len(train)}")
    if any(row.get("split") != "train" or row.get("optimizer_eligible") is not True or row.get("response_only_loss_allowed") is not True or row.get("hold_only") is not False for row in train):
        findings.append("train_contract")
    parent = Path(str((manifest.get("parent_adapter") or {}).get("path") or ""))
    if not parent.is_file() or sha256(parent) != (manifest.get("parent_adapter") or {}).get("sha256"):
        findings.append("parent_hash")
    preflight = root / "PREFLIGHT_READ_ONLY.json"
    preflight_data = json.loads(preflight.read_text(encoding="utf-8")) if preflight.is_file() else {}
    if preflight_data.get("status") != "PREFLIGHT_PASS_TRAINING_CLOSED" or preflight_data.get("manifest_sha256") != sha256(root / "manifest.json"):
        findings.append("preflight_missing_or_stale")
    if findings:
        raise ValueError(json.dumps({"status": "VALIDATION_FAIL", "findings": findings}, sort_keys=True))
    return {"manifest": manifest, "train": train, "parent": parent}


def encode_rows(rows: list[dict[str, Any]], tokenizer: Any, contract_token_weight: float = 1.0) -> list[dict[str, Any]]:
    eos_id = tokenizer.convert_tokens_to_ids(trainer.OPENASTER_EOS_TOKEN)
    encoded: list[dict[str, Any]] = []
    for row in rows:
        prompt_ids = tokenizer(row["prompt"], add_special_tokens=False)["input_ids"]
        response_text = str(row["response"])
        response_encoded = tokenizer(response_text, add_special_tokens=False, return_offsets_mapping=True)
        response_ids = list(response_encoded["input_ids"])
        offsets = list(response_encoded.get("offset_mapping") or [])
        response_weights = [1.0] * len(response_ids)
        if contract_token_weight > 1.0 and offsets:
            spans: list[tuple[int, int]] = []
            for spec in APPROVED_ACRONYMS.values():
                match = re.search(re.escape(f"{spec.expansion} ({spec.acronym})"), response_text)
                if match:
                    spans.append(match.span())
            for index, (start, end) in enumerate(offsets):
                if any(start < span_end and end > span_start for span_start, span_end in spans):
                    response_weights[index] = float(contract_token_weight)
        response_ids.append(eos_id)
        response_weights.append(1.0)
        full = prompt_ids + response_ids
        if len(prompt_ids) >= SEQUENCE_CAP or len(full) > SEQUENCE_CAP:
            raise ValueError(f"tag_row_sequence_overflow:{row['example_id']}:{len(prompt_ids)}:{len(full)}")
        item = {"pair_id": row["pair_hash"], "input_ids": full, "labels": [-100] * len(prompt_ids) + response_ids, "loss_weights": [1.0] * len(prompt_ids) + response_weights, "prompt_tokens": len(prompt_ids), "response_tokens": len(response_ids), "prompt_sha256": row["prompt_sha256"]}
        negative_text = row.get("negative_response")
        if negative_text:
            negative_ids = list(tokenizer(str(negative_text), add_special_tokens=False)["input_ids"]) + [eos_id]
            negative_full = prompt_ids + negative_ids
            if len(negative_full) > SEQUENCE_CAP:
                raise ValueError(f"tag_negative_sequence_overflow:{row['example_id']}:{len(negative_full)}")
            item["negative_input_ids"] = negative_full
            item["negative_labels"] = [-100] * len(prompt_ids) + negative_ids
        encoded.append(item)
    return encoded


def authorize_once(root: Path, steps: int, lr: float, anchor_strength: float, requested_accumulation: int = 0, contract_token_weight: float = 1.0, contrastive_weight: float = 0.0, contrastive_margin: float = 0.0, pairwise_weight: float = 0.0, pairwise_beta: float = 1.0, pairwise_margin: float = 0.2, top1_margin_weight: float = 0.0, top1_margin: float = 0.2) -> dict[str, Any]:
    if anchor_strength < 0.0:
        raise ValueError("anchor_strength_must_be_nonnegative")
    rid_preflight = training_rid_preflight()
    if not rid_preflight.get("allowed"):
        raise PermissionError(json.dumps({"status": "TRAINING_RID_PREFLIGHT_DENIED", "evidence": rid_preflight}, sort_keys=True))
    state = validate_closed(root)
    target_modules = resolve_trainable_target_modules(state["manifest"])
    manifest_top1_weight, manifest_top1_margin = resolve_top1_options(state["manifest"])
    if float(top1_margin_weight) != manifest_top1_weight or float(top1_margin) != manifest_top1_margin:
        raise PermissionError("top1_margin_scope_mismatch")
    accumulation = choose_gradient_accumulation(len(state["train"]), steps, requested_accumulation)
    manifest_path = root / "manifest.json"
    receipt = root / "TAG_NAMED_AUTHORIZATION.json"
    if receipt.exists():
        raise FileExistsError(f"authorization_exists:{receipt}")
    updated = dict(state["manifest"])
    before = sha256(manifest_path)
    if contract_token_weight < 1.0:
        raise ValueError("contract_token_weight_must_be_at_least_one")
    if contrastive_weight < 0.0 or contrastive_margin < 0.0:
        raise ValueError("contrastive_parameters_must_be_nonnegative")
    if pairwise_weight < 0.0 or pairwise_beta <= 0.0 or pairwise_margin < 0.0:
        raise ValueError("pairwise_parameters_invalid")
    updated.update({"status": "CAMPAIGN_EXECUTION_AUTHORIZED", "training_authorized": True, "run_authorized": True, "authorization_scope": {"campaign_id": root.name, "optimizer_steps": steps, "learning_rate": lr, "anchor_strength": anchor_strength, "contract_token_weight": contract_token_weight, "contrastive_weight": contrastive_weight, "contrastive_margin": contrastive_margin, "pairwise_weight": pairwise_weight, "pairwise_beta": pairwise_beta, "pairwise_margin": pairwise_margin, "gradient_accumulation": accumulation, "coverage_rows": len(state["train"]), "checkpoint_steps": list(checkpoints_for_steps(steps)), "trainable_target_modules": target_modules, "top1_margin_weight": manifest_top1_weight, "top1_margin": manifest_top1_margin, "promotion_authorized": False, "deployment_authorized": False}, "next_action": "execute_named_canary_once"})
    manifest_path.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    record = {"schema_version": "tag_named_authorization_v1", "campaign_id": root.name, "manifest_before_sha256": before, "manifest_after_sha256": sha256(manifest_path), "preflight_path": str(root / "PREFLIGHT_READ_ONLY.json").replace("\\", "/"), "training_authorized": True, "run_authorized": True, "optimizer_steps": steps, "learning_rate": lr, "anchor_strength": anchor_strength, "contract_token_weight": contract_token_weight, "contrastive_weight": contrastive_weight, "contrastive_margin": contrastive_margin, "pairwise_weight": pairwise_weight, "pairwise_beta": pairwise_beta, "pairwise_margin": pairwise_margin, "gradient_accumulation": accumulation, "coverage_rows": len(state["train"]), "checkpoint_steps": list(checkpoints_for_steps(steps)), "trainable_target_modules": target_modules, "top1_margin_weight": manifest_top1_weight, "top1_margin": manifest_top1_margin, "promotion_authorized": False, "deployment_authorized": False, "rid_preflight": rid_preflight, "recorded_utc": utc()}
    receipt.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return record


def run_once(root: Path, steps: int, lr: float, anchor_strength: float, requested_accumulation: int = 0, contract_token_weight: float = 1.0, contrastive_weight: float = 0.0, contrastive_margin: float = 0.0, pairwise_weight: float = 0.0, pairwise_beta: float = 1.0, pairwise_margin: float = 0.2, top1_margin_weight: float = 0.0, top1_margin: float = 0.2) -> dict[str, Any]:
    if anchor_strength < 0.0:
        raise ValueError("anchor_strength_must_be_nonnegative")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("training_authorized") is not True or manifest.get("run_authorized") is not True:
        raise PermissionError("named_authorization_required")
    train_path = root / "train.jsonl"
    train_rows = load_jsonl(train_path)
    accumulation = choose_gradient_accumulation(len(train_rows), steps, requested_accumulation)
    authorized_scope = manifest.get("authorization_scope") or {}
    target_modules = resolve_trainable_target_modules(manifest)
    if float(authorized_scope.get("top1_margin_weight") or 0.0) != float(top1_margin_weight) or float(authorized_scope.get("top1_margin") if authorized_scope.get("top1_margin") is not None else 0.2) != float(top1_margin):
        raise PermissionError("top1_margin_scope_mismatch")
    if authorized_scope.get("trainable_target_modules") != target_modules:
        raise PermissionError("trainable_target_module_scope_mismatch")
    if int(authorized_scope.get("gradient_accumulation") or 0) != accumulation:
        raise PermissionError("gradient_coverage_scope_mismatch")
    if float(authorized_scope.get("contract_token_weight") or 1.0) != float(contract_token_weight):
        raise PermissionError("contract_token_weight_scope_mismatch")
    if float(authorized_scope.get("contrastive_weight") or 0.0) != float(contrastive_weight) or float(authorized_scope.get("contrastive_margin") or 0.0) != float(contrastive_margin):
        raise PermissionError("contrastive_scope_mismatch")
    if float(authorized_scope.get("pairwise_weight") or 0.0) != float(pairwise_weight) or float(authorized_scope.get("pairwise_beta") or 1.0) != float(pairwise_beta) or float(authorized_scope.get("pairwise_margin") or 0.2) != float(pairwise_margin):
        raise PermissionError("pairwise_scope_mismatch")
    parent_file = Path(str((manifest.get("parent_adapter") or {}).get("path") or ""))
    parent_dir = parent_file.parent
    run_id = f"{root.name}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    rid_preflight = training_rid_preflight()
    if not rid_preflight.get("allowed"):
        return {"ok": False, "run_id": run_id, "lease_opened": False, "gpu_steps": 0, "training_authorized": True, "run_authorized": True, "deployment_changed": False, "error": "TRAINING_RID_PREFLIGHT_DENIED", "rid_preflight": rid_preflight, "quarantined": False}
    lease = training_security.begin_run_lease(stage_id=root.name, run_id=run_id, manifest_sha256=sha256(root / "manifest.json"), source_hashes=(sha256(train_path), sha256(parent_file)), max_duration_s=2 * 60 * 60, max_disk_mib=4096, lora_rank=16, sequence_cap=SEQUENCE_CAP)
    result: dict[str, Any] = {"ok": False, "run_id": run_id, "lease_opened": True, "gpu_steps": 0, "training_authorized": True, "run_authorized": True, "deployment_changed": False, "trainable_target_modules": target_modules, "top1_margin_weight": top1_margin_weight, "top1_margin": top1_margin}
    prepared: dict[str, Any] | None = None
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoTokenizer

        # Keep CPU-side tokenizer/data orchestration bounded; GPU training is
        # still governed by the lease and Law 5 commit check.
        try:
            torch.set_num_threads(1)
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass

        tokenizer = AutoTokenizer.from_pretrained(str(LOCAL_BASE), trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        rows = train_rows
        encoded = encode_rows(rows, tokenizer, contract_token_weight)
        base = trainer.load_local_qwen_causal_lm(torch=torch).to("cuda")
        base.config.use_cache = False
        model = PeftModel.from_pretrained(base, str(parent_dir), is_trainable=True)
        if target_modules is not None:
            for name, parameter in model.named_parameters():
                parameter.requires_grad = any(
                    f".{target}." in name or name.endswith(f".{target}")
                    for target in target_modules
                )
            if not any(parameter.requires_grad for parameter in model.parameters()):
                raise ValueError("trainable_target_module_scope_empty")
        model.enable_input_require_grads()
        model.gradient_checkpointing_enable()
        model.train()
        optimizer = torch.optim.AdamW([parameter for parameter in model.parameters() if parameter.requires_grad], lr=lr, weight_decay=0.0)
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda step: max(0.0, 1.0 - min(1.0, step / max(1, steps))))
        anchor_state = {name: parameter.detach().clone() for name, parameter in model.named_parameters() if parameter.requires_grad} if anchor_strength > 0.0 else {}
        prepared = {"tokenizer": tokenizer, "model": model, "optimizer": optimizer, "scheduler": scheduler, "anchor_state": anchor_state, "anchor_strength": anchor_strength, "contract_token_weight": contract_token_weight, "contrastive_weight": contrastive_weight, "contrastive_margin": contrastive_margin, "pairwise_weight": pairwise_weight, "pairwise_beta": pairwise_beta, "pairwise_margin": pairwise_margin, "top1_margin_weight": top1_margin_weight, "top1_margin": top1_margin, "encoded": encoded, "train_rows": rows, "learning_rate": lr, "gradient_accumulation": accumulation, "parent_adapter": str(parent_dir).replace("\\", "/"), "train_jsonl_sha256": sha256(train_path), "trainable_target_modules": target_modules, "forward_executed": False, "backward_executed": False, "optimizer_steps_executed": 0}
        trained = trainer.train_under_external_lease(lease=lease, prepared=prepared, max_steps=steps, checkpoint_steps=checkpoints_for_steps(steps), gradient_accumulation=accumulation, seed=42, commit=False)
        trained["gradient_accumulation"] = accumulation
        trained["coverage_rows"] = len(rows)
        result.update(trained)
        prepared["model"] = None
        prepared["optimizer"] = None
        prepared["scheduler"] = None
        del prepared
        gc.collect()
        torch.cuda.empty_cache()
        commit_wait = wait_for_commit_stability()
        result["commit_stability_wait"] = commit_wait
        if not commit_wait.get("allowed"):
            quarantine = lease.quarantine("training_rid_unstable_after_steps", json.dumps(commit_wait, sort_keys=True))
            result.update({"ok": False, "gpu_steps": steps, "quarantined": True, "security_commit": quarantine, "error": "TRAINING_RID_UNSTABLE_AFTER_STEPS"})
            return result
        commit = lease.commit()
        result["security_commit"] = commit
        result["ok"] = bool(trained.get("ok")) and bool(commit.get("allowed"))
        result["gpu_steps"] = steps if result["ok"] else int(trained.get("optimizer_steps", 0))
        if result["ok"]:
            # The Rust lease commit already publishes lease.final_root. Do not
            # copy it onto itself; record the committed root as the artifact.
            result["published_run"] = str(lease.final_root).replace("\\", "/")
        return result
    except Exception as exc:
        try:
            lease.quarantine("tag_campaign_failure", f"{type(exc).__name__}:{exc}")
        except Exception:
            pass
        result.update({"error": f"{type(exc).__name__}:{exc}", "quarantined": True})
        return result


def close_campaign(root: Path, result: dict[str, Any]) -> None:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "status": (
                "CAMPAIGN_EXECUTED_NO_PROMOTION"
                if result.get("ok")
                else "CAMPAIGN_EXECUTED_QUARANTINED"
            ),
            "training_authorized": False,
            "run_authorized": False,
            "lease_opened": False,
            "gpu_steps": int(result.get("gpu_steps") or 0),
            "promotion_allowed": False,
            "deployment_changed": False,
            "next_action": "evaluate_and_retain_or_reject_no_promotion",
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    path = root / "EXECUTION_REPORT.json"
    path.write_text(json.dumps({"schema_version": "tag_campaign_execution_report_v1", "recorded_utc": utc(), "campaign_id": root.name, "result": result, "promotion_allowed": False, "deployment_changed": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    parser.add_argument("--lr", type=float, default=DEFAULT_LR)
    parser.add_argument("--anchor-strength", type=float, default=0.0)
    parser.add_argument("--contract-token-weight", type=float, default=1.0)
    parser.add_argument("--contrastive-weight", type=float, default=0.0)
    parser.add_argument("--contrastive-margin", type=float, default=0.0)
    parser.add_argument("--pairwise-weight", type=float, default=0.0)
    parser.add_argument("--pairwise-beta", type=float, default=1.0)
    parser.add_argument("--pairwise-margin", type=float, default=0.2)
    parser.add_argument("--top1-margin-weight", type=float, default=0.0)
    parser.add_argument("--top1-margin", type=float, default=0.2)
    parser.add_argument("--gradient-accumulation", type=int, default=0, help="0 selects automatic full-corpus coverage")
    args = parser.parse_args()
    root = campaign_root(args.campaign_id)
    if args.steps <= 0 or args.steps > 128:
        raise ValueError("canary_steps_must_be_1_to_128")
    if args.authorize:
        print(json.dumps(authorize_once(root, args.steps, args.lr, args.anchor_strength, args.gradient_accumulation, args.contract_token_weight, args.contrastive_weight, args.contrastive_margin, args.pairwise_weight, args.pairwise_beta, args.pairwise_margin, args.top1_margin_weight, args.top1_margin), indent=2, sort_keys=True))
    if args.execute:
        result = run_once(root, args.steps, args.lr, args.anchor_strength, args.gradient_accumulation, args.contract_token_weight, args.contrastive_weight, args.contrastive_margin, args.pairwise_weight, args.pairwise_beta, args.pairwise_margin, args.top1_margin_weight, args.top1_margin)
        close_campaign(root, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
