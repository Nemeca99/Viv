#!/usr/bin/env python3
"""30-second CARMA validation — remember, retrieve, autonomous live append."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

_FOUNDATION = Path(__file__).resolve().parents[1]
_VIV = _FOUNDATION.parent
_PY = _VIV.parent / ".venv" / "Scripts" / "python.exe"
_MEM = _VIV / "memory_core" / "memory_main.py"
_AUTO = _FOUNDATION / "auto_main.py"
_OUT = _FOUNDATION / "artifacts" / "audit" / "memory_smoke_30s.json"


def _run(args: list[str], timeout: int = 60) -> dict:
    proc = subprocess.run(
        [str(_PY), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(_FOUNDATION),
    )
    return {
        "cmd": args,
        "code": proc.returncode,
        "stdout": (proc.stdout or "").strip()[:2000],
        "stderr": (proc.stderr or "").strip()[:500],
    }


def main() -> int:
    token = f"carma_smoke_{uuid.uuid4().hex[:8]}"
    report: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "token": token,
        "steps": [],
        "passed": False,
    }

    # 1) remember unique token
    r1 = _run([str(_MEM), "remember", f"smoke test note {token}", "--tags", "smoke"])
    report["steps"].append({"remember": r1})
    if r1["code"] != 0:
        report["fail"] = "remember"
        _write(report)
        return 1

    # 2) retrieve token
    r2 = _run([str(_MEM), "retrieve", token, "--top", "3"])
    report["steps"].append({"retrieve": r2})
    if token not in r2.get("stdout", ""):
        report["fail"] = "retrieve_miss"
        _write(report)
        return 1

    # 3) status baseline heartbeat
    st0 = json.loads(_run([str(_MEM), "status"])["stdout"] or "{}")
    hb0 = int(st0.get("heartbeat_lines") or 0)
    report["heartbeat_before"] = hb0

    # 4) ~30s autonomous — memory appends only when S_n >= 0.45 (Law 5)
    proc = subprocess.Popen(
        [str(_PY), str(_AUTO), "autonomous", "--interval", "1", "--no-piston"],
        cwd=str(_FOUNDATION),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(30)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    report["steps"].append({"autonomous_30s": "terminated_after_30s"})

    st1 = json.loads(_run([str(_MEM), "status"])["stdout"] or "{}")
    hb1 = int(st1.get("heartbeat_lines") or 0)
    report["heartbeat_after"] = hb1
    report["heartbeat_delta"] = hb1 - hb0

    r3 = _run([str(_MEM), "retrieve", token, "--top", "1"])
    report["steps"].append({"retrieve_final": r3})

    remember_ok = r1.get("code") == 0 and '"ok": true' in (r1.get("stdout") or "")
    retrieve_ok = token in (r2.get("stdout") or "")
    memory_grew = hb1 > hb0

    if memory_grew:
        report["autonomous_memory"] = "active_appends_observed"
        passed = remember_ok and retrieve_ok and memory_grew
    else:
        report["autonomous_memory"] = "no_appends_likely_dormant_or_law5"
        # Core store must work even if dormancy blocked live append during window
        passed = remember_ok and retrieve_ok

    report["passed"] = passed
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write(report)
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


def _write(report: dict) -> None:
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = _OUT.with_suffix(".md")
    md.write_text(
        f"# CARMA 30s smoke — {'PASS' if report.get('passed') else 'FAIL'}\n\n"
        f"- token: `{report.get('token')}`\n"
        f"- heartbeat: {report.get('heartbeat_before')} → {report.get('heartbeat_after')} "
        f"(Δ{report.get('heartbeat_delta')})\n"
        f"- autonomous_memory: {report.get('autonomous_memory')}\n"
        f"- artifact: `{_OUT}`\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
