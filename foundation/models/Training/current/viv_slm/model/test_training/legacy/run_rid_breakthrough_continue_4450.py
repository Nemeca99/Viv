#!/usr/bin/env python3
"""Continue past hybrid_full breakthrough: push 4200→4450 with KL floor / last-N arms."""
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
HYBRID_EFF = RUNS / "rid_breakthrough" / "hybrid_full" / "efficient_final.pt"
HYBRID_DEEP = RUNS / "rid_breakthrough" / "hybrid_full" / "deep_final.pt"
PRIOR = RUNS / "rid_breakthrough_latest.json"

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


def _score(eff: dict[str, float], deep: dict[str, float], *, acc_floor: float) -> float:
    if eff["acc"] < acc_floor or deep["acc"] < acc_floor:
        return 1e9
    return float(eff["nll"] + deep["nll"])


def _arm_train(lane: str, resume: Path, steps: int, cfg: dict[str, Any]) -> None:
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
    ]
    if cfg.get("residual_feedback"):
        cmd.append("--rid-residual-feedback")
    if cfg.get("base_lr") is not None:
        cmd.extend(["--rid-base-lr", str(cfg["base_lr"])])
    if cfg.get("unfreeze_last_n") is not None:
        cmd.extend(["--rid-unfreeze-last-n", str(cfg["unfreeze_last_n"])])
    if cfg.get("role_scales"):
        cmd.extend(["--rid-role-scales", json.dumps(cfg["role_scales"], separators=(",", ":"))])
    if cfg.get("teacher_from_resume"):
        cmd.append("--teacher-from-resume")
        cmd.extend(["--anchor-weight", str(cfg.get("anchor_weight", 0.18))])
    _run(cmd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-steps", type=int, default=4450)
    parser.add_argument("--acc-floor", type=float, default=0.955)
    args = parser.parse_args()

    if not HYBRID_EFF.is_file() or not HYBRID_DEEP.is_file():
        raise FileNotFoundError("continue_hybrid_parent_missing")
    if not PRIOR.is_file():
        raise FileNotFoundError("continue_prior_breakthrough_missing")

    prior = json.loads(PRIOR.read_text(encoding="utf-8"))
    parent = prior.get("winner") or {}
    parent_metrics = {
        "efficient": dict(parent.get("efficient") or {}),
        "deep": dict(parent.get("deep") or {}),
    }

    root = RUNS / "rid_breakthrough_continue_4450"
    root.mkdir(parents=True, exist_ok=True)
    event_log = root / "events.jsonl"
    backup_eff = root / "pre_continue_efficient.pt"
    backup_deep = root / "pre_continue_deep.pt"
    if EFF.is_file():
        shutil.copy2(EFF, backup_eff)
    if DEEP.is_file():
        shutil.copy2(DEEP, backup_deep)

    start_steps = int(
        torch.load(HYBRID_EFF, map_location="cpu", weights_only=False)["train"]["steps_completed"]
    )
    target_steps = int(args.target_steps)
    if start_steps >= target_steps:
        raise RuntimeError(f"continue_start_not_below_target:{start_steps}>={target_steps}")

    arms: list[dict[str, Any]] = [
        {
            "arm_id": "hybrid_continue",
            "efficient": {
                "rid_rank": 8,
                "lr": 8e-6,
                "base_lr": 1.5e-6,
                "rid_residual": 0.3,
                "uml_nesting": 2.0,
                "uml_math": 2.0,
                "train_mode": "hybrid",
                "residual_feedback": True,
                "role_scales": EFF_ROLES,
            },
            "deep": {
                "rid_rank": 8,
                "lr": 8e-6,
                "base_lr": 2e-6,
                "rid_residual": 0.35,
                "uml_nesting": 3.0,
                "uml_math": 3.0,
                "train_mode": "hybrid",
                "residual_feedback": True,
                "role_scales": DEEP_ROLES,
            },
        },
        {
            "arm_id": "hybrid_deep_kl",
            "efficient": {
                "rid_rank": 8,
                "lr": 8e-6,
                "base_lr": 1.5e-6,
                "rid_residual": 0.3,
                "uml_nesting": 2.0,
                "uml_math": 2.0,
                "train_mode": "hybrid",
                "residual_feedback": True,
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
                "residual_feedback": True,
                "role_scales": DEEP_ROLES,
                "teacher_from_resume": True,
                "anchor_weight": 0.18,
            },
        },
        {
            "arm_id": "last_n2_hybrid",
            "efficient": {
                "rid_rank": 8,
                "lr": 1e-5,
                "base_lr": 2.5e-6,
                "rid_residual": 0.3,
                "uml_nesting": 2.0,
                "uml_math": 2.0,
                "train_mode": "last_n",
                "unfreeze_last_n": 2,
                "residual_feedback": True,
                "role_scales": EFF_ROLES,
            },
            "deep": {
                "rid_rank": 8,
                "lr": 8e-6,
                "base_lr": 2e-6,
                "rid_residual": 0.35,
                "uml_nesting": 3.0,
                "uml_math": 3.0,
                "train_mode": "last_n",
                "unfreeze_last_n": 2,
                "residual_feedback": True,
                "role_scales": DEEP_ROLES,
                "teacher_from_resume": True,
                "anchor_weight": 0.15,
            },
        },
    ]

    _append_jsonl(
        event_log,
        {
            "ts": _now_iso(),
            "event": "continue_start",
            "start_steps": start_steps,
            "target_steps": target_steps,
            "parent_arm": parent.get("arm_id"),
            "parent_metrics": parent_metrics,
            "arms": [a["arm_id"] for a in arms],
        },
    )

    try:
        baseline = {
            "efficient": _eval_checkpoint(
                HYBRID_EFF,
                rid_rank=8,
                rid_residual=0.3,
                uml_nesting=2.0,
                uml_math=2.0,
                role_scales=EFF_ROLES,
            ),
            "deep": _eval_checkpoint(
                HYBRID_DEEP,
                rid_rank=8,
                rid_residual=0.35,
                uml_nesting=3.0,
                uml_math=3.0,
                role_scales=DEEP_ROLES,
            ),
        }
        results: list[dict[str, Any]] = []
        for arm in arms:
            arm_id = str(arm["arm_id"])
            arm_dir = root / arm_id
            arm_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(HYBRID_EFF, EFF)
            shutil.copy2(HYBRID_DEEP, DEEP)
            _append_jsonl(event_log, {"ts": _now_iso(), "event": "arm_start", "arm_id": arm_id})

            for lane in ("efficient", "deep"):
                cfg = arm[lane]
                _arm_train(lane, EFF if lane == "efficient" else DEEP, target_steps, cfg)
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
            item = {
                "arm_id": arm_id,
                "efficient": eff_m,
                "deep": deep_m,
                "score": _score(eff_m, deep_m, acc_floor=float(args.acc_floor)),
                "delta_vs_parent": {
                    "efficient": {
                        "nll": eff_m["nll"] - baseline["efficient"]["nll"],
                        "acc": eff_m["acc"] - baseline["efficient"]["acc"],
                    },
                    "deep": {
                        "nll": deep_m["nll"] - baseline["deep"]["nll"],
                        "acc": deep_m["acc"] - baseline["deep"]["acc"],
                    },
                },
                "probes": {
                    "efficient": _probe(
                        arm_dir / "efficient_final.pt",
                        rid_rank=int(eff_cfg["rid_rank"]),
                        lane="efficient",
                    ),
                    "deep": _probe(
                        arm_dir / "deep_final.pt",
                        rid_rank=int(deep_cfg["rid_rank"]),
                        lane="deep",
                    ),
                },
                "cfg": {
                    "efficient": {k: v for k, v in eff_cfg.items() if k != "role_scales"},
                    "deep": {k: v for k, v in deep_cfg.items() if k != "role_scales"},
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
                    "delta_vs_parent": item["delta_vs_parent"],
                },
            )
            print(
                f"CONTINUE_RESULT {arm_id} "
                f"eff_nll={eff_m['nll']:.5f} deep_nll={deep_m['nll']:.5f} "
                f"d_eff={item['delta_vs_parent']['efficient']['nll']:+.6f} "
                f"d_deep={item['delta_vs_parent']['deep']['nll']:+.6f}",
                flush=True,
            )

        ranked = sorted(results, key=lambda r: r["score"])
        winner = ranked[0]
        parent_score = float(baseline["efficient"]["nll"] + baseline["deep"]["nll"])
        improved = float(winner["score"]) < parent_score - 1e-7
        if improved:
            win_dir = root / str(winner["arm_id"])
            shutil.copy2(win_dir / "efficient_final.pt", EFF)
            shutil.copy2(win_dir / "deep_final.pt", DEEP)
            pin_note = "pinned_winner"
        else:
            # Keep hybrid_full as active plant if no further gain.
            shutil.copy2(HYBRID_EFF, EFF)
            shutil.copy2(HYBRID_DEEP, DEEP)
            pin_note = "retained_parent_hybrid_full"

        summary = {
            "status": "PASS",
            "start_steps": start_steps,
            "target_steps": target_steps,
            "parent_arm": parent.get("arm_id"),
            "parent_metrics": baseline,
            "parent_score": parent_score,
            "arms": ranked,
            "winner": winner,
            "improved_vs_parent": improved,
            "pin_policy": pin_note,
            "pinned_to": {
                "efficient": str(EFF).replace("\\", "/"),
                "deep": str(DEEP).replace("\\", "/"),
            },
            "finished_at": _now_iso(),
        }
        latest = RUNS / "rid_breakthrough_continue_4450_latest.json"
        for path in (latest, root / "summary.json"):
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
        _append_jsonl(
            event_log,
            {
                "ts": _now_iso(),
                "event": "continue_pass",
                "winner": winner["arm_id"],
                "score": winner["score"],
                "improved_vs_parent": improved,
                "pin_policy": pin_note,
            },
        )
        print(
            f"CONTINUE_PASS winner={winner['arm_id']} improved={improved} pin={pin_note} "
            f"eff_nll={winner['efficient']['nll']:.5f} deep_nll={winner['deep']['nll']:.5f}",
            flush=True,
        )
        return 0
    except Exception as exc:
        if backup_eff.is_file():
            shutil.copy2(backup_eff, EFF)
        if backup_deep.is_file():
            shutil.copy2(backup_deep, DEEP)
        _append_jsonl(event_log, {"ts": _now_iso(), "event": "continue_fail", "error": repr(exc)})
        fail = {"status": "FAIL", "error": repr(exc), "finished_at": _now_iso()}
        with (RUNS / "rid_breakthrough_continue_4450_latest.json").open(
            "w", encoding="utf-8", newline="\n"
        ) as handle:
            json.dump(fail, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
