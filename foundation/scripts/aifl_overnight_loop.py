#!/usr/bin/env python3
"""Overnight AIFL driver: collect until gate arms → auto-train → sleep → repeat.

GPU preflight refuses cycles when PRT/other LoRA jobs hold the card.
Train+validate run in a subprocess so a hung CUDA generate can be killed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.aifl_gpu_guard import gpu_preflight  # noqa: E402

LOG = FOUNDATION / "artifacts" / "audit" / "aifl_overnight_loop.jsonl"
PY = Path(sys.executable)
# Train (~15m) + validate 60×120s worst case + buffer
DEFAULT_TRAIN_VALIDATE_TIMEOUT_S = 4 * 60 * 60
DEFAULT_CASE_TIMEOUT_S = 120


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _free_soft_gpu_holders() -> dict:
    """Unload Ollama models that wake during collect and steal VRAM from LoRA train."""
    out: dict = {"actions": []}
    try:
        ps = subprocess.run(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc), "actions": []}
    lines = [ln.strip() for ln in (ps.stdout or "").splitlines() if ln.strip()]
    # Skip header "NAME ID SIZE ..."
    for ln in lines[1:]:
        name = ln.split()[0] if ln.split() else ""
        if not name or name.upper() == "NAME":
            continue
        stop = subprocess.run(
            ["ollama", "stop", name],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        out["actions"].append(
            {"stop": name, "rc": stop.returncode, "stderr": (stop.stderr or "")[:200]}
        )
    time.sleep(2.0)
    out["ok"] = True
    return out


def _preflight_or_free(
    *,
    max_foreign_mib: float,
    self_pid: int,
    label: str,
) -> tuple[dict, dict | None]:
    """Run preflight; if only soft VRAM (e.g. Ollama) blocks, unload and recheck once."""
    pre = gpu_preflight(max_foreign_mib=max_foreign_mib, self_pid=self_pid)
    if pre.get("ok"):
        return pre, None
    blocked = pre.get("blocked_by") or []
    heavy_block = any(str(b).startswith("competing_process:") for b in blocked)
    mem_block = any("gpu_memory_used>" in str(b) for b in blocked)
    if heavy_block or not mem_block:
        return pre, None
    print(f"GPU soft holders detected after {label} — unloading Ollama models", flush=True)
    freed = _free_soft_gpu_holders()
    print(json.dumps({"freed_soft_gpu": freed}, indent=2, default=str), flush=True)
    pre2 = gpu_preflight(max_foreign_mib=max_foreign_mib, self_pid=self_pid)
    return pre2, freed

def _load(name: str, path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _append_log(row: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _run_train_cycle_subprocess(*, timeout_s: int) -> dict:
    """Run auto-train in a child process so hang kills free the GPU.

    Streams stdout/stderr live (not captured) so the operator sees train progress.
    """
    cmd = [str(PY), str(FOUNDATION / "models" / "Training" / "code" / "aifl_auto_train_cycle.py")]
    print(f"TRAIN-VALIDATE subprocess timeout={timeout_s}s", flush=True)
    latest = FOUNDATION / "artifacts" / "auto" / "aifl" / "auto_train_cycle_latest.json"
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(FOUNDATION),
            timeout=timeout_s,
            check=False,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except subprocess.TimeoutExpired:
        print("TRAIN-VALIDATE subprocess HARD TIMEOUT — killed", flush=True)
        return {
            "ok": False,
            "error": "train_validate_subprocess_timeout",
            "timeout_s": timeout_s,
            "cuda_poison_risk": True,
        }

    parsed: dict = {}
    if latest.is_file():
        try:
            parsed = json.loads(latest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            parsed = {}
    if not parsed:
        parsed = {
            "ok": False,
            "error": "train_validate_missing_result",
            "returncode": proc.returncode,
        }
    else:
        parsed.setdefault("ok", proc.returncode == 0)
        parsed["subprocess_returncode"] = proc.returncode
    return parsed


def run_once(
    *,
    sleep_s: int,
    train_timeout_s: int,
    max_foreign_mib: float,
    skip_gpu_preflight: bool,
) -> dict:
    print(f"=== OVERNIGHT CYCLE {_utc()} ===", flush=True)

    if not skip_gpu_preflight:
        pre, _freed0 = _preflight_or_free(
            max_foreign_mib=max_foreign_mib,
            self_pid=os.getpid(),
            label="start",
        )
        print(json.dumps({"gpu_preflight": pre}, indent=2, default=str), flush=True)
        if not pre.get("ok"):
            row = {
                "at": _utc(),
                "ok": False,
                "error": "gpu_preflight_blocked",
                "gpu_preflight": pre,
                "sleep_s": sleep_s,
                "note": "Stop prt_main apply/autonomous (and other LoRA jobs) before overnight GPU cycles.",
            }
            _append_log(row)
            print(json.dumps(row, indent=2, default=str), flush=True)
            return row
    else:
        pre = {"ok": True, "skipped": True}

    collect = _load("aifl_collect_until_ready", FOUNDATION / "scripts" / "aifl_collect_until_ready.py")
    collect_rc = collect.main()

    # Re-check GPU after collect (pulses / Ollama may have woken a model)
    freed_after = None
    if not skip_gpu_preflight:
        pre2, freed_after = _preflight_or_free(
            max_foreign_mib=max_foreign_mib,
            self_pid=os.getpid(),
            label="collect",
        )
        if not pre2.get("ok"):
            row = {
                "at": _utc(),
                "ok": False,
                "collect_rc": collect_rc,
                "error": "gpu_preflight_blocked_after_collect",
                "gpu_preflight": pre2,
                "freed_soft_gpu": freed_after,
                "sleep_s": sleep_s,
                "note": "Collect armed train_ready but GPU still busy — free VRAM then re-run --once (signal may already exist).",
            }
            _append_log(row)
            print(json.dumps(row, indent=2, default=str), flush=True)
            return row
        pre = pre2

    train_out = _run_train_cycle_subprocess(timeout_s=train_timeout_s)
    row = {
        "at": _utc(),
        "collect_rc": collect_rc,
        "train": train_out,
        "sleep_s": sleep_s,
        "gpu_preflight": pre,
    }
    if freed_after:
        row["freed_soft_gpu"] = freed_after
    if train_out.get("cuda_poison_risk") or (train_out.get("validate") or {}).get("cuda_poison_risk"):
        row["cuda_poison_risk"] = True
        row["note"] = "CUDA hang risk — exiting overnight so next start is a clean process"
    _append_log(row)
    print(json.dumps(row, indent=2, default=str), flush=True)
    return row


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="AIFL overnight collect → train loop")
    p.add_argument("--sleep", type=int, default=600, help="Seconds between cycles (default 600)")
    p.add_argument("--once", action="store_true", help="Single cycle then exit")
    p.add_argument(
        "--train-timeout",
        type=int,
        default=DEFAULT_TRAIN_VALIDATE_TIMEOUT_S,
        help="Hard kill train+validate subprocess after N seconds (default 4h)",
    )
    p.add_argument(
        "--max-foreign-mib",
        type=float,
        default=1536,
        help="Refuse cycle if GPU memory.used above this (default 1536)",
    )
    p.add_argument(
        "--skip-gpu-preflight",
        action="store_true",
        help="Do not block on competing GPU processes (not recommended)",
    )
    args = p.parse_args()

    while True:
        row = run_once(
            sleep_s=args.sleep,
            train_timeout_s=args.train_timeout,
            max_foreign_mib=args.max_foreign_mib,
            skip_gpu_preflight=args.skip_gpu_preflight,
        )
        if row.get("cuda_poison_risk"):
            print("EXIT overnight due to cuda_poison_risk — restart manually when GPU is free", flush=True)
            return 2
        if args.once:
            return 0 if row.get("error") != "gpu_preflight_blocked" else 3
        print(f"sleep {args.sleep}s", flush=True)
        time.sleep(max(1, args.sleep))


if __name__ == "__main__":
    raise SystemExit(main())
