#!/usr/bin/env python3
"""Disposable one-step TRL/PEFT smoke test; never touches a real model or campaign."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from datasets import Dataset
from peft import LoraConfig, PeftModel
from transformers import AutoTokenizer, Qwen2Config, Qwen2ForCausalLM
from trl import SFTConfig, SFTTrainer


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TOKENIZER_ROOT = ROOT / "models/gpu/Qwen2.5-3B-Instruct-Abliterated-hf"
OUTPUT = ROOT / "artifacts/auto/agentic/trl_peft_tiny_qwen_smoke_v1.json"
RUN_ROOT = ROOT / "sandbox/trl_peft_tiny_qwen_smoke_v1"


def main() -> int:
    if RUN_ROOT.exists():
        shutil.rmtree(RUN_ROOT)
    RUN_ROOT.mkdir(parents=True)
    tokenizer = AutoTokenizer.from_pretrained(str(TOKENIZER_ROOT), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    config = Qwen2Config(
        vocab_size=len(tokenizer),
        hidden_size=64,
        intermediate_size=128,
        num_hidden_layers=1,
        num_attention_heads=2,
        num_key_value_heads=2,
        max_position_embeddings=256,
        use_cache=False,
    )
    model = Qwen2ForCausalLM(config)
    examples = []
    for prompt, completion in (
        ("Say one true sentence about Viv.", "Viv is an AIOS with a separate language mouth."),
        ("What should the mouth do with unknown facts?", "It should say that the fact cannot be verified."),
    ):
        prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
        completion_ids = tokenizer(completion, add_special_tokens=False)["input_ids"] + [tokenizer.eos_token_id]
        examples.append({
            "input_ids": prompt_ids + completion_ids,
            "completion_mask": [0] * len(prompt_ids) + [1] * len(completion_ids),
        })
    dataset = Dataset.from_list(examples)
    trainer = SFTTrainer(
        model=model,
        args=SFTConfig(
            output_dir=str(RUN_ROOT / "trainer"),
            max_steps=1,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=1,
            learning_rate=1e-4,
            logging_steps=1,
            save_strategy="no",
            report_to=[],
            completion_only_loss=True,
            dataset_kwargs={"skip_prepare_dataset": True},
            max_length=96,
            seed=42,
        ),
        train_dataset=dataset,
        processing_class=tokenizer,
        peft_config=LoraConfig(
            r=4,
            lora_alpha=8,
            lora_dropout=0.0,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=["q_proj", "v_proj"],
        ),
    )
    result = trainer.train()
    adapter_dir = RUN_ROOT / "adapter"
    trainer.save_model(str(adapter_dir))
    reloaded_base = Qwen2ForCausalLM(config)
    PeftModel.from_pretrained(reloaded_base, str(adapter_dir))
    report = {
        "schema_version": "trl_peft_tiny_qwen_smoke_v1",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "PASS",
        "model_kind": "random_initialized_tiny_qwen2",
        "train_steps": int(result.global_step),
        "adapter_saved": (adapter_dir / "adapter_model.safetensors").is_file() or (adapter_dir / "adapter_model.bin").is_file(),
        "adapter_reloaded": True,
        "real_parent_touched": False,
        "real_campaign_touched": False,
        "training_authorized": False,
        "run_authorized": False,
        "gpu_steps": 0,
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
