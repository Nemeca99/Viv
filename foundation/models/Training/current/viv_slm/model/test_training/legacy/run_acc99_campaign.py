#!/usr/bin/env python3
"""Accuracy campaign: --mode reach99 | hold99 (Phase A / Phase B)."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

SANDBOX = Path(__file__).resolve().parents[1]  # legacy home: parents[1] = test_training/
MODEL = SANDBOX.parent
PY = Path(r"L:\Continue\.venv\Scripts\python.exe")
EFF = SANDBOX / "checkpoints" / "efficient" / "specialist.pt"
DEEP = SANDBOX / "checkpoints" / "deep" / "specialist.pt"
RUNS = SANDBOX / "runs"
LOCK = RUNS / "acc99_lock.json"
PARENT_EFF = RUNS / "rid_breakthrough_continue_4450" / "hybrid_continue" / "efficient_final.pt"
PARENT_DEEP = RUNS / "rid_breakthrough_continue_4450" / "hybrid_continue" / "deep_final.pt"

if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))
if str(SANDBOX) not in sys.path:
    sys.path.insert(0, str(SANDBOX))

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import (  # noqa: E402
    IDENTITY_MODEL_CFG,
    evaluate_split,
    load_split,
    resolve_codex_dataset,
)
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402

PROBE_PROMPTS = (
    "User: Hello, Viv.\nViv:",
    "User: Who are you?\nViv:",
    "User: What should I do next?\nViv:",
)
EFF_ROLES = {"lm_head": 0.35, "ffn_in": 0.45, "ffn_out": 0.45, "attn_qkv_fused": 0.7, "generic": 0.8}
DEEP_ROLES = {
    "lm_head": 1.0,
    "ffn_in": 1.1,
    "ffn_out": 1.1,
    "attn_qkv_fused": 1.2,
    "attn_query": 1.15,
    "attn_key": 1.15,
    "attn_value": 1.15,
    "generic": 1.0,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _run(cmd: list[str]) -> None:
    print("RUN", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=str(MODEL))


def _eval(
    path: Path,
    *,
    rid_rank: int,
    rid_residual: float,
    uml_nesting: float,
    uml_math: float,
    role_scales: dict[str, float] | None,
) -> dict[str, float]:
    configure_plant_runtime(device="cuda")
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    _, vocab_path, tensor_dir = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    val_in, val_tg, val_mask = load_split(
        tensor_dir, "validation", vocab_size=tok.vocab_size, response_only_loss=True
    )
    payload = torch.load(path, map_location="cpu", weights_only=False)
    model = TransformerLanguageModel(
        tok.vocab_size,
        **IDENTITY_MODEL_CFG,
        rid_adapter=True,
        rid_rank=rid_rank,
        rid_alpha=16.0,
        rid_dropout=0.05,
    ).to(device)
    model.load_state_dict(payload["model_state_dict"], strict=False)
    model.set_rid_metrics(rid_residual=rid_residual, uml_nesting=uml_nesting, uml_math=uml_math)
    if role_scales:
        model.set_rid_role_scales(role_scales)
    model.eval()
    val = evaluate_split(model, val_in, val_tg, device=device, batch_size=64, loss_masks=val_mask)
    return {
        "nll": float(val["nll"]),
        "acc": float(val["token_accuracy"]),
        "ppl": float(val["perplexity"]),
    }


def _probe(path: Path, *, rid_rank: int, lane: str) -> dict[str, str]:
    configure_plant_runtime(device="cuda")
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    _, vocab_path, _ = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    payload = torch.load(path, map_location="cpu", weights_only=False)
    model = TransformerLanguageModel(
        tok.vocab_size,
        **IDENTITY_MODEL_CFG,
        rid_adapter=True,
        rid_rank=rid_rank,
        rid_alpha=16.0,
        rid_dropout=0.05,
    ).to(device)
    model.load_state_dict(payload["model_state_dict"], strict=False)
    model.set_rid_metrics(rid_residual=0.35, uml_nesting=2.0, uml_math=2.0)
    model.eval()
    temp = 0.0 if lane == "efficient" else 0.7
    out: dict[str, str] = {}
    for prompt in PROBE_PROMPTS:
        ids = torch.tensor([tok.encode(prompt)], dtype=torch.long, device=device)
        with torch.no_grad():
            gen = model.generate(ids, max_new_tokens=96, temperature=temp, use_kv_cache=True)
        out[prompt] = tok.decode(gen[0].tolist())
    return out


def _probes_ok(probes: dict[str, dict[str, str]]) -> bool:
    for lane_texts in probes.values():
        joined = " ".join(lane_texts.values()).lower()
        if "aios" not in joined and "viv" not in joined and "hello" not in joined:
            return False
        if joined.count("<end>") > 40:
            return False
    return True


def _phase_a_gates(
    parent: dict[str, dict[str, float]],
    cand: dict[str, dict[str, float]],
    probes: dict[str, dict[str, str]],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if min(cand["efficient"]["acc"], cand["deep"]["acc"]) + 1e-12 < min(
        parent["efficient"]["acc"], parent["deep"]["acc"]
    ):
        reasons.append("min_acc_not_improved")
    if cand["efficient"]["nll"] - parent["efficient"]["nll"] > 0.02:
        reasons.append("efficient_nll_collapse")
    if cand["deep"]["nll"] - parent["deep"]["nll"] > 0.02:
        reasons.append("deep_nll_collapse")
    if abs(cand["efficient"]["acc"] - cand["deep"]["acc"]) > 0.015:
        reasons.append("lane_acc_gap")
    if not _probes_ok(probes):
        reasons.append("probe_collapse")
    return len(reasons) == 0, reasons


def _phase_b_gates(cand: dict[str, dict[str, float]], parent_nll_sum: float) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if cand["efficient"]["acc"] < 0.99 or cand["deep"]["acc"] < 0.99:
        reasons.append("acc_floor_breach")
    nll_sum = cand["efficient"]["nll"] + cand["deep"]["nll"]
    if nll_sum + 1e-12 >= parent_nll_sum:
        reasons.append("nll_not_improved")
    return len(reasons) == 0, reasons


def _train(lane: str, resume: Path, steps: int, cfg: dict[str, Any]) -> None:
    cmd = [
        str(PY),
        "-B",
        str(SANDBOX / "train_specialist.py"),
        "--lane",
        lane,
        "--codex-identity",
        "v61",
        "--device",
        "cuda",
        "--resume",
        str(resume),
        "--steps",
        str(steps),
        "--training-phase",
        "default",
        "--learning-rate",
        str(cfg["lr"]),
        "--rid-adapter",
        "--rid-rank",
        str(cfg["rid_rank"]),
        "--rid-alpha",
        "16",
        "--rid-dropout",
        "0.05",
        "--rid-train-mode",
        str(cfg["train_mode"]),
        "--rid-residual",
        str(cfg["rid_residual"]),
        "--uml-nesting",
        str(cfg["uml_nesting"]),
        "--uml-math",
        str(cfg["uml_math"]),
        "--rid-residual-feedback",
    ]
    if cfg.get("base_lr") is not None:
        cmd.extend(["--rid-base-lr", str(cfg["base_lr"])])
    if cfg.get("role_scales"):
        cmd.extend(["--rid-role-scales", json.dumps(cfg["role_scales"], separators=(",", ":"))])
    if cfg.get("teacher_from_resume"):
        cmd.append("--teacher-from-resume")
        cmd.extend(["--anchor-weight", str(cfg.get("anchor_weight", 0.18))])
    _run(cmd)


def _maybe_seal_lock(metrics: dict[str, dict[str, float]], arm_dir: Path) -> bool:
    if metrics["efficient"]["acc"] >= 0.99 and metrics["deep"]["acc"] >= 0.99:
        lock = {
            "status": "LOCKED",
            "sealed_at": _now(),
            "metrics": metrics,
            "checkpoints": {
                "efficient": str((arm_dir / "efficient_final.pt")).replace("\\", "/"),
                "deep": str((arm_dir / "deep_final.pt")).replace("\\", "/"),
            },
        }
        with LOCK.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(lock, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        shutil.copy2(arm_dir / "efficient_final.pt", EFF)
        shutil.copy2(arm_dir / "deep_final.pt", DEEP)
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("reach99", "hold99"), required=True)
    parser.add_argument("--target-steps", type=int, default=5000)
    parser.add_argument("--stage", default="S1")
    args = parser.parse_args()

    if args.mode == "hold99" and not LOCK.is_file():
        raise SystemExit("hold99_requires_acc99_lock_json")

    if not PARENT_EFF.is_file() or not PARENT_DEEP.is_file():
        raise FileNotFoundError("acc99_parent_missing_hybrid_continue")

    root = RUNS / f"acc99_{args.mode}_{args.stage}"
    root.mkdir(parents=True, exist_ok=True)
    event_log = root / "events.jsonl"
    backup_eff = root / "pre_efficient.pt"
    backup_deep = root / "pre_deep.pt"
    if EFF.is_file():
        shutil.copy2(EFF, backup_eff)
    if DEEP.is_file():
        shutil.copy2(DEEP, backup_deep)

    start_steps = int(
        torch.load(PARENT_EFF, map_location="cpu", weights_only=False)["train"]["steps_completed"]
    )
    target_steps = int(args.target_steps)
    if start_steps >= target_steps:
        raise RuntimeError(f"acc99_start_not_below_target:{start_steps}>={target_steps}")

    arms = [
        {
            "arm_id": "s1_hybrid_deep_kl",
            "efficient": {
                "rid_rank": 8,
                "lr": 8e-6,
                "base_lr": 1.5e-6,
                "rid_residual": 0.3,
                "uml_nesting": 2.0,
                "uml_math": 2.0,
                "train_mode": "hybrid",
                "role_scales": EFF_ROLES,
            },
            "deep": {
                "rid_rank": 8,
                "lr": 7e-6,
                "base_lr": 1.5e-6,
                "rid_residual": 0.35,
                "uml_nesting": 3.0,
                "uml_math": 3.0,
                "train_mode": "hybrid",
                "role_scales": DEEP_ROLES,
                "teacher_from_resume": True,
                "anchor_weight": 0.18,
            },
        }
    ]

    _append_jsonl(
        event_log,
        {
            "ts": _now(),
            "event": "campaign_start",
            "mode": args.mode,
            "stage": args.stage,
            "start_steps": start_steps,
            "target_steps": target_steps,
        },
    )

    try:
        parent = {
            "efficient": _eval(
                PARENT_EFF,
                rid_rank=8,
                rid_residual=0.3,
                uml_nesting=2.0,
                uml_math=2.0,
                role_scales=EFF_ROLES,
            ),
            "deep": _eval(
                PARENT_DEEP,
                rid_rank=8,
                rid_residual=0.35,
                uml_nesting=3.0,
                uml_math=3.0,
                role_scales=DEEP_ROLES,
            ),
        }
        results: list[dict[str, Any]] = []
        for arm in arms:
            arm_id = arm["arm_id"]
            arm_dir = root / arm_id
            arm_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PARENT_EFF, EFF)
            shutil.copy2(PARENT_DEEP, DEEP)
            for lane in ("efficient", "deep"):
                _train(lane, EFF if lane == "efficient" else DEEP, target_steps, arm[lane])
                shutil.copy2(EFF if lane == "efficient" else DEEP, arm_dir / f"{lane}_final.pt")

            metrics = {
                "efficient": _eval(
                    arm_dir / "efficient_final.pt",
                    rid_rank=int(arm["efficient"]["rid_rank"]),
                    rid_residual=float(arm["efficient"]["rid_residual"]),
                    uml_nesting=float(arm["efficient"]["uml_nesting"]),
                    uml_math=float(arm["efficient"]["uml_math"]),
                    role_scales=arm["efficient"].get("role_scales"),
                ),
                "deep": _eval(
                    arm_dir / "deep_final.pt",
                    rid_rank=int(arm["deep"]["rid_rank"]),
                    rid_residual=float(arm["deep"]["rid_residual"]),
                    uml_nesting=float(arm["deep"]["uml_nesting"]),
                    uml_math=float(arm["deep"]["uml_math"]),
                    role_scales=arm["deep"].get("role_scales"),
                ),
            }
            probes = {
                "efficient": _probe(
                    arm_dir / "efficient_final.pt",
                    rid_rank=int(arm["efficient"]["rid_rank"]),
                    lane="efficient",
                ),
                "deep": _probe(
                    arm_dir / "deep_final.pt", rid_rank=int(arm["deep"]["rid_rank"]), lane="deep"
                ),
            }
            if args.mode == "reach99":
                accept, reasons = _phase_a_gates(parent, metrics, probes)
            else:
                parent_nll = parent["efficient"]["nll"] + parent["deep"]["nll"]
                accept, reasons = _phase_b_gates(metrics, parent_nll)

            item = {
                "arm_id": arm_id,
                "metrics": metrics,
                "min_acc": min(metrics["efficient"]["acc"], metrics["deep"]["acc"]),
                "accept": accept,
                "reject_reasons": reasons,
                "probes": probes,
                "delta_vs_parent": {
                    "efficient": {
                        "acc": metrics["efficient"]["acc"] - parent["efficient"]["acc"],
                        "nll": metrics["efficient"]["nll"] - parent["efficient"]["nll"],
                    },
                    "deep": {
                        "acc": metrics["deep"]["acc"] - parent["deep"]["acc"],
                        "nll": metrics["deep"]["nll"] - parent["deep"]["nll"],
                    },
                },
            }
            results.append(item)
            _append_jsonl(
                event_log,
                {
                    "ts": _now(),
                    "event": "arm_result",
                    "arm_id": arm_id,
                    "min_acc": item["min_acc"],
                    "accept": accept,
                    "reject_reasons": reasons,
                    "metrics": metrics,
                },
            )
            print(
                f"ACC99_RESULT mode={args.mode} arm={arm_id} "
                f"min_acc={item['min_acc']:.5f} accept={accept} reasons={reasons}",
                flush=True,
            )

            locked = _maybe_seal_lock(metrics, arm_dir)
            if accept:
                shutil.copy2(arm_dir / "efficient_final.pt", EFF)
                shutil.copy2(arm_dir / "deep_final.pt", DEEP)
                pin = "pinned_accepted"
            else:
                shutil.copy2(PARENT_EFF, EFF)
                shutil.copy2(PARENT_DEEP, DEEP)
                pin = "retained_parent"
            if locked:
                pin = "acc99_lock_sealed"

            # Plateau note vs parent for Stage S1
            plateau = abs(item["min_acc"] - min(parent["efficient"]["acc"], parent["deep"]["acc"])) < 0.001

        best = max(results, key=lambda r: (bool(r["accept"]), r["min_acc"]))
        summary = {
            "status": "PASS",
            "mode": args.mode,
            "stage": args.stage,
            "start_steps": start_steps,
            "target_steps": target_steps,
            "parent": parent,
            "results": results,
            "best": best,
            "pin_policy": pin,
            "locked": LOCK.is_file(),
            "plateau_vs_parent": plateau,
            "finished_at": _now(),
        }
        latest = RUNS / f"acc99_{args.mode}_{args.stage}_latest.json"
        for path in (latest, root / "summary.json"):
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
        print(
            f"ACC99_PASS mode={args.mode} stage={args.stage} "
            f"min_acc={best['min_acc']:.5f} accept={best['accept']} lock={LOCK.is_file()}",
            flush=True,
        )
        return 0
    except Exception as exc:
        if backup_eff.is_file():
            shutil.copy2(backup_eff, EFF)
        if backup_deep.is_file():
            shutil.copy2(backup_deep, DEEP)
        _append_jsonl(event_log, {"ts": _now(), "event": "campaign_fail", "error": repr(exc)})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
