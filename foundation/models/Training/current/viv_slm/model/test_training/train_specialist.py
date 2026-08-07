#!/usr/bin/env python3
"""Train one sandbox identity specialist (efficient CPU-mind or deep GPU-mouth).

Both specialists train on **GPU** from the same Codex identity data (shared vocab).
Different seeds / learning rates / step budgets teach different reasoning styles.
At speak time: efficient deploys on CPU, deep on GPU (`deploy_device` in checkpoint).

Default: Codex v43 identity dataset (read-only, response-only loss, vocab 96).
Writes checkpoints only under test_training/. Does not mutate Codex originals.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import sys
from pathlib import Path
from typing import Any

import torch

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))
if str(SANDBOX) not in sys.path:
    sys.path.insert(0, str(SANDBOX))

from plant_checkpoint import load_plant_state_dict  # noqa: E402
from plant_runtime import configure_plant_runtime, detect_hardware  # noqa: E402
from rid_pid import apply_pid_u_to_optimizer  # noqa: E402
from sandbox_codex_identity import (  # noqa: E402
    CODEX_MAX_GRAD_NORM,
    CODEX_PARENT_CHECKPOINT,
    CODEX_WEIGHT_DECAY,
    IDENTITY_MODEL_CFG,
    evaluate_split,
    evaluate_teacher_kl,
    load_split,
    masked_batch_loss,
    read_input_manifest,
    resolve_codex_dataset,
    teacher_anchor_kl,
    weighted_masked_batch_loss,
)
from sandbox_paths import (  # noqa: E402
    CAMPAIGN_CFG,
    CHECKPOINTS_DIR,
    DATASET_DIR,
    DEEP_CAMPAIGN,
    DEEP_CKPT,
    DEEP_DIVERGENT,
    DEEP_TEACHER_PASS,
    EFFICIENT_CAMPAIGN,
    EFFICIENT_CKPT,
    EFFICIENT_DIVERGENT,
    EFFICIENT_TEACHER_PASS,
    RUNS_DIR,
    SCHEMA_CAMPAIGN,
    SCHEMA_CKPT,
    TINY_CFG,
    VOCAB_MANIFEST,
)
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402


def _teacher_confidence_weights(
    teacher_logits: torch.Tensor,
    targets: torch.Tensor,
    mask: torch.Tensor,
    *,
    min_weight: float,
    max_weight: float,
    boilerplate_token_ids: set[int] | None = None,
    boilerplate_scale: float = 1.0,
) -> torch.Tensor:
    probs = torch.softmax(teacher_logits.float(), dim=-1)
    target_prob = torch.gather(probs, dim=-1, index=targets.unsqueeze(-1)).squeeze(-1)
    valid = mask.bool()
    if not bool(valid.reshape(-1).any()):
        return torch.ones_like(target_prob, dtype=torch.float32)
    valid_vals = target_prob[valid]
    pmin = valid_vals.min()
    pmax = valid_vals.max()
    denom = (pmax - pmin).clamp_min(1e-8)
    norm = (target_prob - pmin) / denom
    weights = min_weight + norm * (max_weight - min_weight)
    if boilerplate_token_ids:
        boilerplate = torch.zeros_like(targets, dtype=torch.bool)
        for token_id in boilerplate_token_ids:
            boilerplate |= targets.eq(token_id)
        weights = torch.where(boilerplate, weights * float(boilerplate_scale), weights)
    return weights.to(dtype=torch.float32)


def _fingerprint(state: dict[str, torch.Tensor]) -> str:
    blob: list[str] = []
    for key, tensor in sorted(state.items()):
        if torch.is_tensor(tensor):
            blob.append(
                f"{key}:{float(tensor.detach().float().sum())}:{tuple(tensor.shape)}"
            )
    return sha256("|".join(blob).encode("utf-8")).hexdigest().upper()


def _lane_config(lane: str, *, phase: str = "default") -> dict[str, Any]:
    if phase == "teacher":
        return dict(EFFICIENT_TEACHER_PASS if lane == "efficient" else DEEP_TEACHER_PASS)
    if phase == "divergent":
        return dict(EFFICIENT_DIVERGENT if lane == "efficient" else DEEP_DIVERGENT)
    if lane == "efficient":
        return dict(EFFICIENT_CAMPAIGN)
    if lane == "deep":
        return dict(DEEP_CAMPAIGN)
    raise ValueError(f"sandbox_lane_invalid:{lane}")


def _clone_frozen_teacher(
    model: TransformerLanguageModel,
    model_cfg: dict[str, Any],
) -> TransformerLanguageModel:
    device = next(model.parameters()).device
    rid_kwargs: dict[str, Any] = {}
    if bool(getattr(model, "rid_adapter", False)):
        rid_kwargs = {
            "rid_adapter": True,
            "rid_rank": int(model.rid_rank),
            "rid_alpha": float(model.rid_alpha),
            "rid_dropout": float(model.rid_dropout),
        }
    teacher = TransformerLanguageModel(model.vocab_size, **model_cfg, **rid_kwargs).to(device)
    teacher.load_state_dict(model.state_dict(), strict=False)
    if hasattr(model, "_rid_metrics") and hasattr(teacher, "set_rid_metrics"):
        teacher.set_rid_metrics(**dict(model._rid_metrics))
    if hasattr(model, "_rid_role_scales") and hasattr(teacher, "set_rid_role_scales"):
        teacher.set_rid_role_scales(dict(model._rid_role_scales))
    teacher.eval()
    for parameter in teacher.parameters():
        parameter.requires_grad_(False)
    return teacher


def _load_frozen_teacher(
    path: Path,
    tok: CharacterTokenizer,
    model_cfg: dict[str, Any],
    device: torch.device,
    *,
    rid_adapter: bool = False,
    rid_rank: int = 8,
    rid_alpha: float = 16.0,
    rid_dropout: float = 0.0,
) -> TransformerLanguageModel:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(payload, dict) or "model_state_dict" not in payload:
        raise ValueError(f"sandbox_teacher_anchor_invalid:{path}")
    payload_vocab = str(payload.get("vocab_sha256", ""))
    if payload_vocab and payload_vocab != tok.vocab_sha256:
        raise ValueError("sandbox_teacher_anchor_vocab_mismatch")
    rid_kwargs: dict[str, Any] = {}
    if rid_adapter:
        rid_kwargs = {
            "rid_adapter": True,
            "rid_rank": int(rid_rank),
            "rid_alpha": float(rid_alpha),
            "rid_dropout": float(rid_dropout),
        }
    teacher = TransformerLanguageModel(tok.vocab_size, **model_cfg, **rid_kwargs).to(device)
    load_plant_state_dict(
        teacher,
        payload["model_state_dict"],
        strict=False,
        config=model_cfg,
    )
    teacher.eval()
    for parameter in teacher.parameters():
        parameter.requires_grad_(False)
    return teacher


def _resolve_device(requested: str, *, allow_cpu_fallback: bool) -> torch.device:
    req = str(requested).lower()
    if req.startswith("cuda"):
        if not torch.cuda.is_available():
            if allow_cpu_fallback:
                return torch.device("cpu")
            raise RuntimeError("sandbox_training_requires_cuda")
        return torch.device(req if req != "cuda" else "cuda:0")
    return torch.device(req)


def _sample(
    model: TransformerLanguageModel,
    tok: CharacterTokenizer,
    prompt: str,
    *,
    device: torch.device,
    max_new_tokens: int,
    temperature: float,
    seed: int,
) -> str:
    model.eval()
    ids = torch.tensor([tok.encode(prompt)], dtype=torch.long, device=device)
    gen = torch.Generator(device=device)
    gen.manual_seed(seed)
    with torch.no_grad():
        out = model.generate(
            ids,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            generator=gen,
        )
    return tok.decode(out[0].detach().cpu().tolist())


def _save_checkpoint(
    path: Path,
    *,
    model: TransformerLanguageModel,
    optimizer: torch.optim.Optimizer,
    tok: CharacterTokenizer,
    lane: str,
    step: int,
    history: list[dict[str, Any]],
    campaign: dict[str, Any],
    dataset_meta: dict[str, Any],
    model_cfg: dict[str, Any],
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
    fp = _fingerprint(state)
    payload = {
        "schema_version": SCHEMA_CKPT,
        "sandbox_only": True,
        "originals_untouched": True,
        "lane": lane,
        "reasoning_style": campaign.get("reasoning_style"),
        "deploy_device": campaign.get("deploy_device"),
        "train_device": campaign.get("train_device"),
        "vocab_size": tok.vocab_size,
        "vocab_sha256": tok.vocab_sha256,
        "dataset": dataset_meta,
        "config": {"vocab_size": tok.vocab_size, **model_cfg, **model.plant_config()},
        "train": {
            "seed": campaign["seed"],
            "steps_completed": step,
            "steps_target": campaign["steps"],
            "learning_rate": campaign["lr"],
            "batch_size": campaign["batch_size"],
            "device": str(next(model.parameters()).device),
            "training_phase": campaign.get("training_phase"),
            "anchor_weight": campaign.get("anchor_weight"),
            "teacher_anchor": campaign.get("teacher_anchor"),
        },
        "weight_fingerprint": fp,
        "model_state_dict": state,
        "optimizer_state_dict": optimizer.state_dict(),
        "training_history": history,
    }
    torch.save(payload, path)
    return {"path": str(path).replace("\\", "/"), "weight_fingerprint": fp, "step": step}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=("efficient", "deep"), required=True)
    parser.add_argument(
        "--codex-identity",
        choices=("v43", "v61", "v62"),
        default="v43",
        help="Read-only Codex identity lane (v61 = preservation replay, richer train set).",
    )
    parser.add_argument(
        "--local-dataset",
        action="store_true",
        help="Use sandbox dataset/ from sandbox_build_dataset.py instead of Codex.",
    )
    parser.add_argument("--dataset", default=None, help="Explicit tensor_dataset dir.")
    parser.add_argument("--vocab", default=None, help="Explicit VOCAB.json path.")
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--learning-rate", type=float, default=None)
    parser.add_argument("--device", default=None, help="Training device (default: cuda for both lanes).")
    parser.add_argument(
        "--allow-cpu-fallback",
        action="store_true",
        help="Allow CPU if CUDA unavailable (not recommended).",
    )
    parser.add_argument(
        "--training-phase",
        choices=("default", "teacher", "divergent"),
        default="default",
        help="teacher = Codex parent KL pass; divergent = lane-specific fine-tune.",
    )
    parser.add_argument(
        "--teacher-anchor",
        default=None,
        help="Frozen teacher checkpoint (.pt). Default: clone weights at --resume boundary.",
    )
    parser.add_argument(
        "--teacher-from-resume",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Clone resumed student as teacher (Codex immediate-parent style). Default: on for teacher/divergent phases.",
    )
    parser.add_argument(
        "--anchor-weight",
        type=float,
        default=None,
        help="Teacher KL weight (default: phase campaign or 0.31).",
    )
    parser.add_argument(
        "--loss-weighting",
        choices=("none", "teacher_confidence"),
        default="none",
        help="Optional weighted CE mode for aggressive NLL shaping.",
    )
    parser.add_argument("--weight-min", type=float, default=0.15)
    parser.add_argument("--weight-max", type=float, default=1.85)
    parser.add_argument(
        "--boilerplate-scale",
        type=float,
        default=0.25,
        help="Scale applied to boilerplate tokens (<END>, newline, space) in weighted mode.",
    )
    parser.add_argument("--resume", default=None)
    parser.add_argument(
        "--warm-start",
        default=None,
        help="Codex parent checkpoint .pt (model weights only, fresh optimizer).",
    )
    parser.add_argument("--checkpoint-every", type=int, default=None)
    parser.add_argument("--eval-every", type=int, default=None)
    parser.add_argument("--rid-adapter", action="store_true", help="Enable RID adapter path in transformer.")
    parser.add_argument("--rid-rank", type=int, default=8)
    parser.add_argument("--rid-alpha", type=float, default=16.0)
    parser.add_argument("--rid-dropout", type=float, default=0.0)
    parser.add_argument(
        "--rid-adapter-only",
        action="store_true",
        help="Train only RID adapter parameters (alias for --rid-train-mode adapter_only).",
    )
    parser.add_argument(
        "--rid-train-mode",
        choices=("adapter_only", "full", "hybrid", "last_n"),
        default=None,
        help="adapter_only=freeze dense; full=train all; hybrid=dual LR; last_n=adapters+final blocks.",
    )
    parser.add_argument(
        "--rid-base-lr",
        type=float,
        default=None,
        help="Base-weight LR for hybrid/last_n mode (default: campaign lr * 0.25).",
    )
    parser.add_argument(
        "--rid-unfreeze-last-n",
        type=int,
        default=2,
        help="For last_n mode: unfreeze final N transformer blocks (+ ln/lm_head).",
    )
    parser.add_argument("--rid-residual", type=float, default=0.0)
    parser.add_argument("--uml-nesting", type=float, default=0.0)
    parser.add_argument("--uml-math", type=float, default=0.0)
    parser.add_argument(
        "--rid-residual-feedback",
        action="store_true",
        help="EMA-couple batch SFT loss into rid_residual / PID during training.",
    )
    parser.add_argument(
        "--pid-lr-couple",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When RID adapter is on, scale optimizer LR from PID actuation u (default: on).",
    )
    parser.add_argument(
        "--pid-lr-min-scale",
        type=float,
        default=0.55,
        help="Minimum LR multiplier from PID u coupling.",
    )
    parser.add_argument(
        "--pid-lr-max-scale",
        type=float,
        default=1.15,
        help="Maximum LR multiplier from PID u coupling.",
    )
    parser.add_argument(
        "--rid-role-scales",
        default=None,
        help='JSON object of role->scale, e.g. {"lm_head":0.4,"ffn_in":0.5}.',
    )
    return parser


def _resolve_data(args: argparse.Namespace) -> tuple[CharacterTokenizer, Path, bool, dict[str, Any], dict[str, Any]]:
    if args.local_dataset:
        dataset_dir = Path(args.dataset or DATASET_DIR)
        vocab_path = Path(args.vocab or VOCAB_MANIFEST)
        if not vocab_path.is_file():
            raise FileNotFoundError(f"sandbox_vocab_missing:{vocab_path}")
        tok = CharacterTokenizer.from_manifest(vocab_path)
        response_only = False
        model_cfg = dict(CAMPAIGN_CFG)
        meta = {
            "source": "sandbox_local",
            "dataset_dir": str(dataset_dir).replace("\\", "/"),
            "response_only_loss": False,
        }
        return tok, dataset_dir, response_only, meta, model_cfg

    if args.dataset and args.vocab:
        root = Path(args.dataset).parent.parent
        tok = CharacterTokenizer.from_manifest(args.vocab)
        manifest = read_input_manifest(root)
        response_only = bool(manifest.get("response_only_loss", False))
        model_cfg = dict(IDENTITY_MODEL_CFG)
        meta = {
            "source": "codex_identity_explicit",
            "root": str(root).replace("\\", "/"),
            "response_only_loss": response_only,
            "train_examples": manifest.get("train_examples"),
            "validation_examples": manifest.get("validation_examples"),
        }
        return tok, Path(args.dataset), response_only, meta, model_cfg

    root, vocab_path, tensor_dir = resolve_codex_dataset(str(args.codex_identity))
    manifest = read_input_manifest(root)
    tok = CharacterTokenizer.from_manifest(vocab_path)
    response_only = bool(manifest.get("response_only_loss", True))
    model_cfg = dict(IDENTITY_MODEL_CFG)
    meta = {
        "source": "codex_identity_read_only",
        "lane_id": str(args.codex_identity),
        "root": str(root).replace("\\", "/"),
        "read_only": True,
        "originals_untouched": True,
        "response_only_loss": response_only,
        "train_examples": manifest.get("train_examples"),
        "validation_examples": manifest.get("validation_examples"),
        "vocab_size": manifest.get("vocab_size"),
    }
    return tok, tensor_dir, response_only, meta, model_cfg


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    lane = str(args.lane)
    phase = str(args.training_phase)
    campaign = _lane_config(lane, phase=phase)
    if args.steps is not None:
        campaign["steps"] = int(args.steps)
    if args.batch_size is not None:
        campaign["batch_size"] = int(args.batch_size)
    if args.learning_rate is not None:
        campaign["lr"] = float(args.learning_rate)
    if args.checkpoint_every is not None:
        campaign["checkpoint_every"] = int(args.checkpoint_every)
    if args.eval_every is not None:
        campaign["eval_every"] = int(args.eval_every)
    if args.anchor_weight is not None:
        campaign["anchor_weight"] = float(args.anchor_weight)
    campaign["loss_weighting"] = str(args.loss_weighting)
    campaign["weight_min"] = float(args.weight_min)
    campaign["weight_max"] = float(args.weight_max)
    campaign["boilerplate_scale"] = float(args.boilerplate_scale)

    teacher_path: Path | None = None
    teacher_from_resume = args.teacher_from_resume
    if teacher_from_resume is None:
        teacher_from_resume = phase in ("teacher", "divergent")
    if args.teacher_anchor:
        teacher_path = Path(args.teacher_anchor)
        teacher_from_resume = False
        campaign["teacher_anchor"] = str(teacher_path).replace("\\", "/")
    elif phase in ("teacher", "divergent"):
        campaign["teacher_anchor"] = "resume_snapshot"

    tok, tensor_dir, response_only, dataset_meta, model_cfg = _resolve_data(args)
    weighted_mode = str(args.loss_weighting)
    boilerplate_token_ids: set[int] = set()
    for ch in ("\n", " ", "<", ">", "E", "N", "D"):
        if ch in tok.stoi:
            boilerplate_token_ids.add(int(tok.stoi[ch]))

    device_str = args.device or campaign.get("train_device", "cuda")
    device = _resolve_device(device_str, allow_cpu_fallback=bool(args.allow_cpu_fallback))
    configure_plant_runtime(device=str(device))

    train_in, train_tg, train_mask = load_split(
        tensor_dir, "train", vocab_size=tok.vocab_size, response_only_loss=response_only
    )
    val_in, val_tg, val_mask = load_split(
        tensor_dir, "validation", vocab_size=tok.vocab_size, response_only_loss=response_only
    )

    final_ckpt = EFFICIENT_CKPT if lane == "efficient" else DEEP_CKPT
    run_dir = RUNS_DIR / lane
    run_dir.mkdir(parents=True, exist_ok=True)

    start_step = 0
    history: list[dict[str, Any]] = []
    torch.manual_seed(int(campaign["seed"]))
    model = TransformerLanguageModel(
        tok.vocab_size,
        **model_cfg,
        rid_adapter=bool(args.rid_adapter),
        rid_rank=int(args.rid_rank),
        rid_alpha=float(args.rid_alpha),
        rid_dropout=float(args.rid_dropout),
    ).to(device)
    model.set_rid_metrics(
        rid_residual=float(args.rid_residual),
        uml_nesting=float(args.uml_nesting),
        uml_math=float(args.uml_math),
    )
    if args.rid_role_scales:
        scales = json.loads(str(args.rid_role_scales))
        if not isinstance(scales, dict):
            raise ValueError("sandbox_rid_role_scales_must_be_object")
        model.set_rid_role_scales({str(k): float(v) for k, v in scales.items()})
    wd = float(campaign.get("weight_decay", CODEX_WEIGHT_DECAY))
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(campaign["lr"]), weight_decay=wd)
    max_grad = float(campaign.get("max_grad_norm", CODEX_MAX_GRAD_NORM))

    if args.resume and args.warm_start:
        raise ValueError("sandbox_resume_and_warm_start_mutually_exclusive")

    if args.warm_start:
        ws_path = Path(args.warm_start)
        payload = torch.load(ws_path, map_location="cpu", weights_only=False)
        if not isinstance(payload, dict) or "model_state_dict" not in payload:
            raise ValueError(f"sandbox_warm_start_invalid:{ws_path}")
        if str(payload.get("vocab_sha256", "")) != tok.vocab_sha256:
            raise ValueError("sandbox_warm_start_vocab_mismatch")
        load_plant_state_dict(
            model,
            payload["model_state_dict"],
            strict=False,
            config=model_cfg,
        )
        dataset_meta["warm_start"] = str(ws_path).replace("\\", "/")
        model.to(device)
    elif args.resume:
        payload = torch.load(Path(args.resume), map_location="cpu", weights_only=False)
        model.load_state_dict(payload["model_state_dict"], strict=False)
        rid_mode_hint = args.rid_train_mode or ("adapter_only" if args.rid_adapter_only else None)
        load_opt = (
            phase == "default"
            and rid_mode_hint not in ("adapter_only", "hybrid", "last_n")
            and "optimizer_state_dict" in payload
        )
        if load_opt:
            optimizer.load_state_dict(payload["optimizer_state_dict"])
        elif phase in ("teacher", "divergent"):
            # Fresh optimizer for phase boundary (Codex-style continuation).
            wd = float(campaign.get("weight_decay", CODEX_WEIGHT_DECAY))
            optimizer = torch.optim.AdamW(model.parameters(), lr=float(campaign["lr"]), weight_decay=wd)
        start_step = int((payload.get("train") or {}).get("steps_completed") or 0)
        history = list(payload.get("training_history") or [])
        model.to(device)

    teacher: TransformerLanguageModel | None = None
    anchor_weight = float(campaign.get("anchor_weight") or 0.0)
    use_teacher = teacher_from_resume or teacher_path is not None
    if weighted_mode == "teacher_confidence":
        use_teacher = True
        if teacher_path is None and not teacher_from_resume:
            teacher_from_resume = True
    if use_teacher:
        if train_mask is None:
            raise ValueError("sandbox_teacher_anchor_requires_response_masks")
        if teacher_from_resume:
            teacher = _clone_frozen_teacher(model, model_cfg)
            dataset_meta["teacher_anchor"] = "resume_snapshot"
        else:
            if teacher_path is None or not teacher_path.is_file():
                raise FileNotFoundError(f"sandbox_teacher_anchor_missing:{teacher_path}")
            teacher = _load_frozen_teacher(
                teacher_path,
                tok,
                model_cfg,
                device,
                rid_adapter=bool(args.rid_adapter),
                rid_rank=int(args.rid_rank),
                rid_alpha=float(args.rid_alpha),
                rid_dropout=float(args.rid_dropout),
            )
            dataset_meta["teacher_anchor"] = str(teacher_path).replace("\\", "/")
        if anchor_weight <= 0.0:
            anchor_weight = 0.31
        dataset_meta["anchor_weight"] = anchor_weight

    model.train()
    rid_train_mode = args.rid_train_mode
    if rid_train_mode is None and args.rid_adapter_only:
        rid_train_mode = "adapter_only"
    if rid_train_mode is None:
        rid_train_mode = "full" if args.rid_adapter else None
    if rid_train_mode == "adapter_only":
        for name, parameter in model.named_parameters():
            parameter.requires_grad = "rid_" in name
        frozen = [n for n, p in model.named_parameters() if not p.requires_grad]
        if len(frozen) == 0:
            raise ValueError("sandbox_rid_adapter_only_no_frozen_params")
        optimizer = torch.optim.AdamW(
            [p for p in model.parameters() if p.requires_grad],
            lr=float(campaign["lr"]),
            weight_decay=wd,
        )
    elif rid_train_mode == "hybrid":
        adapter_params = [p for n, p in model.named_parameters() if "rid_" in n and p.requires_grad]
        base_params = [p for n, p in model.named_parameters() if "rid_" not in n and p.requires_grad]
        if not adapter_params:
            raise ValueError("sandbox_rid_hybrid_no_adapter_params")
        base_lr = float(args.rid_base_lr) if args.rid_base_lr is not None else float(campaign["lr"]) * 0.25
        optimizer = torch.optim.AdamW(
            [
                {"params": adapter_params, "lr": float(campaign["lr"])},
                {"params": base_params, "lr": base_lr},
            ],
            weight_decay=wd,
        )
        dataset_meta["rid_base_lr"] = base_lr
    elif rid_train_mode == "last_n":
        last_n = max(1, int(args.rid_unfreeze_last_n))
        n_layers = len(model.blocks)
        thaw_from = max(0, n_layers - last_n)
        for parameter in model.parameters():
            parameter.requires_grad = False
        for name, parameter in model.named_parameters():
            if "rid_" in name:
                parameter.requires_grad = True
        for idx in range(thaw_from, n_layers):
            for parameter in model.blocks[idx].parameters():
                parameter.requires_grad = True
        for parameter in model.final_layer_norm.parameters():
            parameter.requires_grad = True
        for parameter in model.lm_head.parameters():
            parameter.requires_grad = True
        adapter_params = [p for n, p in model.named_parameters() if "rid_" in n and p.requires_grad]
        base_params = [p for n, p in model.named_parameters() if "rid_" not in n and p.requires_grad]
        if not adapter_params or not base_params:
            raise ValueError("sandbox_rid_last_n_param_groups_empty")
        base_lr = float(args.rid_base_lr) if args.rid_base_lr is not None else float(campaign["lr"]) * 0.35
        optimizer = torch.optim.AdamW(
            [
                {"params": adapter_params, "lr": float(campaign["lr"])},
                {"params": base_params, "lr": base_lr},
            ],
            weight_decay=wd,
        )
        dataset_meta["rid_base_lr"] = base_lr
        dataset_meta["rid_unfreeze_last_n"] = last_n
        dataset_meta["rid_thaw_from_block"] = thaw_from
    if rid_train_mode:
        dataset_meta["rid_train_mode"] = rid_train_mode
        dataset_meta["rid_residual_feedback"] = bool(args.rid_residual_feedback)
        dataset_meta["pid_lr_couple"] = bool(args.pid_lr_couple and args.rid_adapter)
        if hasattr(model, "rid_control_receipt"):
            dataset_meta["rid_control"] = model.rid_control_receipt()
    batch_size = int(campaign["batch_size"])
    target_steps = int(campaign["steps"])
    ckpt_every = int(campaign.get("checkpoint_every", 100))
    eval_every = int(campaign.get("eval_every", 100))
    sample_prompt = "User: Hello, Viv.\nViv:" if dataset_meta.get("source", "").startswith("codex") else str(
        campaign.get("sample_prompt", "viv ")
    )
    base_lrs = [float(group["lr"]) for group in optimizer.param_groups]
    pid_couple = bool(args.pid_lr_couple and args.rid_adapter)
    last_pid_u = 0.0
    last_lr_scale = 1.0
    if hasattr(model, "_rid_monitor") and model._rid_monitor is not None:
        last_pid_u = float(model._rid_monitor.last_u)

    if start_step == 0:
        history.append(
            {
                "step": 0,
                "train": evaluate_split(
                    model, train_in, train_tg, device=device, batch_size=batch_size, loss_masks=train_mask
                ),
            }
        )

    n_train = int(train_in.shape[0])
    gen = torch.Generator(device="cpu")
    gen.manual_seed(int(campaign["seed"]) + start_step)

    for step in range(start_step + 1, target_steps + 1):
        idx = torch.randint(0, n_train, (batch_size,), generator=gen)
        batch_in = train_in[idx].to(device)
        batch_tg = train_tg[idx].to(device)
        batch_mask = train_mask[idx].to(device) if train_mask is not None else None
        optimizer.zero_grad(set_to_none=True)
        logits = model(batch_in)
        teacher_logits: torch.Tensor | None = None
        token_weights: torch.Tensor | None = None
        if teacher is not None and batch_mask is not None:
            with torch.no_grad():
                teacher_logits = teacher(batch_in)
            if weighted_mode == "teacher_confidence":
                token_weights = _teacher_confidence_weights(
                    teacher_logits,
                    batch_tg,
                    batch_mask,
                    min_weight=float(args.weight_min),
                    max_weight=float(args.weight_max),
                    boilerplate_token_ids=boilerplate_token_ids,
                    boilerplate_scale=float(args.boilerplate_scale),
                )
                sft_loss, acc = weighted_masked_batch_loss(
                    model,
                    logits,
                    batch_tg,
                    batch_mask,
                    token_weights=token_weights,
                )
            else:
                sft_loss, acc = masked_batch_loss(model, logits, batch_tg, batch_mask)
        else:
            sft_loss, acc = masked_batch_loss(model, logits, batch_tg, batch_mask)
        total_loss = sft_loss
        batch_anchor_kl: float | None = None
        batch_weight_mean: float | None = None
        if token_weights is not None and batch_mask is not None:
            valid_w = token_weights[batch_mask.bool()]
            if valid_w.numel() > 0:
                batch_weight_mean = float(valid_w.mean().detach().cpu())
        if teacher is not None and batch_mask is not None and teacher_logits is not None:
            anchor_kl = teacher_anchor_kl(logits, teacher_logits, batch_mask)
            batch_anchor_kl = float(anchor_kl.detach().cpu())
            total_loss = sft_loss + (anchor_weight * anchor_kl)
        # PID→training couple: scale LR from last actuation before the step.
        if pid_couple:
            last_lr_scale = apply_pid_u_to_optimizer(
                optimizer,
                last_pid_u,
                base_lrs=base_lrs,
                min_scale=float(args.pid_lr_min_scale),
                max_scale=float(args.pid_lr_max_scale),
            )
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=max_grad)
        optimizer.step()
        if args.rid_residual_feedback and args.rid_adapter:
            model.update_rid_residual_from_loss(float(sft_loss.detach().cpu()))
            if hasattr(model, "_rid_monitor") and model._rid_monitor is not None:
                last_pid_u = float(model._rid_monitor.last_u)

        if step % eval_every == 0 or step == target_steps:
            val_m = evaluate_split(
                model, val_in, val_tg, device=device, batch_size=batch_size, loss_masks=val_mask
            )
            metrics: dict[str, Any] = {
                "step": step,
                "train_loss": float(total_loss.detach().cpu()),
                "train_sft_loss": float(sft_loss.detach().cpu()),
                "train_batch_acc": acc,
                "train": evaluate_split(
                    model, train_in, train_tg, device=device, batch_size=batch_size, loss_masks=train_mask
                ),
                "validation": val_m,
                "training_phase": phase,
                "anchor_weight": anchor_weight if teacher is not None else None,
                "loss_weighting": weighted_mode,
            }
            if batch_anchor_kl is not None:
                metrics["train_batch_teacher_kl"] = batch_anchor_kl
            if batch_weight_mean is not None:
                metrics["train_batch_weight_mean"] = batch_weight_mean
            if pid_couple:
                metrics["pid_u"] = last_pid_u
                metrics["pid_lr_scale"] = last_lr_scale
                if hasattr(model, "rid_control_receipt"):
                    metrics["rid_control"] = model.rid_control_receipt()
            if teacher is not None and val_mask is not None:
                metrics["validation_teacher_kl"] = evaluate_teacher_kl(
                    model,
                    teacher,
                    val_in,
                    device=device,
                    batch_size=batch_size,
                    loss_masks=val_mask,
                )
            history.append(metrics)
            teacher_kl_str = ""
            if metrics.get("validation_teacher_kl"):
                teacher_kl_str = f" val_teacher_kl={metrics['validation_teacher_kl']['teacher_kl']:.4f}"
            weight_str = ""
            if metrics.get("train_batch_weight_mean") is not None:
                weight_str = f" w_mean={metrics['train_batch_weight_mean']:.3f}"
            pid_str = ""
            if metrics.get("pid_lr_scale") is not None:
                pid_str = f" pid_u={metrics['pid_u']:.4f} lr_x={metrics['pid_lr_scale']:.3f}"
            print(
                f"VIV_SANDBOX_TRAIN lane={lane} phase={phase} step={step}/{target_steps} "
                f"loss={metrics['train_loss']:.4f} sft={metrics['train_sft_loss']:.4f} "
                f"val_nll={val_m['nll']:.4f} val_ppl={val_m['perplexity']:.3f} "
                f"val_acc={val_m['token_accuracy']:.4f}{teacher_kl_str}{weight_str}{pid_str} "
                f"dataset={dataset_meta.get('lane_id') or dataset_meta.get('source')}"
            )

        if step % ckpt_every == 0 or step == target_steps:
            ckpt_path = run_dir / f"checkpoint_step_{step:05d}.pt"
            _save_checkpoint(
                ckpt_path,
                model=model,
                optimizer=optimizer,
                tok=tok,
                lane=lane,
                step=step,
                history=history,
                campaign=campaign,
                dataset_meta=dataset_meta,
                model_cfg=model_cfg,
            )

    temp = float(campaign.get("sample_temperature", 0.0 if lane == "efficient" else 0.7))
    sample = _sample(
        model,
        tok,
        sample_prompt,
        device=device,
        max_new_tokens=int(campaign.get("sample_tokens", 96)),
        temperature=temp,
        seed=int(campaign["seed"]) + target_steps,
    )

    meta = _save_checkpoint(
        final_ckpt,
        model=model,
        optimizer=optimizer,
        tok=tok,
        lane=lane,
        step=target_steps,
        history=history,
        campaign=campaign,
        dataset_meta=dataset_meta,
        model_cfg=model_cfg,
    )

    run_manifest = {
        "schema_version": SCHEMA_CAMPAIGN,
        "sandbox_only": True,
        "originals_untouched": True,
        "status": "PASS",
        "lane": lane,
        "device": str(device),
        "steps_completed": target_steps,
        "campaign": campaign,
        "dataset": dataset_meta,
        "checkpoint": meta,
        "sample": sample,
        "hardware": detect_hardware(),
        "paths": {
            "final_checkpoint": str(final_ckpt).replace("\\", "/"),
            "run_dir": str(run_dir).replace("\\", "/"),
        },
    }
    manifest_path = run_dir / "train_latest.json"
    with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(run_manifest, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    (run_dir / "sample_latest.txt").write_text(sample + "\n", encoding="utf-8", newline="\n")

    print(
        f"VIV_SANDBOX_TRAIN_{lane.upper()}_PASS "
        f"steps={target_steps} fp={meta['weight_fingerprint'][:16]}... "
        f"sample={sample[:100]!r}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
