#!/usr/bin/env python3
"""Performance-seeking RID breakthrough A/B (trainable gains, hybrid, asymmetric, offspring)."""
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
SWEEP_LATEST = RUNS / "rid_metric_sweep_4200_latest.json"
SWEEP_CKPT = RUNS / "rid_metric_sweep_4200" / "checkpoints"
BASE_EFF = RUNS / "rid_metric_sweep_4200" / "efficient_base.pt"
BASE_DEEP = RUNS / "rid_metric_sweep_4200" / "deep_base.pt"

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _run(cmd: list[str]) -> None:
    print("RUN", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=str(MODEL))


def _eval_checkpoint(
    path: Path,
    *,
    rid_rank: int,
    rid_residual: float,
    uml_nesting: float,
    uml_math: float,
    role_scales: dict[str, float] | None = None,
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
    model.set_rid_metrics(
        rid_residual=rid_residual,
        uml_nesting=uml_nesting,
        uml_math=uml_math,
    )
    if role_scales:
        model.set_rid_role_scales(role_scales)
    model.eval()
    val = evaluate_split(model, val_in, val_tg, device=device, batch_size=64, loss_masks=val_mask)
    return {
        "nll": float(val["nll"]),
        "acc": float(val["token_accuracy"]),
        "ppl": float(val["perplexity"]),
    }


def _baseline_metrics() -> dict[str, dict[str, float]]:
    # Dense base (no adapter) evaluated via rid_rank>0 but zero metrics => gain~0.
    return {
        "efficient": _eval_checkpoint(
            BASE_EFF, rid_rank=4, rid_residual=0.0, uml_nesting=0.0, uml_math=0.0
        ),
        "deep": _eval_checkpoint(
            BASE_DEEP, rid_rank=4, rid_residual=0.0, uml_nesting=0.0, uml_math=0.0
        ),
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
        text = tok.decode(gen[0].tolist())
        out[prompt] = text
    return out


def _merge_offspring(
    *,
    lane: str,
    run_ids: list[str],
    out_path: Path,
    rid_rank: int,
) -> None:
    base = BASE_EFF if lane == "efficient" else BASE_DEEP
    base_payload = torch.load(base, map_location="cpu", weights_only=False)
    _, vocab_path, _ = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    model = TransformerLanguageModel(
        tok.vocab_size,
        **IDENTITY_MODEL_CFG,
        rid_adapter=True,
        rid_rank=rid_rank,
        rid_alpha=16.0,
        rid_dropout=0.05,
    )
    model.load_state_dict(base_payload["model_state_dict"], strict=False)
    adapters: list[dict[str, torch.Tensor]] = []
    for run_id in run_ids:
        ckpt = SWEEP_CKPT / f"{run_id}_{lane}.pt"
        if not ckpt.is_file():
            raise FileNotFoundError(f"offspring_missing:{ckpt}")
        payload = torch.load(ckpt, map_location="cpu", weights_only=False)
        adapters.append(
            {k: v for k, v in payload["model_state_dict"].items() if "rid_" in k and torch.is_tensor(v)}
        )
    if not adapters:
        raise ValueError("offspring_no_adapters")
    merged = model.state_dict()
    keys = sorted(set().union(*(a.keys() for a in adapters)))
    for key in keys:
        tensors = [a[key].float() for a in adapters if key in a]
        if not tensors:
            continue
        if any(t.shape != tensors[0].shape for t in tensors):
            continue  # skip rank-mismatched tensors
        avg = torch.stack(tensors, dim=0).mean(dim=0)
        if key in merged and merged[key].shape == avg.shape:
            merged[key] = avg.to(dtype=merged[key].dtype)
    model.load_state_dict(merged, strict=False)
    out = {
        "model_state_dict": model.state_dict(),
        "vocab_sha256": base_payload.get("vocab_sha256"),
        "train": {"steps_completed": int((base_payload.get("train") or {}).get("steps_completed") or 0)},
        "training_history": list(base_payload.get("training_history") or []),
        "offspring_merge": {"lane": lane, "parents": run_ids, "rid_rank": rid_rank},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(out, out_path)


def _score(eff: dict[str, float], deep: dict[str, float], *, acc_floor: float) -> float:
    if eff["acc"] < acc_floor or deep["acc"] < acc_floor:
        return 1e9
    return float(eff["nll"] + deep["nll"])


def _arm_train(
    *,
    lane: str,
    resume: Path,
    steps: int,
    lr: float,
    rid_rank: int,
    rid_residual: float,
    uml_nesting: float,
    uml_math: float,
    train_mode: str,
    base_lr: float | None,
    residual_feedback: bool,
    role_scales: dict[str, float] | None,
) -> None:
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
        str(lr),
        "--rid-adapter",
        "--rid-rank",
        str(rid_rank),
        "--rid-alpha",
        "16",
        "--rid-dropout",
        "0.05",
        "--rid-train-mode",
        train_mode,
        "--rid-residual",
        str(rid_residual),
        "--uml-nesting",
        str(uml_nesting),
        "--uml-math",
        str(uml_math),
    ]
    if residual_feedback:
        cmd.append("--rid-residual-feedback")
    if base_lr is not None:
        cmd.extend(["--rid-base-lr", str(base_lr)])
    if role_scales:
        cmd.extend(["--rid-role-scales", json.dumps(role_scales, separators=(",", ":"))])
    _run(cmd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-steps", type=int, default=4200)
    parser.add_argument("--acc-floor", type=float, default=0.955)
    parser.add_argument("--top-k-merge", type=int, default=5)
    args = parser.parse_args()

    if not BASE_EFF.is_file() or not BASE_DEEP.is_file():
        raise FileNotFoundError("breakthrough_base_missing")
    if not SWEEP_LATEST.is_file():
        raise FileNotFoundError("breakthrough_sweep_latest_missing")

    root = RUNS / "rid_breakthrough"
    root.mkdir(parents=True, exist_ok=True)
    event_log = root / "events.jsonl"
    backup_eff = root / "pre_breakthrough_efficient.pt"
    backup_deep = root / "pre_breakthrough_deep.pt"
    if EFF.is_file():
        shutil.copy2(EFF, backup_eff)
    if DEEP.is_file():
        shutil.copy2(DEEP, backup_deep)

    start_steps = int(
        torch.load(BASE_EFF, map_location="cpu", weights_only=False)["train"]["steps_completed"]
    )
    target_steps = int(args.target_steps)
    sweep = json.loads(SWEEP_LATEST.read_text(encoding="utf-8"))
    top_k = list(sweep.get("top_k") or [])[: int(args.top_k_merge)]
    # Prefer same-rank parents for merge (rank 4 winners dominate prior sweep).
    merge_rank = int(top_k[0]["cfg"]["rid_rank"]) if top_k else 4
    merge_ids = [str(item["run_id"]) for item in top_k if int(item["cfg"]["rid_rank"]) == merge_rank]
    if len(merge_ids) < 2:
        merge_ids = [str(item["run_id"]) for item in top_k]

    eff_roles = {"lm_head": 0.35, "ffn_in": 0.45, "ffn_out": 0.45, "attn_qkv_fused": 0.7, "generic": 0.8}
    deep_roles = {
        "lm_head": 1.0,
        "ffn_in": 1.1,
        "ffn_out": 1.1,
        "attn_qkv_fused": 1.2,
        "attn_query": 1.15,
        "attn_key": 1.15,
        "attn_value": 1.15,
        "generic": 1.0,
    }

    arms: list[dict[str, Any]] = [
        {
            "arm_id": "asymmetric_trainable",
            "efficient": {
                "rid_rank": 4,
                "lr": 5e-6,
                "rid_residual": 0.25,
                "uml_nesting": 0.0,
                "uml_math": 0.0,
                "train_mode": "adapter_only",
                "base_lr": None,
                "residual_feedback": True,
                "role_scales": eff_roles,
            },
            "deep": {
                "rid_rank": 16,
                "lr": 7e-6,
                "rid_residual": 0.45,
                "uml_nesting": 4.0,
                "uml_math": 4.0,
                "train_mode": "adapter_only",
                "base_lr": None,
                "residual_feedback": True,
                "role_scales": deep_roles,
            },
        },
        {
            "arm_id": "hybrid_full",
            "efficient": {
                "rid_rank": 8,
                "lr": 1e-5,
                "rid_residual": 0.3,
                "uml_nesting": 2.0,
                "uml_math": 2.0,
                "train_mode": "hybrid",
                "base_lr": 2e-6,
                "residual_feedback": True,
                "role_scales": eff_roles,
            },
            "deep": {
                "rid_rank": 8,
                "lr": 1e-5,
                "rid_residual": 0.35,
                "uml_nesting": 3.0,
                "uml_math": 3.0,
                "train_mode": "hybrid",
                "base_lr": 2.5e-6,
                "residual_feedback": True,
                "role_scales": deep_roles,
            },
        },
        {
            "arm_id": "offspring_merge_r4",
            "merge": {"rank": merge_rank, "parents": merge_ids},
            "efficient": {
                "rid_rank": merge_rank,
                "lr": 5e-6,
                "rid_residual": 0.25,
                "uml_nesting": 1.0,
                "uml_math": 1.0,
                "train_mode": "adapter_only",
                "base_lr": None,
                "residual_feedback": True,
                "role_scales": eff_roles,
            },
            "deep": {
                "rid_rank": merge_rank,
                "lr": 5e-6,
                "rid_residual": 0.3,
                "uml_nesting": 2.0,
                "uml_math": 2.0,
                "train_mode": "adapter_only",
                "base_lr": None,
                "residual_feedback": True,
                "role_scales": deep_roles,
            },
        },
    ]

    _append_jsonl(
        event_log,
        {
            "ts": _now_iso(),
            "event": "breakthrough_start",
            "start_steps": start_steps,
            "target_steps": target_steps,
            "arms": [a["arm_id"] for a in arms],
            "merge_parents": merge_ids,
        },
    )

    try:
        baseline = _baseline_metrics()
        results: list[dict[str, Any]] = []
        for arm in arms:
            arm_id = str(arm["arm_id"])
            arm_dir = root / arm_id
            arm_dir.mkdir(parents=True, exist_ok=True)
            _append_jsonl(event_log, {"ts": _now_iso(), "event": "arm_start", "arm_id": arm_id})

            if arm_id.startswith("offspring_merge"):
                merge_cfg = arm["merge"]
                for lane in ("efficient", "deep"):
                    merged_path = arm_dir / f"{lane}_merged.pt"
                    _merge_offspring(
                        lane=lane,
                        run_ids=list(merge_cfg["parents"]),
                        out_path=merged_path,
                        rid_rank=int(merge_cfg["rank"]),
                    )
                    shutil.copy2(merged_path, EFF if lane == "efficient" else DEEP)
            else:
                shutil.copy2(BASE_EFF, EFF)
                shutil.copy2(BASE_DEEP, DEEP)

            for lane in ("efficient", "deep"):
                cfg = arm[lane]
                _arm_train(
                    lane=lane,
                    resume=EFF if lane == "efficient" else DEEP,
                    steps=target_steps,
                    lr=float(cfg["lr"]),
                    rid_rank=int(cfg["rid_rank"]),
                    rid_residual=float(cfg["rid_residual"]),
                    uml_nesting=float(cfg["uml_nesting"]),
                    uml_math=float(cfg["uml_math"]),
                    train_mode=str(cfg["train_mode"]),
                    base_lr=cfg.get("base_lr"),
                    residual_feedback=bool(cfg["residual_feedback"]),
                    role_scales=cfg.get("role_scales"),
                )
                shutil.copy2(EFF if lane == "efficient" else DEEP, arm_dir / f"{lane}_final.pt")

            eff_cfg = arm["efficient"]
            deep_cfg = arm["deep"]
            eff_m = _eval_checkpoint(
                arm_dir / "efficient_final.pt",
                rid_rank=int(eff_cfg["rid_rank"]),
                rid_residual=float(eff_cfg["rid_residual"]),
                uml_nesting=float(eff_cfg["uml_nesting"]),
                uml_math=float(eff_cfg["uml_math"]),
                role_scales=eff_cfg.get("role_scales"),
            )
            deep_m = _eval_checkpoint(
                arm_dir / "deep_final.pt",
                rid_rank=int(deep_cfg["rid_rank"]),
                rid_residual=float(deep_cfg["rid_residual"]),
                uml_nesting=float(deep_cfg["uml_nesting"]),
                uml_math=float(deep_cfg["uml_math"]),
                role_scales=deep_cfg.get("role_scales"),
            )
            probes = {
                "efficient": _probe(
                    arm_dir / "efficient_final.pt", rid_rank=int(eff_cfg["rid_rank"]), lane="efficient"
                ),
                "deep": _probe(arm_dir / "deep_final.pt", rid_rank=int(deep_cfg["rid_rank"]), lane="deep"),
            }
            item = {
                "arm_id": arm_id,
                "efficient": eff_m,
                "deep": deep_m,
                "score": _score(eff_m, deep_m, acc_floor=float(args.acc_floor)),
                "delta_vs_baseline": {
                    "efficient": {
                        "nll": eff_m["nll"] - baseline["efficient"]["nll"],
                        "acc": eff_m["acc"] - baseline["efficient"]["acc"],
                    },
                    "deep": {
                        "nll": deep_m["nll"] - baseline["deep"]["nll"],
                        "acc": deep_m["acc"] - baseline["deep"]["acc"],
                    },
                },
                "probes": probes,
                "cfg": {
                    "efficient": {k: v for k, v in eff_cfg.items() if k != "role_scales"},
                    "deep": {k: v for k, v in deep_cfg.items() if k != "role_scales"},
                    "merge": arm.get("merge"),
                },
            }
            results.append(item)
            _append_jsonl(
                event_log,
                {
                    "ts": _now_iso(),
                    "event": "arm_result",
                    "arm_id": arm_id,
                    "score": item["score"],
                    "efficient": eff_m,
                    "deep": deep_m,
                    "delta_vs_baseline": item["delta_vs_baseline"],
                },
            )
            print(
                f"BREAKTHROUGH_RESULT {arm_id} "
                f"eff_nll={eff_m['nll']:.5f} deep_nll={deep_m['nll']:.5f} "
                f"d_eff={item['delta_vs_baseline']['efficient']['nll']:+.6f} "
                f"d_deep={item['delta_vs_baseline']['deep']['nll']:+.6f}",
                flush=True,
            )

        results_sorted = sorted(results, key=lambda r: r["score"])
        winner = results_sorted[0]
        # Pin winner to active specialist paths.
        win_dir = root / str(winner["arm_id"])
        shutil.copy2(win_dir / "efficient_final.pt", EFF)
        shutil.copy2(win_dir / "deep_final.pt", DEEP)

        summary = {
            "status": "PASS",
            "start_steps": start_steps,
            "target_steps": target_steps,
            "baseline": baseline,
            "arms": results_sorted,
            "winner": winner,
            "prior_sweep_winner": sweep.get("winner"),
            "merge_parents": merge_ids,
            "pinned_to": {
                "efficient": str(EFF).replace("\\", "/"),
                "deep": str(DEEP).replace("\\", "/"),
            },
            "finished_at": _now_iso(),
        }
        latest = RUNS / "rid_breakthrough_latest.json"
        with latest.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        with (root / "summary.json").open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        _append_jsonl(
            event_log,
            {"ts": _now_iso(), "event": "breakthrough_pass", "winner": winner["arm_id"], "score": winner["score"]},
        )
        print(
            f"BREAKTHROUGH_PASS winner={winner['arm_id']} "
            f"eff_nll={winner['efficient']['nll']:.5f} deep_nll={winner['deep']['nll']:.5f}",
            flush=True,
        )
        return 0
    except Exception as exc:
        if backup_eff.is_file():
            shutil.copy2(backup_eff, EFF)
        if backup_deep.is_file():
            shutil.copy2(backup_deep, DEEP)
        _append_jsonl(
            event_log,
            {"ts": _now_iso(), "event": "breakthrough_fail", "error": repr(exc)},
        )
        fail = {
            "status": "FAIL",
            "error": repr(exc),
            "restored_from": {
                "efficient": str(backup_eff).replace("\\", "/"),
                "deep": str(backup_deep).replace("\\", "/"),
            },
            "finished_at": _now_iso(),
        }
        with (RUNS / "rid_breakthrough_latest.json").open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(fail, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
