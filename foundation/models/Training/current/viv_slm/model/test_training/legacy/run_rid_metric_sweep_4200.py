#!/usr/bin/env python3
"""Sweep RID/UML metric combinations from current checkpoints to 4200 steps."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import torch

SANDBOX = Path(__file__).resolve().parents[1]  # legacy home: parents[1] = test_training/
MODEL = SANDBOX.parent
PY = Path(r"L:\Continue\.venv\Scripts\python.exe")
EFF = SANDBOX / "checkpoints" / "efficient" / "specialist.pt"
DEEP = SANDBOX / "checkpoints" / "deep" / "specialist.pt"
RUNS = SANDBOX / "runs"

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


@dataclass
class SweepCfg:
    rid_rank: int
    rid_residual: float
    uml_nesting: float
    uml_math: float
    learning_rate: float

    @property
    def run_id(self) -> str:
        return (
            f"r{self.rid_rank}"
            f"_res{str(self.rid_residual).replace('.', 'p')}"
            f"_nest{str(self.uml_nesting).replace('.', 'p')}"
            f"_math{str(self.uml_math).replace('.', 'p')}"
            f"_lr{str(self.learning_rate).replace('.', 'p')}"
        )


def _run(cmd: list[str]) -> None:
    print("RUN", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=str(MODEL))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _eval_checkpoint(path: Path, *, cfg: SweepCfg) -> dict[str, float]:
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
        rid_rank=cfg.rid_rank,
        rid_alpha=16.0,
        rid_dropout=0.05,
    ).to(device)
    model.load_state_dict(payload["model_state_dict"], strict=False)
    model.set_rid_metrics(
        rid_residual=cfg.rid_residual,
        uml_nesting=cfg.uml_nesting,
        uml_math=cfg.uml_math,
    )
    model.eval()
    val = evaluate_split(model, val_in, val_tg, device=device, batch_size=64, loss_masks=val_mask)
    return {
        "nll": float(val["nll"]),
        "acc": float(val["token_accuracy"]),
        "ppl": float(val["perplexity"]),
    }


def _baseline_metrics(eff_path: Path, deep_path: Path) -> dict[str, dict[str, float]]:
    base_cfg = SweepCfg(rid_rank=8, rid_residual=0.0, uml_nesting=0.0, uml_math=0.0, learning_rate=7e-6)
    return {
        "efficient": _eval_checkpoint(eff_path, cfg=base_cfg),
        "deep": _eval_checkpoint(deep_path, cfg=base_cfg),
    }


def _score(eff: dict[str, float], deep: dict[str, float], acc_floor: float) -> float:
    penalty = 0.0
    if eff["acc"] < acc_floor:
        penalty += 10.0
    if deep["acc"] < acc_floor:
        penalty += 10.0
    return eff["nll"] + deep["nll"] + penalty


def _generate_grid() -> list[SweepCfg]:
    ranks = [4, 8, 16]
    residuals = [0.2, 0.5, 0.8, 1.0]
    nestings = [0.0, 4.0, 8.0]
    maths = [0.0, 4.0, 8.0]
    lrs = [5e-6, 7e-6]
    out: list[SweepCfg] = []
    for rank in ranks:
        for residual in residuals:
            for nesting in nestings:
                for math_sig in maths:
                    for lr in lrs:
                        out.append(
                            SweepCfg(
                                rid_rank=rank,
                                rid_residual=residual,
                                uml_nesting=nesting,
                                uml_math=math_sig,
                                learning_rate=lr,
                            )
                        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-runs", type=int, default=72)
    parser.add_argument("--acc-floor", type=float, default=0.961)
    parser.add_argument("--save-top-k", type=int, default=5)
    parser.add_argument("--target-steps", type=int, default=4200)
    parser.add_argument("--base-efficient", default=None, help="Optional base checkpoint for efficient lane.")
    parser.add_argument("--base-deep", default=None, help="Optional base checkpoint for deep lane.")
    args = parser.parse_args()

    base_eff_src = Path(args.base_efficient) if args.base_efficient else EFF
    base_deep_src = Path(args.base_deep) if args.base_deep else DEEP
    if not base_eff_src.is_file() or not base_deep_src.is_file():
        raise FileNotFoundError("sweep_base_checkpoint_missing")
    start_steps = int(torch.load(base_eff_src, map_location="cpu", weights_only=False)["train"]["steps_completed"])
    target_steps = int(args.target_steps)
    if start_steps > target_steps:
        raise RuntimeError(f"sweep_start_above_target:start={start_steps}:target={target_steps}")

    sweep_root = RUNS / "rid_metric_sweep_4200"
    sweep_root.mkdir(parents=True, exist_ok=True)
    event_log = sweep_root / "events.jsonl"
    _append_jsonl(
        event_log,
        {
            "ts": _now_iso(),
            "event": "sweep_start",
            "max_runs": int(args.max_runs),
            "acc_floor": float(args.acc_floor),
            "save_top_k": int(args.save_top_k),
            "start_steps": start_steps,
            "target_steps": target_steps,
        },
    )
    eff_base = sweep_root / "efficient_base.pt"
    deep_base = sweep_root / "deep_base.pt"
    shutil.copy2(base_eff_src, eff_base)
    shutil.copy2(base_deep_src, deep_base)

    baseline = _baseline_metrics(base_eff_src, base_deep_src)
    all_cfgs = _generate_grid()[: int(args.max_runs)]
    results: list[dict[str, Any]] = []

    try:
        for idx, cfg in enumerate(all_cfgs, start=1):
            shutil.copy2(eff_base, EFF)
            shutil.copy2(deep_base, DEEP)
            _append_jsonl(
                event_log,
                {"ts": _now_iso(), "event": "run_start", "index": idx, "total": len(all_cfgs), "run_id": cfg.run_id},
            )
            print(f"SWEEP_CFG {idx}/{len(all_cfgs)} {cfg.run_id}", flush=True)
            for lane, ckpt in (("efficient", EFF), ("deep", DEEP)):
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
                    str(ckpt),
                    "--steps",
                    str(target_steps),
                    "--training-phase",
                    "default",
                    "--learning-rate",
                    str(cfg.learning_rate),
                    "--rid-adapter",
                    "--rid-rank",
                    str(cfg.rid_rank),
                    "--rid-alpha",
                    "16",
                    "--rid-dropout",
                    "0.05",
                    "--rid-adapter-only",
                    "--rid-residual",
                    str(cfg.rid_residual),
                    "--uml-nesting",
                    str(cfg.uml_nesting),
                    "--uml-math",
                    str(cfg.uml_math),
                ]
                _run(cmd)
            eff_m = _eval_checkpoint(EFF, cfg=cfg)
            deep_m = _eval_checkpoint(DEEP, cfg=cfg)
            score = _score(eff_m, deep_m, acc_floor=float(args.acc_floor))
            item = {
                "cfg": asdict(cfg),
                "run_id": cfg.run_id,
                "efficient": eff_m,
                "deep": deep_m,
                "score": score,
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
            }
            results.append(item)
            _append_jsonl(
                event_log,
                {
                    "ts": _now_iso(),
                    "event": "run_result",
                    "index": idx,
                    "run_id": cfg.run_id,
                    "score": score,
                    "efficient": eff_m,
                    "deep": deep_m,
                },
            )
            print(
                f"SWEEP_RESULT {cfg.run_id} "
                f"eff_nll={eff_m['nll']:.4f} eff_acc={eff_m['acc']:.4f} "
                f"deep_nll={deep_m['nll']:.4f} deep_acc={deep_m['acc']:.4f} "
                f"score={score:.4f}",
                flush=True,
            )
            checkpoint_copy_dir = sweep_root / "checkpoints"
            checkpoint_copy_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(EFF, checkpoint_copy_dir / f"{cfg.run_id}_efficient.pt")
            shutil.copy2(DEEP, checkpoint_copy_dir / f"{cfg.run_id}_deep.pt")
            summary = {
                "status": "RUNNING",
                "start_steps": start_steps,
                "target_steps": target_steps,
                "baseline": baseline,
                "completed_runs": len(results),
                "requested_runs": len(all_cfgs),
                "results": results,
            }
            (RUNS / "rid_metric_sweep_4200_latest.json").write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8"
            )

        ranked = sorted(results, key=lambda x: float(x["score"]))
        top_k = ranked[: max(1, int(args.save_top_k))]
        winner = top_k[0]
        shutil.copy2(sweep_root / "checkpoints" / f"{winner['run_id']}_efficient.pt", EFF)
        shutil.copy2(sweep_root / "checkpoints" / f"{winner['run_id']}_deep.pt", DEEP)

        final = {
            "status": "PASS",
            "start_steps": start_steps,
            "target_steps": target_steps,
            "baseline": baseline,
            "runs": len(results),
            "winner": winner,
            "top_k": top_k,
            "results": results,
        }
        (RUNS / "rid_metric_sweep_4200_latest.json").write_text(
            json.dumps(final, indent=2) + "\n", encoding="utf-8"
        )
        _append_jsonl(
            event_log,
            {
                "ts": _now_iso(),
                "event": "sweep_pass",
                "runs": len(results),
                "winner": winner["run_id"],
                "winner_score": float(winner["score"]),
            },
        )
        print(
            f"RID_SWEEP_PASS runs={len(results)} winner={winner['run_id']} "
            f"eff_nll={winner['efficient']['nll']:.4f} deep_nll={winner['deep']['nll']:.4f}",
            flush=True,
        )
        return 0
    except Exception as exc:
        # Fail closed: restore baseline checkpoints on any crash.
        shutil.copy2(eff_base, EFF)
        shutil.copy2(deep_base, DEEP)
        crash = {
            "status": "FAIL_CLOSED",
            "error": repr(exc),
            "start_steps": start_steps,
            "target_steps": target_steps,
            "completed_runs": len(results),
            "baseline_restored": True,
        }
        (RUNS / "rid_metric_sweep_4200_latest.json").write_text(
            json.dumps(crash, indent=2) + "\n", encoding="utf-8"
        )
        _append_jsonl(
            event_log,
            {
                "ts": _now_iso(),
                "event": "sweep_fail_closed",
                "error": repr(exc),
                "completed_runs": len(results),
            },
        )
        print(f"RID_SWEEP_FAIL_CLOSED error={exc!r}", flush=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
