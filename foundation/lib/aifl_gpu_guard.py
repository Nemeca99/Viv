#!/usr/bin/env python3
"""GPU preflight for AIFL overnight — detect competing compute before train/validate.

Does not claim sleep/wake diagnosis. Focus: VRAM holders and known AIOS GPU jobs.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from typing import Any

DEFAULT_MAX_FOREIGN_MIB = 1536  # ~1.5 GiB — display/desktop OK; another LoRA is not

# Command-line needles for jobs that fight AIFL on the same card
COMPETE_NEEDLES = (
    "prt_main.py apply",
    "prt_main.py autonomous",
    "train_judge_lora",
    "validate_judge_adapter",
    # Do not match aifl_overnight_loop — the caller is that process (self false-positive).
    "aifl_auto_train_cycle",
    "hf_lora",
    "ollama",
)

HEAVY_NEEDLES = {
    "prt_main.py apply",
    "prt_main.py autonomous",
    "train_judge_lora",
    "validate_judge_adapter",
    "aifl_auto_train_cycle",
    "hf_lora",
}


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run(cmd: list[str], *, timeout: float = 15.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", "command_not_found"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def nvidia_smi_compute_apps() -> list[dict[str, Any]]:
    """Best-effort list of compute apps. Empty if nvidia-smi unavailable."""
    code, out, _err = _run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    if code != 0:
        return []
    rows: list[dict[str, Any]] = []
    for ln in out.splitlines():
        parts = [p.strip() for p in ln.split(",")]
        if len(parts) < 3:
            continue
        pid_s, name, mem_s = parts[0], parts[1], parts[2]
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        try:
            mem = float(re.sub(r"[^\d.]", "", mem_s) or "0")
        except ValueError:
            mem = None
        rows.append({"pid": pid, "name": name, "used_gpu_memory_mib": mem})
    return rows


def nvidia_smi_memory() -> dict[str, Any]:
    code, out, _err = _run(
        [
            "nvidia-smi",
            "--query-gpu=memory.used,memory.total,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
    )
    if code != 0 or not out.strip():
        return {"ok": False, "error": "nvidia_smi_failed"}
    parts = [p.strip() for p in out.strip().splitlines()[0].split(",")]
    if len(parts) < 3:
        return {"ok": False, "error": "nvidia_smi_parse"}
    try:
        return {
            "ok": True,
            "memory_used_mib": float(parts[0]),
            "memory_total_mib": float(parts[1]),
            "utilization_gpu_pct": float(parts[2]),
        }
    except ValueError:
        return {"ok": False, "error": "nvidia_smi_parse"}


def find_competing_processes(*, self_pid: int | None = None) -> list[dict[str, Any]]:
    """Scan running python/ollama for known GPU-competing AIOS commands."""
    import os

    self_pid = self_pid if self_pid is not None else os.getpid()
    code, out, _ = _run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe' "
                "OR Name='ollama.exe'\" | "
                "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
            ),
        ],
        timeout=20.0,
    )
    if code != 0 or not out.strip():
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    found: list[dict[str, Any]] = []
    for row in data or []:
        try:
            pid = int(row.get("ProcessId") or 0)
        except (TypeError, ValueError):
            continue
        if pid in (0, self_pid):
            continue
        cmd = str(row.get("CommandLine") or "")
        low = cmd.lower()
        hit = next((n for n in COMPETE_NEEDLES if n.lower() in low), None)
        if not hit:
            continue
        found.append(
            {
                "pid": pid,
                "name": row.get("Name"),
                "needle": hit,
                "cmd": cmd[:240],
            }
        )
    return found


def gpu_preflight(
    *,
    max_foreign_mib: float = DEFAULT_MAX_FOREIGN_MIB,
    block_compete: bool = True,
    self_pid: int | None = None,
) -> dict[str, Any]:
    """Return ok=False when overnight should refuse to start a GPU cycle."""
    mem = nvidia_smi_memory()
    apps = nvidia_smi_compute_apps()
    compete = find_competing_processes(self_pid=self_pid) if block_compete else []

    blocked: list[str] = []
    if not mem.get("ok"):
        note = "nvidia_smi_unavailable"
    else:
        note = "ok"
        used = float(mem.get("memory_used_mib") or 0.0)
        if used > float(max_foreign_mib):
            blocked.append(f"gpu_memory_used>{max_foreign_mib:.0f}MiB ({used:.0f})")

    heavy = [c for c in compete if c.get("needle") in HEAVY_NEEDLES]
    if heavy:
        blocked.append(
            "competing_process:" + ",".join(f"{c['needle']}@{c['pid']}" for c in heavy)
        )

    return {
        "ok": len(blocked) == 0,
        "at": _utc(),
        "blocked_by": blocked,
        "note": note,
        "memory": mem,
        "compute_apps": apps,
        "competing": compete,
        "max_foreign_mib": max_foreign_mib,
    }


if __name__ == "__main__":
    print(json.dumps(gpu_preflight(), indent=2))
