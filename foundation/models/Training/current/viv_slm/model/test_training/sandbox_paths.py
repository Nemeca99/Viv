"""Sandbox-only path constants. Never point writers at live Codex campaign trees."""
from __future__ import annotations

from pathlib import Path

# model/ (parent of this sandbox — import plant modules from here; do not write there
# except sealed receipts under artifacts_local/experiments/ via the smoke runner).
MODEL_DIR = Path(__file__).resolve().parent.parent
SANDBOX_DIR = Path(__file__).resolve().parent

SHARED_DIR = SANDBOX_DIR / "shared"
CHECKPOINTS_DIR = SANDBOX_DIR / "checkpoints"
EFFICIENT_CKPT = CHECKPOINTS_DIR / "efficient" / "specialist.pt"
DEEP_CKPT = CHECKPOINTS_DIR / "deep" / "specialist.pt"
VOCAB_MANIFEST = SHARED_DIR / "vocab_manifest.json"
RUNS_DIR = SANDBOX_DIR / "runs"
DATA_DIR = SANDBOX_DIR / "data"
CORPUS_FILE = DATA_DIR / "identity_corpus.txt"
DATASET_DIR = SANDBOX_DIR / "dataset"
CAMPAIGNS_DIR = SANDBOX_DIR / "campaigns"

# Sealed experiment receipt (allowed write outside sandbox, per operator).
RECEIPT_PATH = (
    MODEL_DIR / "artifacts_local" / "experiments" / "H_sandbox_test_training.json"
)

# Legacy inline corpus (mint smoke fallback).
IDENTITY_CORPUS = [
    "the dog bites man and the cat sits on the mat\n",
    "viv speaks with one identity and two specialists\n",
]

SCHEMA_CKPT = "viv_slm_sandbox_specialist_checkpoint_v1"
SCHEMA_RECEIPT = "viv_slm_sandbox_test_training_v1"
SCHEMA_CAMPAIGN = "viv_slm_sandbox_campaign_run_v1"

# Mint smoke dims (quick fingerprint proof).
TINY_CFG = dict(
    context_length=32,
    embedding_width=64,
    num_heads=4,
    head_size=16,
    num_layers=2,
    dropout=0.0,
    position_encoding="rope",
)

# Campaign plant — sandbox scale, not Codex production.
CAMPAIGN_CFG = dict(
    context_length=64,
    embedding_width=96,
    num_heads=4,
    head_size=24,
    num_layers=3,
    dropout=0.05,
    position_encoding="rope",
)

# Two specialists: same Codex identity (vocab/data), different reasoning curricula.
# Training runs on GPU for both; deploy_device is where speak_lanes runs inference.
TRAIN_DEVICE = "cuda"
CODEX_LR = 2e-5
CODEX_WEIGHT_DECAY = 0.01
CODEX_MAX_GRAD_NORM = 1.0
# V69 controller final anchor (Codex matched-metrics run).
TEACHER_ANCHOR_WEIGHT = 0.31
TEACHER_PASS_STEPS = 1500
DIVERGENT_STEPS = 1750

EFFICIENT_TRAIN = dict(
    seed=11,
    steps=8,
    lr=CODEX_LR,
    weight_decay=CODEX_WEIGHT_DECAY,
    max_grad_norm=CODEX_MAX_GRAD_NORM,
    label="efficient_cpu_mind_specialist",
    reasoning_style="speculative_verify_short",
    train_device=TRAIN_DEVICE,
    deploy_device="cpu",
    batch_size=64,
    sample_prompt="User: Hello, Viv.\nViv:",
    sample_tokens=48,
    sample_temperature=0.0,
)
DEEP_TRAIN = dict(
    seed=22,
    steps=40,
    lr=CODEX_LR,
    weight_decay=CODEX_WEIGHT_DECAY,
    max_grad_norm=CODEX_MAX_GRAD_NORM,
    label="deep_gpu_mouth_specialist",
    reasoning_style="explore_then_lock_long",
    train_device=TRAIN_DEVICE,
    deploy_device="cuda",
    batch_size=64,
    sample_prompt="User: What are you?\nViv:",
    sample_tokens=128,
    sample_temperature=0.7,
)

# Full campaign defaults (override via CLI). GPU trains both checkpoints.
EFFICIENT_CAMPAIGN = {
    **EFFICIENT_TRAIN,
    "steps": 250,
    "batch_size": 64,
    "checkpoint_every": 50,
    "eval_every": 50,
}
DEEP_CAMPAIGN = {
    **DEEP_TRAIN,
    "steps": 250,
    "batch_size": 64,
    "checkpoint_every": 50,
    "eval_every": 50,
}

# Teacher-anchor pass: shared Codex parent KL, same LR family as V69.
EFFICIENT_TEACHER_PASS = {
    **EFFICIENT_CAMPAIGN,
    "steps": TEACHER_PASS_STEPS,
    "anchor_weight": TEACHER_ANCHOR_WEIGHT,
    "training_phase": "teacher",
}
DEEP_TEACHER_PASS = {
    **DEEP_CAMPAIGN,
    "steps": TEACHER_PASS_STEPS,
    "anchor_weight": TEACHER_ANCHOR_WEIGHT,
    "training_phase": "teacher",
}

# Lane divergence: same identity data, different reasoning pressure after teacher pass.
EFFICIENT_DIVERGENT = {
    **EFFICIENT_CAMPAIGN,
    "steps": DIVERGENT_STEPS,
    "lr": 2.8e-5,
    "weight_decay": 0.008,
    "anchor_weight": 0.20,
    "sample_tokens": 48,
    "sample_temperature": 0.0,
    "training_phase": "divergent",
    "reasoning_style": "speculative_verify_short",
}
DEEP_DIVERGENT = {
    **DEEP_CAMPAIGN,
    "steps": DIVERGENT_STEPS,
    "lr": 1.0e-5,
    "weight_decay": 0.012,
    "anchor_weight": 0.40,
    "sample_tokens": 128,
    "sample_temperature": 0.7,
    "training_phase": "divergent",
    "reasoning_style": "explore_then_lock_long",
}
