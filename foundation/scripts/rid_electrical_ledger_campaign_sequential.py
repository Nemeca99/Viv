#!/usr/bin/env python3
"""Sequential single-factor ledger evidence runs (tokens → … → executor).

Keeps auto_admit=false. Writes factor progress logs under ledger_campaign/.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
PY = FOUNDATION.parents[1] / ".venv" / "Scripts" / "python.exe"
if not PY.is_file():
    PY = Path(r"L:/Continue/.venv/Scripts/python.exe")
OUT = FOUNDATION / "artifacts" / "auto" / "rid_electrical" / "ledger_campaign"
FACTORS = ("tokens", "thermal", "repetition", "model", "executor")


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    repeats = 3
    if len(sys.argv) > 1:
        repeats = int(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    progress = OUT / "sequential_factors_progress.jsonl"
    script = FOUNDATION / "scripts" / "rid_electrical_ledger_campaign.py"
    for factor in FACTORS:
        rec = {"at": _utc(), "event": "factor_start", "factor": factor, "repeats": repeats}
        progress.open("a", encoding="utf-8").write(json.dumps(rec) + "\n")
        print(f"[sequential] START factor={factor} repeats={repeats}", flush=True)
        t0 = time.time()
        proc = subprocess.run(
            [
                str(PY),
                "-u",
                str(script),
                "--factor",
                factor,
                "--repeats",
                str(repeats),
                "--gap-s",
                "20",
            ],
            cwd=str(FOUNDATION),
        )
        elapsed = time.time() - t0
        rec2 = {
            "at": _utc(),
            "event": "factor_end",
            "factor": factor,
            "exit_code": proc.returncode,
            "elapsed_s": round(elapsed, 1),
        }
        progress.open("a", encoding="utf-8").write(json.dumps(rec2) + "\n")
        print(
            f"[sequential] END factor={factor} exit={proc.returncode} elapsed_s={elapsed:.1f}",
            flush=True,
        )
        if proc.returncode != 0:
            print(f"[sequential] STOP on failure at factor={factor}", flush=True)
            return proc.returncode
    # Final evaluate-only refresh
    subprocess.run(
        [str(PY), "-u", str(script), "--evaluate-only"],
        cwd=str(FOUNDATION),
        check=False,
    )
    print("[sequential] DONE all factors", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
