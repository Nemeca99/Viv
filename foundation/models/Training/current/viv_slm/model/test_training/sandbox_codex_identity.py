"""Read-only Codex identity dataset paths and loaders for sandbox training."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch
from torch.nn import functional as F

# Canonical Codex identity copies (read-only for sandbox).
FOUNDATION = Path(__file__).resolve().parents[6]  # .../foundation
CODEX_IDENTITY_ROOT = (
    FOUNDATION / "models" / "Training" / "data" / "identity"
)
CODEX_V43_ROOT = CODEX_IDENTITY_ROOT / "v43_conversation_focus"
CODEX_V43_VOCAB = CODEX_V43_ROOT / "VOCAB.json"
CODEX_V43_INPUT_MANIFEST = CODEX_V43_ROOT / "INPUT_MANIFEST.json"
CODEX_V43_TENSOR_DIR = CODEX_V43_ROOT / "tensor_dataset"

CODEX_V61_ROOT = CODEX_IDENTITY_ROOT / "v61_stratified_preservation_replay"
CODEX_V62_ROOT = CODEX_IDENTITY_ROOT / "v62_dialogue_visibility_preservation"
CODEX_INDEX = CODEX_IDENTITY_ROOT / "INDEX.json"

# Read-only Codex parent checkpoint (warm-start for sandbox re-lanes).
CODEX_PARENT_CHECKPOINT = (
    FOUNDATION
    / "models"
    / "Training"
    / "runs"
    / "viv_slm"
    / "v69_v61_parent_depth_continuation_steps_1000"
    / "checkpoint.pt"
)

# Codex TRAINING_KNOBS optimizer defaults.
CODEX_LR = 2e-5
CODEX_WEIGHT_DECAY = 0.01
CODEX_MAX_GRAD_NORM = 1.0

MASKED_TENSOR_SCHEMAS = {
    "viv_slm_response_only_tensor_dataset_v1",
    "viv_slm_dialogue_aligned_tensor_dataset_v1",
    "viv_slm_dialogue_aligned_chunked_tensor_dataset_v2",
    "viv_slm_route_conditioned_chunked_tensor_dataset_v1",
    "viv_slm_packed_route_conditioned_response_only_tensor_dataset_v1",
    "viv_slm_preservation_replay_tensor_dataset_v1",
    "viv_slm_v43_conversation_focus_tensor_dataset_v1",
}

# Match Codex identity trainer plant dims (train_viv_slm_identity_v1).
IDENTITY_MODEL_CFG = dict(
    context_length=128,
    embedding_width=128,
    num_heads=4,
    head_size=32,
    num_layers=4,
    dropout=0.1,
    position_encoding="rope",
)


def read_input_manifest(root: Path) -> dict[str, Any]:
    path = root / "INPUT_MANIFEST.json"
    if not path.is_file():
        raise FileNotFoundError(f"codex_identity_input_manifest_missing:{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"codex_identity_input_manifest_invalid:{path}")
    return payload


def resolve_codex_dataset(lane: str = "v43") -> tuple[Path, Path, Path]:
    """Return (root, vocab_path, tensor_dir) for a Codex identity lane."""

    if lane in ("v43", "v43_conversation_focus", "default"):
        root = CODEX_V43_ROOT
    elif lane in ("v61", "v61_stratified_preservation_replay"):
        root = CODEX_V61_ROOT
    elif lane in ("v62", "v62_dialogue_visibility_preservation"):
        root = CODEX_V62_ROOT
    else:
        root = CODEX_IDENTITY_ROOT / lane
    vocab = root / "VOCAB.json"
    tensor_dir = root / "tensor_dataset"
    if not vocab.is_file() or not tensor_dir.is_dir():
        raise FileNotFoundError(f"codex_identity_dataset_incomplete:{root}")
    return root, vocab, tensor_dir


def _load_masked_shard(path: Path, *, vocab_size: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(payload, dict):
        raise ValueError(f"codex_shard_invalid:{path}")
    schema = str(payload.get("schema_version") or "")
    if schema not in MASKED_TENSOR_SCHEMAS:
        raise ValueError(f"codex_shard_schema_unsupported:{path}:{schema}")
    inputs = payload.get("inputs")
    targets = payload.get("targets")
    masks = payload.get("loss_mask")
    if not all(isinstance(v, torch.Tensor) for v in (inputs, targets, masks)):
        raise ValueError(f"codex_shard_tensors_missing:{path}")
    if inputs.shape != targets.shape or masks.shape != inputs.shape:
        raise ValueError(f"codex_shard_shape_mismatch:{path}")
    if inputs.numel() and (
        int(inputs.min()) < 0
        or int(inputs.max()) >= vocab_size
        or int(targets.min()) < 0
        or int(targets.max()) >= vocab_size
    ):
        raise ValueError(f"codex_shard_token_range:{path}")
    return (
        inputs.to(dtype=torch.long),
        targets.to(dtype=torch.long),
        masks.to(dtype=torch.bool),
    )


def _load_plain_shard(path: Path, *, vocab_size: int) -> tuple[torch.Tensor, torch.Tensor, None]:
    from dataset import load_tensor_shard  # local import — parent model/

    inputs, targets = load_tensor_shard(path, vocab_size=vocab_size)
    return inputs, targets, None


def load_split(
    tensor_dir: Path,
    split: str,
    *,
    vocab_size: int,
    response_only_loss: bool,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor | None]:
    split_dir = tensor_dir / split
    paths = sorted(split_dir.glob("shard_*.pt"))
    if not paths:
        raise FileNotFoundError(f"codex_identity_shards_missing:{split_dir}")
    inputs: list[torch.Tensor] = []
    targets: list[torch.Tensor] = []
    masks: list[torch.Tensor] = []
    for path in paths:
        if response_only_loss:
            shard_in, shard_tg, shard_mask = _load_masked_shard(path, vocab_size=vocab_size)
            inputs.append(shard_in)
            targets.append(shard_tg)
            masks.append(shard_mask)
        else:
            shard_in, shard_tg, _ = _load_plain_shard(path, vocab_size=vocab_size)
            inputs.append(shard_in)
            targets.append(shard_tg)
    if response_only_loss:
        return torch.cat(inputs, dim=0), torch.cat(targets, dim=0), torch.cat(masks, dim=0)
    return torch.cat(inputs, dim=0), torch.cat(targets, dim=0), None


def teacher_anchor_kl(
    student_logits: torch.Tensor,
    teacher_logits: torch.Tensor,
    loss_masks: torch.Tensor,
) -> torch.Tensor:
    flat_masks = loss_masks.reshape(-1).bool()
    student = student_logits.float().reshape(-1, student_logits.shape[-1])[flat_masks]
    teacher = teacher_logits.float().reshape(-1, teacher_logits.shape[-1])[flat_masks]
    if student.numel() == 0:
        raise ValueError("sandbox_teacher_anchor_empty")
    return F.kl_div(
        F.log_softmax(student, dim=-1),
        F.softmax(teacher, dim=-1),
        reduction="batchmean",
    )


def evaluate_teacher_kl(
    student: Any,
    teacher: Any,
    inputs: torch.Tensor,
    *,
    device: torch.device,
    batch_size: int,
    loss_masks: torch.Tensor,
) -> dict[str, float | int]:
    was_training = student.training
    student.eval()
    teacher.eval()
    total_kl = 0.0
    total_tokens = 0
    with torch.no_grad():
        for start in range(0, inputs.shape[0], batch_size):
            batch_inputs = inputs[start : start + batch_size].to(device)
            batch_masks = loss_masks[start : start + batch_size].to(device)
            if not bool(batch_masks.reshape(-1).bool().any()):
                continue
            student_logits = student(batch_inputs)
            teacher_logits = teacher(batch_inputs)
            kl = teacher_anchor_kl(student_logits, teacher_logits, batch_masks)
            tokens = int(batch_masks.reshape(-1).bool().sum())
            total_kl += float(kl) * tokens
            total_tokens += tokens
    if was_training:
        student.train()
    return {
        "teacher_kl": total_kl / max(total_tokens, 1),
        "tokens": total_tokens,
    }


def masked_batch_loss(
    model: Any,
    logits: torch.Tensor,
    targets: torch.Tensor,
    loss_masks: torch.Tensor | None,
) -> tuple[torch.Tensor, float]:
    if loss_masks is None:
        loss, acc = model.loss_and_accuracy(logits, targets)
        return loss, float(acc)
    valid = loss_masks.reshape(-1).bool()
    if not bool(valid.any()):
        raise ValueError("codex_batch_no_response_targets")
    flat_logits = logits.reshape(-1, model.vocab_size)[valid]
    flat_targets = targets.reshape(-1)[valid]
    loss = F.cross_entropy(flat_logits, flat_targets)
    acc = float((flat_logits.argmax(dim=-1) == flat_targets).float().mean())
    return loss, acc


def weighted_masked_batch_loss(
    model: Any,
    logits: torch.Tensor,
    targets: torch.Tensor,
    loss_masks: torch.Tensor,
    *,
    token_weights: torch.Tensor | None = None,
) -> tuple[torch.Tensor, float]:
    valid = loss_masks.reshape(-1).bool()
    if not bool(valid.any()):
        raise ValueError("codex_batch_no_response_targets")
    flat_logits = logits.reshape(-1, model.vocab_size)[valid]
    flat_targets = targets.reshape(-1)[valid]
    per_token = F.cross_entropy(flat_logits, flat_targets, reduction="none")
    if token_weights is not None:
        flat_weights = token_weights.reshape(-1)[valid].to(per_token.dtype)
        flat_weights = torch.clamp(flat_weights, min=1e-6)
        loss = (per_token * flat_weights).sum() / flat_weights.sum()
    else:
        loss = per_token.mean()
    acc = float((flat_logits.argmax(dim=-1) == flat_targets).float().mean())
    return loss, acc


def evaluate_split(
    model: Any,
    inputs: torch.Tensor,
    targets: torch.Tensor,
    *,
    device: torch.device,
    batch_size: int,
    loss_masks: torch.Tensor | None = None,
) -> dict[str, float | int]:
    import math

    was_training = model.training
    model.eval()
    total_nll = 0.0
    total_correct = 0
    total_tokens = 0
    with torch.no_grad():
        for start in range(0, inputs.shape[0], batch_size):
            batch_inputs = inputs[start : start + batch_size].to(device)
            batch_targets = targets[start : start + batch_size].to(device)
            logits = model(batch_inputs)
            flat_logits = logits.reshape(-1, model.vocab_size)
            flat_targets = batch_targets.reshape(-1)
            if loss_masks is None:
                valid = None
            else:
                valid = loss_masks[start : start + batch_size].to(device).reshape(-1).bool()
                if not bool(valid.any()):
                    continue
                flat_logits = flat_logits[valid]
                flat_targets = flat_targets[valid]
            total_nll += float(F.cross_entropy(flat_logits, flat_targets, reduction="sum"))
            total_correct += int((flat_logits.argmax(dim=-1) == flat_targets).sum())
            total_tokens += int(flat_targets.numel())
    if was_training:
        model.train()
    nll = total_nll / max(total_tokens, 1)
    return {
        "examples": int(inputs.shape[0]),
        "tokens": total_tokens,
        "nll": nll,
        "perplexity": math.exp(min(nll, 20.0)),
        "token_accuracy": total_correct / max(total_tokens, 1),
    }
