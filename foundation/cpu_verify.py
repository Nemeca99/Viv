#!/usr/bin/env python3
"""One-shot CPU automaton verification — no LLM."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts" / "auto"


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    out = (p.stdout or p.stderr or "").strip()[:500]
    return p.returncode, out


def main() -> int:
    steps = [
        ("rid_sample", [sys.executable, str(ROOT / "rid_main.py"), "sample"]),
        ("auto_run", [sys.executable, str(ROOT / "auto_main.py"), "run", "--once", "--quiet", "--allow-denied"]),
        ("gate", [sys.executable, str(ROOT / "auto_main.py"), "gate"]),
        ("guardian_demo", [sys.executable, str(ROOT / "guardian_main.py"), "demo"]),
        ("reasoning", [sys.executable, str(ROOT / "model_main.py"), "reasoning"]),
    ]
    report = {"steps": [], "all_ok": True}
    for name, cmd in steps:
        code, detail = run(cmd)
        ok = code == 0 or (name == "auto_run" and code in (0, 30))
        if name == "gate" and code == 0:
            ok = True
        report["steps"].append({"name": name, "exit_code": code, "ok": ok, "detail": detail[:200]})
        if not ok:
            report["all_ok"] = False
        print(f"[{'PASS' if ok else 'FAIL'}] {name} ({code})")
    out = ART / "cpu_verify_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
