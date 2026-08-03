"""Smoke-test the CPU neuro-symbolic reasoning stack (not a transformer)."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

from lib.paths import AUTOMATION_ROOT, CONTINUE_ROOT, FOUNDATION_ROOT

AIOS_V2 = CONTINUE_ROOT / "FSAA" / "Luna" / "AIOS_V2"


def _py_ok(script: Path, *args: str, timeout: int = 60) -> tuple[bool, str]:
    if not script.is_file():
        return False, f"missing {script}"
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(script.parent),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    detail = (proc.stdout or proc.stderr or "").strip()[:300]
    return proc.returncode == 0, detail or f"exit {proc.returncode}"


def _import_ok(rel: str) -> tuple[bool, str]:
    path = AIOS_V2 / rel.replace("/", "\\").replace("\\", "/")
    if not path.is_file():
        return False, f"missing {path}"
    name = "viv_reason_" + rel.replace("/", "_").replace(".", "_")
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            return False, "spec failed"
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return True, "import ok"
    except Exception as ex:
        return False, str(ex)


def run_reasoning_smoke(cfg: dict[str, Any]) -> dict[str, Any]:
    foundation = Path(cfg["reasoning"]["foundation_dir"])
    results: dict[str, Any] = {}

    rid = foundation / "rid_main.py"
    ok, detail = _py_ok(rid, "sample")
    results["rid_main"] = {"ok": ok, "detail": detail}

    uml = foundation / "uml_main.py"
    ok, detail = _py_ok(uml, "eval", "[3,4]")
    results["uml_main"] = {"ok": ok, "detail": detail}

    auto = foundation / "auto_main.py"
    ok, detail = _py_ok(auto, "paths")
    results["auto_main"] = {"ok": ok, "detail": detail}

    ok, detail = _py_ok(auto, "run", "--once", "--quiet", "--allow-denied")
    results["auto_run"] = {"ok": ok, "detail": detail}

    ok, detail = _py_ok(foundation / "guardian_main.py", "demo")
    results["guardian_v2"] = {"ok": ok, "detail": detail}

    ok, detail = _import_ok("consciousness_core/guardian_v2_bridge.py")
    results["guardian_bridge"] = {"ok": ok, "detail": detail}

    for name, rel in (
        ("security_core", "security_core/security_core.py"),
        ("intent_resolver", "consciousness_core/intent_resolver.py"),
    ):
        ok, detail = _import_ok(rel)
        results[name] = {"ok": ok, "detail": detail}

    # heart uses package-relative imports — test via sys.path, not bare file load
    if str(AIOS_V2) not in sys.path:
        sys.path.insert(0, str(AIOS_V2))
    try:
        from consciousness_core.biological.heart import Heart  # noqa: F401

        results["heart"] = {"ok": True, "detail": "Heart import ok"}
    except Exception as ex:
        results["heart"] = {"ok": False, "detail": str(ex)}

    hb = AUTOMATION_ROOT / "master_ai_heartbeat_service.py"
    ok, detail = (hb.is_file(), str(hb) if hb.is_file() else "missing")
    results["automation_heartbeat"] = {"ok": ok, "detail": detail}

    results["all_ok"] = all(v.get("ok") for v in results.values() if isinstance(v, dict))
    return results
