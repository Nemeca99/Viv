#!/usr/bin/env python3
"""AIFL Training home — per-run folders under models/Training.

Layout
------
models/Training/
  README.md
  code/          # train / plot / validate / auto cycle
  runs/
    <run_id>/
      RUN.md
      adapter/       # Peft weights (deploy/validate load this)
      checkpoints/   # HF Trainer output
      plots/         # train_metrics.png + .json
      logs/
        events.jsonl   # labeled timeline (train.*, validate.*, deploy.*, plot.*)
        metrics.jsonl  # one row per trainer log step
        forensics.jsonl  # per-step batch + grad direction (diagnostic)
      validate/      # holdout results
      meta/          # viv_train_meta.json, cycle_result.json
  deploy/
    current          # junction → runs/<id>/adapter (production mouth)
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import FOUNDATION_ROOT

TRAINING_ROOT = FOUNDATION_ROOT / "models" / "Training"
TRAINING_CODE = TRAINING_ROOT / "code"
TRAINING_RUNS = TRAINING_ROOT / "runs"
TRAINING_DEPLOY = TRAINING_ROOT / "deploy"
TRAINING_DEPLOY_CURRENT = TRAINING_DEPLOY / "current"

# Legacy GPU deploy junction (kept in sync for older callers)
LEGACY_GPU_DEPLOY = FOUNDATION_ROOT / "models" / "gpu" / "viv_voice_lora_judge_deploy"
LEGACY_GPU_ROOT = FOUNDATION_ROOT / "models" / "gpu"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_training_tree() -> None:
    for p in (TRAINING_ROOT, TRAINING_CODE, TRAINING_RUNS, TRAINING_DEPLOY):
        p.mkdir(parents=True, exist_ok=True)


def make_run_id(steps: int, stamp: str | None = None) -> str:
    return f"lora_judge_{int(steps)}_{stamp or _stamp()}"


def run_paths(run_dir: Path) -> dict[str, Path]:
    run_dir = Path(run_dir)
    return {
        "root": run_dir,
        "adapter": run_dir / "adapter",
        "checkpoints": run_dir / "checkpoints",
        "plots": run_dir / "plots",
        "logs": run_dir / "logs",
        "validate": run_dir / "validate",
        "meta": run_dir / "meta",
        "events": run_dir / "logs" / "events.jsonl",
        "metrics": run_dir / "logs" / "metrics.jsonl",
        "run_md": run_dir / "RUN.md",
    }


def create_run_dir(*, steps: int, stamp: str | None = None, allow_overwrite: bool = False) -> dict[str, Path]:
    """Create empty per-run tree. Returns path map. Refuses if exists unless allow_overwrite."""
    ensure_training_tree()
    run_id = make_run_id(steps, stamp)
    root = TRAINING_RUNS / run_id
    if root.exists() and any(root.iterdir()) and not allow_overwrite:
        raise FileExistsError(f"run_exists_no_overwrite: {root}")
    paths = run_paths(root)
    for key in ("adapter", "checkpoints", "plots", "logs", "validate", "meta"):
        paths[key].mkdir(parents=True, exist_ok=True)
    paths["run_md"].write_text(
        f"# {run_id}\n\n"
        f"- created: {_utc()}\n"
        f"- steps: {steps}\n"
        f"- adapter: `{paths['adapter'].as_posix()}`\n"
        f"- status: created\n",
        encoding="utf-8",
    )
    append_event(root, label="run.create", payload={"run_id": run_id, "steps": steps})
    return paths


def append_event(run_dir: Path, *, label: str, payload: dict[str, Any] | None = None) -> None:
    """Append a labeled event to logs/events.jsonl (separated timeline)."""
    paths = run_paths(run_dir)
    paths["logs"].mkdir(parents=True, exist_ok=True)
    row = {"at": _utc(), "label": str(label), **(payload or {})}
    with paths["events"].open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def write_metrics_jsonl(run_dir: Path, log_history: list[dict[str, Any]]) -> Path:
    """Write separated per-step trainer metrics (loss/lr/grad_norm/epoch/step)."""
    paths = run_paths(run_dir)
    paths["logs"].mkdir(parents=True, exist_ok=True)
    with paths["metrics"].open("w", encoding="utf-8") as fh:
        for h in log_history:
            if not isinstance(h, dict) or "loss" not in h:
                continue
            fh.write(
                json.dumps(
                    {
                        "label": "train.metric",
                        "step": h.get("step"),
                        "epoch": h.get("epoch"),
                        "loss": h.get("loss"),
                        "learning_rate": h.get("learning_rate"),
                        "grad_norm": h.get("grad_norm"),
                    },
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
    append_event(
        run_dir,
        label="train.metrics_written",
        payload={"path": str(paths["metrics"]).replace("\\", "/"), "n": len(log_history)},
    )
    return paths["metrics"]


def update_run_md(run_dir: Path, *, status: str, extra_lines: list[str] | None = None) -> None:
    paths = run_paths(run_dir)
    lines = [
        f"# {run_dir.name}",
        "",
        f"- updated: {_utc()}",
        f"- status: {status}",
        f"- adapter: `{paths['adapter'].as_posix()}`",
        f"- checkpoints: `{paths['checkpoints'].as_posix()}`",
        f"- plots: `{paths['plots'].as_posix()}`",
        f"- logs: `{paths['logs'].as_posix()}`",
        f"- validate: `{paths['validate'].as_posix()}`",
    ]
    if extra_lines:
        lines.append("")
        lines.extend(extra_lines)
    paths["run_md"].write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_adapter_dir(path: Path | str) -> Path:
    """Accept run root or adapter dir; return directory containing adapter_config.json."""
    p = Path(path)
    if (p / "adapter_config.json").is_file():
        return p
    if (p / "adapter" / "adapter_config.json").is_file():
        return p / "adapter"
    return p


def resolve_run_dir(path: Path | str) -> Path | None:
    """If path is inside a Training run, return run root."""
    p = Path(path).resolve()
    try:
        rel = p.relative_to(TRAINING_RUNS.resolve())
    except ValueError:
        # legacy flat gpu adapter
        if p.name.startswith("lora_judge_") and p.is_dir():
            return p
        return None
    parts = rel.parts
    if not parts:
        return None
    return TRAINING_RUNS / parts[0]


def set_deploy_junction(adapter_dir: Path) -> dict[str, Any]:
    """Point Training/deploy/current and legacy gpu deploy junction at adapter_dir."""
    ensure_training_tree()
    adapter_dir = resolve_adapter_dir(adapter_dir)
    results: dict[str, Any] = {"adapter": str(adapter_dir).replace("\\", "/"), "targets": []}

    import subprocess

    for target in (TRAINING_DEPLOY_CURRENT, LEGACY_GPU_DEPLOY):
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            # Windows junctions: rmdir; symlinks: unlink
            rm = subprocess.run(
                ["cmd", "/c", "rmdir", str(target)],
                capture_output=True,
                text=True,
                check=False,
            )
            if rm.returncode != 0:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    try:
                        shutil.rmtree(target, ignore_errors=True)
                    except OSError:
                        pass
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(adapter_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        results["targets"].append(
            {
                "path": str(target).replace("\\", "/"),
                "ok": proc.returncode == 0,
                "rc": proc.returncode,
                "stderr": (proc.stderr or "")[:200],
                "stdout": (proc.stdout or "")[:200],
            }
        )
    return results


def migrate_legacy_adapter(src: Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Move models/gpu/lora_judge_* flat dir into Training/runs/<id>/ layout."""
    src = Path(src)
    if not src.is_dir():
        return {"ok": False, "error": "not_a_dir", "src": str(src)}
    run_id = src.name
    dest = TRAINING_RUNS / run_id
    if dest.exists():
        return {"ok": False, "error": "dest_exists", "dest": str(dest)}
    if dry_run:
        return {"ok": True, "dry_run": True, "src": str(src), "dest": str(dest)}

    ensure_training_tree()
    paths = run_paths(dest)
    for key in ("adapter", "checkpoints", "plots", "logs", "validate", "meta"):
        paths[key].mkdir(parents=True, exist_ok=True)

    # Move peft/tokenizer files into adapter/
    adapter_names = {
        "adapter_config.json",
        "adapter_model.safetensors",
        "adapter_model.bin",
        "README.md",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "added_tokens.json",
        "merges.txt",
        "vocab.json",
        "DEPLOYED.md",
    }
    moved: list[str] = []
    for child in list(src.iterdir()):
        name = child.name
        if name in adapter_names or name.endswith(".safetensors"):
            shutil.move(str(child), str(paths["adapter"] / name))
            moved.append(f"adapter/{name}")
        elif name == "runs":
            # HF trainer checkpoints
            for sub in child.iterdir():
                shutil.move(str(sub), str(paths["checkpoints"] / sub.name))
            try:
                child.rmdir()
            except OSError:
                shutil.rmtree(child, ignore_errors=True)
            moved.append("checkpoints/")
        elif name.startswith("train_metrics"):
            shutil.move(str(child), str(paths["plots"] / name))
            moved.append(f"plots/{name}")
        elif name in {"holdout_validate.json", "validate_latest.json"}:
            shutil.move(str(child), str(paths["validate"] / name))
            moved.append(f"validate/{name}")
        elif name in {"viv_train_meta.json"}:
            shutil.move(str(child), str(paths["meta"] / name))
            moved.append(f"meta/{name}")
        else:
            # leftover → meta/
            shutil.move(str(child), str(paths["meta"] / name))
            moved.append(f"meta/{name}")

    try:
        src.rmdir()
    except OSError:
        # leave empty husk if locked
        pass

    update_run_md(dest, status="migrated_from_gpu", extra_lines=[f"- source: `{src.as_posix()}`"])
    append_event(dest, label="run.migrated", payload={"from": str(src).replace("\\", "/"), "moved": moved})
    return {"ok": True, "run_id": run_id, "dest": str(dest).replace("\\", "/"), "moved": moved}
