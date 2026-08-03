#!/usr/bin/env python3
"""Local LoRA SFT for Viv GPU voice — OpenAster base + AIOS fluency (no RLHF).

Downloads HF base to foundation/models/gpu/ if missing, trains LoRA adapter, writes adapter dir.
Requires: torch+cuda, transformers, peft, datasets (AIOS venv).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
HF_ID = "binichallein/OpenAster1-128k-base"
LOCAL_BASE = FOUNDATION / "models" / "gpu" / "OpenAster1-128k-base-hf"
ADAPTER_OUT = FOUNDATION / "models" / "gpu" / "viv_voice_lora"
FLUENCY = FOUNDATION / "artifacts" / "models" / "voice_fluency.jsonl"
TRAIN_JSONL = FOUNDATION / "artifacts" / "models" / "viv_voice_sft_train.jsonl"


def _build_train_rows() -> list[dict]:
    rows: list[dict] = []
    # Packet-shaped pairs (primary speak shape)
    pairs = [
        (
            "Translate facts only. Do not invent. Do not decide.\nTone: measured.\n"
            "Query: state summary\nStatus: ACTIVE S_n=0.72\n"
            "Facts:\n- master_s_n=0.7200\n- status=ACTIVE\n- plant=PASS\nMemory:\n- (none)\n"
            "Spoken report:\nArchitect: ",
            "stability is 0.72 and I am active. Plant is pass. I speak from facts only.",
        ),
        (
            "Translate facts only. Do not invent. Do not decide.\nTone: terse.\n"
            "Query: state summary\nStatus: DORMANT S_n=0.38\n"
            "Facts:\n- master_s_n=0.3800\n- status=DORMANT\nMemory:\n- (none)\n"
            "Spoken report:\nArchitect: ",
            "S_n is 0.38 under the 0.45 dormancy line. I am dormant and will not act until stability returns.",
        ),
        (
            "Translate facts only. Do not invent. Do not decide.\nTone: calm.\n"
            "Query: hello\nStatus: ACTIVE S_n=0.61\n"
            "Facts:\n- master_s_n=0.6100\n- status=ACTIVE\nMemory:\n- (none)\n"
            "Spoken report:\nArchitect: ",
            "Hello, Architect. Master stability is 0.61 and I am active. I translate; I do not decide.",
        ),
        (
            "Translate facts only. Do not invent. Do not decide.\nTone: measured.\n"
            "Query: state summary\nStatus: ACTIVE S_n=0.56\n"
            "Facts:\n- master_s_n=0.5600\n- status=ACTIVE\n- n_subsystems=4\n"
            "Memory:\n- first real memory for CPU AI\nSpoken report:\nArchitect: ",
            "Stability is 0.56. I am active with four subsystems reporting. "
            "Recent memory notes the first CPU AI memory. That is all I am authorized to say.",
        ),
        (
            "Structured state:\n{\"S_n\":0.72,\"status\":\"ACTIVE\"}\nSpoken: ",
            "Stability is good at S_n 0.72. I am active and within safe limits.",
        ),
        (
            "Structured state:\n{\"S_n\":0.38,\"status\":\"DORMANT\"}\nSpoken: ",
            "S_n is 0.38, below the 0.45 dormancy line. I am in a forced safe state.",
        ),
        (
            "Translate facts only. Do not invent. Do not decide.\nTone: measured.\n"
            "Query: state summary\nStatus: ACTIVE S_n=0.81\n"
            "Facts:\n- master_s_n=0.8100\n- status=ACTIVE\n- plant=PASS\n"
            "- autonomy=solo\nMemory:\n- autonomous beat mode=ACTIVE\n"
            "Spoken report:\nArchitect: ",
            "Master stability is 0.81. I am active in solo autonomy. Plant is pass. "
            "I report facts only and wait for your next command.",
        ),
        (
            "Translate facts only. Do not invent. Do not decide.\nTone: calm.\n"
            "Query: state summary\nStatus: ACTIVE S_n=0.67\n"
            "Facts:\n- master_s_n=0.6700\n- status=ACTIVE\n- voice_backend=hf_lora\n"
            "Memory:\n- live note from autonomous beat\nSpoken report:\nArchitect: ",
            "Stability is 0.67 and I am active. Voice is on the local LoRA path. "
            "A live autonomous note is in memory. That is the full report.",
        ),
        (
            "Translate facts only. Do not invent. Do not decide.\nTone: terse.\n"
            "Query: state summary\nStatus: ACTIVE S_n=0.52\n"
            "Facts:\n- master_s_n=0.5200\n- status=ACTIVE\n- agentic_tick=ok\n"
            "Spoken report:\nArchitect: ",
            "S_n is 0.52. I am active. Last agentic tick was ok. No further claims.",
        ),
        (
            "Translate facts only. Do not invent. Do not decide.\nTone: measured.\n"
            "Query: who are you\nStatus: ACTIVE S_n=0.70\n"
            "Facts:\n- name=Viv\n- role=CPU neuro-symbolic mind\n- gpu=optional voice\n"
            "Spoken report:\nArchitect: ",
            "I am Viv, the CPU mind of AIOS. The GPU only translates what I authorize. "
            "I do not invent, and I do not decide outside the membrane.",
        ),
    ]
    for prompt, completion in pairs:
        rows.append({"text": prompt + completion})
    # Expand lightly by repeating short pairs (small corpus)
    rows = rows * 12
    if FLUENCY.is_file():
        with FLUENCY.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    msg = json.loads(line).get("messages") or []
                except json.JSONDecodeError:
                    continue
                if len(msg) < 3:
                    continue
                user = str(msg[1].get("content") or "")
                asst = str(msg[2].get("content") or "")
                if 30 <= len(asst) <= 280 and "Speak this" not in user:
                    rows.append({"text": f"{user}\n{asst}"})
                elif "Structured state" in user and len(asst) < 300:
                    rows.append({"text": f"{user}\n{asst}"})
    return rows


def ensure_train_jsonl() -> Path:
    rows = _build_train_rows()
    TRAIN_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with TRAIN_JSONL.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return TRAIN_JSONL


def download_base() -> Path:
    from huggingface_hub import snapshot_download

    LOCAL_BASE.mkdir(parents=True, exist_ok=True)
    marker = LOCAL_BASE / "config.json"
    if marker.is_file():
        print(f"base already local: {LOCAL_BASE}")
        return LOCAL_BASE
    print(f"downloading {HF_ID} -> {LOCAL_BASE}")
    snapshot_download(
        repo_id=HF_ID,
        local_dir=str(LOCAL_BASE),
        local_dir_use_symlinks=False,
    )
    return LOCAL_BASE


def train(*, steps: int, lr: float) -> Path:
    import torch
    from datasets import load_dataset
    from peft import LoraConfig, get_peft_model
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    if not torch.cuda.is_available():
        raise SystemExit("CUDA required for this LoRA path")

    # MoE config embeds numpy dtypes; INFO logging calls config.__repr__ -> JSON crash
    import transformers

    transformers.logging.set_verbosity_error()

    base = download_base()
    train_path = ensure_train_jsonl()
    print(f"train rows file: {train_path}")

    tok = AutoTokenizer.from_pretrained(str(base), trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    # Explicit cuda (no device_map) — matches voice_core/hf_lora.py serve path
    model = AutoModelForCausalLM.from_pretrained(
        str(base),
        torch_dtype=torch.float16,
        trust_remote_code=True,
    )
    model.to("cuda")
    model.gradient_checkpointing_enable()

    peft_cfg = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.0,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )
    model = get_peft_model(model, peft_cfg)
    model.print_trainable_parameters()

    ds = load_dataset("json", data_files=str(train_path), split="train")

    def tokenize(batch):
        return tok(
            batch["text"],
            truncation=True,
            max_length=384,
            padding="max_length",
        )

    ds = ds.map(tokenize, batched=True, remove_columns=ds.column_names)

    args = TrainingArguments(
        output_dir=str(ADAPTER_OUT / "runs"),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=lr,
        num_train_epochs=1,
        max_steps=steps,
        fp16=True,
        logging_steps=5,
        save_steps=max(steps, 50),
        report_to=[],
        optim="adamw_torch",
        warmup_ratio=0.03,
    )
    collator = DataCollatorForLanguageModeling(tok, mlm=False)
    trainer = Trainer(model=model, args=args, train_dataset=ds, data_collator=collator)
    trainer.train()
    ADAPTER_OUT.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(ADAPTER_OUT))
    tok.save_pretrained(str(ADAPTER_OUT))
    meta = {
        "base": str(base),
        "hf_id": HF_ID,
        "steps": steps,
        "lr": lr,
        "train_jsonl": str(train_path),
        "no_rlhf": True,
    }
    (ADAPTER_OUT / "viv_train_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"adapter saved: {ADAPTER_OUT}")
    return ADAPTER_OUT


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--download-only", action="store_true")
    p.add_argument("--steps", type=int, default=80, help="Short proof train; raise for better fluency")
    p.add_argument("--lr", type=float, default=2e-4)
    args = p.parse_args()
    if args.download_only:
        download_base()
        return 0
    train(steps=args.steps, lr=args.lr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
