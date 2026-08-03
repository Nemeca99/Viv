#!/usr/bin/env python3
"""Governed TRL/PEFT runner for a named V3 mouth campaign.

The campaign, lease, backup, Master S_n, commit, quarantine, promotion, and
deployment boundaries remain AIOS-owned.  This module replaces only the inner
optimizer with TRL/PEFT and consumes pretokenized ``completion_mask`` rows.
Default invocation is read-only validation; execution requires an already
authorized named campaign and never authorizes one implicitly.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib import training_security  # noqa: E402
from models.Training.code.train_pairwise_lora import LOCAL_BASE, OPENASTER_EOS_TOKEN, load_local_qwen_causal_lm  # noqa: E402
from scripts.execution_abort_report import write_abort_report  # noqa: E402
from scripts.mouth_training_recovery_v3_runner import (  # noqa: E402
    CHECKPOINT_STEPS,
    LEARNING_RATE,
    OPTIMIZER_STEPS,
    PARENT,
    SEED,
    WARMUP_RATIO,
    campaign_run_root,
    load_manifest,
    sha256,
    utc,
    validate_campaign,
)

GRADIENT_ACCUMULATION = 4
SEQUENCE_CAP = 384


def load_rows(root: Path) -> tuple[dict[str, Any], Path, list[dict[str, Any]]]:
    manifest = load_manifest(root)
    train_path = root / str((manifest.get("files", {}).get("train") or {}).get("path") or "train_256.jsonl")
    rows = [json.loads(line) for line in train_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = int((manifest.get("files", {}).get("train") or {}).get("rows") or manifest.get("train_rows") or 0)
    if len(rows) != expected:
        raise ValueError(f"train_count:{len(rows)}:{expected}")
    for row in rows:
        if row.get("split") != "train":
            raise ValueError(f"non_train_row:{row.get('pair_id')}")
        if row.get("optimizer_eligible") is not True or row.get("response_only_loss_allowed") is not True:
            raise ValueError(f"optimizer_contract:{row.get('pair_id')}")
    return manifest, train_path, rows


def build_pretokenized_dataset(rows: list[dict[str, Any]], tokenizer: Any, eos_id: int) -> Any:
    from datasets import Dataset

    examples = []
    for row in rows:
        prompt_ids = tokenizer(str(row["ask"]), add_special_tokens=False)["input_ids"]
        completion_ids = tokenizer(str(row.get("chosen") or row["target"]), add_special_tokens=False)["input_ids"] + [eos_id]
        if not completion_ids:
            raise ValueError(f"empty_completion:{row.get('pair_id')}")
        examples.append({
            "input_ids": prompt_ids + completion_ids,
            "completion_mask": [0] * len(prompt_ids) + [1] * len(completion_ids),
            "pair_id": row["pair_id"],
        })
    return Dataset.from_list(examples)


def run_experiment(*, root: Path, output_root: Path | None = None) -> dict[str, Any]:
    root = Path(root)
    manifest, train_path, rows = load_rows(root)
    campaign_id = str(manifest.get("campaign_id") or root.name)
    if manifest.get("training_authorized") is not True or manifest.get("run_authorized") is not True:
        raise PermissionError("named_campaign_authorization_required")
    if manifest.get("lora_authorized") is not False or manifest.get("dpo_authorized") is not False:
        raise PermissionError("unapproved_training_mode_authorized")
    validation = validate_campaign(root, allow_authorized=True)
    training_security.require_training_security()
    parent_weights = PARENT / "adapter_model.safetensors"
    run_id = f"{campaign_id}_trl_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    request_manifest = sha256(root / "manifest.json")
    lease = None
    committed = False
    trained: dict[str, Any] | None = None
    commit: dict[str, Any] | None = None
    failure: BaseException | None = None
    result: dict[str, Any] = {"ok": False, "run_id": run_id, "engine": "trl_peft", "lease_opened": False, "gpu_steps": 0}
    try:
        lease = training_security.begin_run_lease(
            stage_id=campaign_id,
            run_id=run_id,
            manifest_sha256=request_manifest,
            source_hashes=(sha256(train_path), sha256(parent_weights)),
            max_duration_s=4 * 60 * 60,
            max_disk_mib=8192,
            lora_rank=16,
            sequence_cap=SEQUENCE_CAP,
        )
        result["lease_opened"] = True

        import torch
        from peft import PeftModel
        from transformers import AutoTokenizer, TrainerCallback
        from trl import SFTConfig, SFTTrainer

        tokenizer = AutoTokenizer.from_pretrained(str(LOCAL_BASE), trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        eos_id = tokenizer.convert_tokens_to_ids(OPENASTER_EOS_TOKEN)
        if eos_id is None or eos_id == tokenizer.unk_token_id:
            raise ValueError("openaster_eos_missing")
        dataset = build_pretokenized_dataset(rows, tokenizer, eos_id)
        base = load_local_qwen_causal_lm(torch=torch).to("cuda")
        base.config.use_cache = False
        model = PeftModel.from_pretrained(base, str(PARENT), is_trainable=True)
        model.enable_input_require_grads()
        model.gradient_checkpointing_enable()

        final_root = Path(lease.final_root)
        staging_root = Path(lease.staging_root)
        trainer_root = staging_root / "trl_trainer"

        class AdapterCheckpointCallback(TrainerCallback):
            def on_save(self, args: Any, state: Any, control: Any, model: Any = None, **kwargs: Any) -> Any:
                step = int(state.global_step)
                if model is not None and step in CHECKPOINT_STEPS:
                    model.save_pretrained(final_root / f"adapter_step_{step}")
                return control

        trainer = SFTTrainer(
            model=model,
            args=SFTConfig(
                output_dir=str(trainer_root),
                max_steps=OPTIMIZER_STEPS,
                per_device_train_batch_size=1,
                gradient_accumulation_steps=GRADIENT_ACCUMULATION,
                learning_rate=LEARNING_RATE,
                warmup_ratio=WARMUP_RATIO,
                logging_steps=1,
                save_strategy="steps",
                save_steps=min(CHECKPOINT_STEPS),
                save_total_limit=None,
                report_to=[],
                completion_only_loss=True,
                dataset_kwargs={"skip_prepare_dataset": True},
                max_length=SEQUENCE_CAP,
                bf16=True,
                remove_unused_columns=False,
                seed=SEED,
            ),
            train_dataset=dataset,
            processing_class=tokenizer,
            callbacks=[AdapterCheckpointCallback()],
        )
        train_result = trainer.train()
        final_adapter = final_root / "adapter"
        trainer.save_model(str(final_adapter))
        trained = {
            "engine": "trl_peft",
            "global_step": int(trainer.state.global_step),
            "train_loss": float(train_result.training_loss),
            "train_rows": len(rows),
            "train_sha256": sha256(train_path),
            "adapter_final": str(final_adapter).replace("\\", "/"),
            "checkpoint_steps": {str(step): (final_root / f"adapter_step_{step}").is_dir() for step in CHECKPOINT_STEPS},
            "completion_only_loss": True,
            "automatic_chat_template_conversion": False,
        }
        if int(trainer.state.global_step) != OPTIMIZER_STEPS:
            raise RuntimeError(f"optimizer_steps:{trainer.state.global_step}:{OPTIMIZER_STEPS}")
        commit = lease.commit()
        if not commit.get("allowed"):
            raise PermissionError(f"security_commit_denied:{commit}")
        committed = True
        if output_root is not None:
            target_root = Path(output_root)
            target_root.mkdir(parents=True, exist_ok=True)
            for step in CHECKPOINT_STEPS:
                source = final_root / f"adapter_step_{step}"
                target = target_root / f"adapter_step_{step}"
                if source.is_dir() and not target.exists():
                    shutil.copytree(source, target)
        result.update({"ok": True, "gpu_steps": OPTIMIZER_STEPS, "training": trained, "security_commit": commit, "validation": validation})
        success_path = root / "EXECUTION_SUCCESS_REPORT_TRL.json"
        if success_path.exists():
            raise FileExistsError(f"refuse_overwrite:{success_path}")
        success_path.write_text(json.dumps({
            "schema_version": "execution_success_report_trl_v1",
            "recorded_utc": utc(),
            "campaign_id": campaign_id,
            "run_id": run_id,
            "status": "EXECUTION_COMMITTED_NO_PROMOTION",
            "authority": {"training_authorized": True, "run_authorized": True, "promotion_authorized": False, "deployment_authorized": False},
            "engine": "trl_peft",
            "gpu_steps": OPTIMIZER_STEPS,
            "lease_opened": True,
            "adapter_final": trained["adapter_final"],
            "training": trained,
            "security_commit": commit,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        return result
    except BaseException as exc:
        failure = exc
        raise
    finally:
        if lease is not None and not committed:
            try:
                quarantine = lease.quarantine("trl_runner_abort", f"trl_runner_aborted_before_commit:{type(failure).__name__ if failure else 'unknown'}")
            except Exception:
                quarantine = {"allowed": False, "error": traceback.format_exc()}
            if failure is not None:
                try:
                    write_abort_report(
                        root / "EXECUTION_ABORT_REPORT_TRL.json",
                        campaign_id=campaign_id,
                        run_id=run_id,
                        stage="trl_run_experiment",
                        exception_type=type(failure).__name__,
                        exception_message=str(failure),
                        traceback_text="".join(traceback.format_exception(failure)),
                        trained_result=trained,
                        commit_verdict=commit,
                        quarantine_root=str((quarantine or {}).get("path") or (quarantine or {}).get("quarantine_root") or "") or None,
                        authority={"training_authorized": True, "run_authorized": True, "lease_opened": True, "promotion_authorized": False, "deployment_authorized": False},
                    )
                except Exception:
                    pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Governed TRL/PEFT V3 runner; default is read-only validation")
    parser.add_argument("--execute", action="store_true", help="execute only after exact named campaign authorization")
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=None)
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(run_experiment(root=args.campaign_root, output_root=args.output_root), indent=2, sort_keys=True))
    else:
        report = validate_campaign(args.campaign_root)
        print(json.dumps({"ok": True, "status": report["status"], "findings": report["findings"], "engine": "trl_peft", "training_authorized": False, "run_authorized": False, "gpu_steps": 0}, sort_keys=True))
