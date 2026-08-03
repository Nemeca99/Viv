"""AIOS foundation health — bedrock checks importable by auto_gate."""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from lib.paths import CONTINUE_ROOT, FOUNDATION_ROOT, RID_ARTIFACTS
from lib.plant_piston_bridge import LAST_CAPTURE_PATH
from lib.piston_engine import PISTON_STATE_PATH

VENV_PY = CONTINUE_ROOT / ".venv" / "Scripts" / "python.exe"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, str | bool]:
        return asdict(self)


def check_venv() -> CheckResult:
    if not VENV_PY.is_file():
        return CheckResult("venv", False, f"missing {VENV_PY}")
    return CheckResult("venv", True, str(VENV_PY))


def check_stress_quick() -> CheckResult:
    from lib.rid_stressor import start_stressor, stop_stressor, stress_alive

    procs = start_stressor(4)
    time.sleep(2.0)
    alive = stress_alive(procs)
    stop_stressor(procs)
    if alive < 4:
        return CheckResult("stress", False, f"{alive}/4 workers alive after 2s")
    return CheckResult("stress", True, f"{alive}/4 ok")


def check_plant_capture() -> CheckResult:
    if not LAST_CAPTURE_PATH.is_file():
        return CheckResult("plant_capture", False, "no plant capture published")
    data = json.loads(LAST_CAPTURE_PATH.read_text(encoding="utf-8"))
    v = data.get("verdict", {})
    verdict = str(v.get("verdict", "UNKNOWN"))
    if verdict in ("PASS", "PASS_FLAT"):
        return CheckResult("plant_capture", True, f"verdict {verdict}")
    return CheckResult("plant_capture", False, f"verdict {verdict}: {v.get('reasons')}")


def check_piston_state() -> CheckResult:
    if not PISTON_STATE_PATH.is_file():
        return CheckResult("piston", False, "no piston_state.json")
    try:
        raw = PISTON_STATE_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            return CheckResult("piston", False, "piston_state.json empty (transient write?)")
        st = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult("piston", False, f"piston_state unreadable: {exc}")
    return CheckResult(
        "piston",
        True,
        f"beat={st.get('beat')} pkg_S_n={st.get('package_s_n')}",
    )


def run_checks(
    *,
    include_stress: bool = True,
    checks: list[tuple[str, Callable[[], CheckResult]]] | None = None,
) -> dict[str, Any]:
    suite = checks or [
        ("venv", check_venv),
        ("plant_capture", check_plant_capture),
        ("piston", check_piston_state),
    ]
    if include_stress:
        suite = [("venv", check_venv), ("stress", check_stress_quick)] + suite[1:]
    results: list[CheckResult] = []
    for name, fn in suite:
        try:
            results.append(fn())
        except Exception as exc:  # noqa: BLE001 — gate must never crash the heartbeat
            results.append(CheckResult(name, False, f"check raised: {exc}"))
    failed = [r for r in results if not r.ok]
    return {
        "ok": len(failed) == 0,
        "foundation_root": str(FOUNDATION_ROOT),
        "rid_artifacts": str(RID_ARTIFACTS),
        "checks": [r.to_dict() for r in results],
        "failed": [r.name for r in failed],
    }


def evaluate_foundation_gate(*, include_stress: bool = False) -> dict[str, Any]:
    """Lightweight gate for automation spine (no stress burn by default)."""
    report = run_checks(include_stress=include_stress)
    return {
        "allow": report["ok"],
        "include_stress": include_stress,
        "checks": report["checks"],
        "failed": report["failed"],
        "foundation_root": report["foundation_root"],
    }
