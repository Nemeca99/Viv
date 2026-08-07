"""Callable support_core adapter — Viv health bus + V1 read-mirror (REAL).

Registry id: support_core
V1 source (READ-ONLY mirror): D:/LocalAi/AIOS_V1/support_core

API: status(), health(), run_smoke()

Maps V1 embed/cache/health-bus role onto Viv foundation_health + sandbox/CARMA
artifact surfaces. V1 path is surveyed read-only (markers only) — never imported,
executed, or written. Does not mutate security_core. Does not write to D:.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.foundation_health import evaluate_foundation_gate  # noqa: E402
from lib.paths import AUTO_ARTIFACTS, CARMA_ARTIFACTS, SANDBOX_ROOT  # noqa: E402
from lib.security_membrane import membrane_status  # noqa: E402
from lib.support_core import diagnostic_report, module_status as cpu_module_status  # noqa: E402

ADAPTER_ID = "support_core"
REGISTRY_ID = "support_core"

V1_SUPPORT = Path(r"D:/LocalAi/AIOS_V1/support_core")
EVIDENCE_DIR = AUTO_ARTIFACTS / "support"
ADAPTER_EVIDENCE = EVIDENCE_DIR / "adapter_smoke.json"

# Read-mirror markers only — never import these modules
_V1_MARKERS = (
    "support_core.py",
    "hybrid_support_core.py",
    "core/health_checker.py",
    "core/cache_operations.py",
    "core/embedding_operations.py",
    "README.md",
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_posix(p: Path | str) -> str:
    return str(p).replace("\\", "/")


def _s_n() -> float:
    try:
        from lib.master_rid import load_master_rid

        return float(load_master_rid().master_s_n)
    except Exception:  # noqa: BLE001
        return 0.5


def _dir_stats(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        return {"path": _as_posix(path), "exists": False, "entries": 0}
    try:
        entries = list(path.iterdir())
        n = len(entries)
        names = sorted((p.name for p in entries), key=str.lower)[:12]
    except OSError as exc:
        return {"path": _as_posix(path), "exists": True, "entries": 0, "error": str(exc)}
    return {
        "path": _as_posix(path),
        "exists": True,
        "entries": n,
        "sample": names,
    }


def _v1_mirror() -> dict[str, Any]:
    """Read-only presence survey of V1 support_core. Never import/execute."""
    present = V1_SUPPORT.is_dir()
    markers: dict[str, bool] = {}
    if present:
        for rel in _V1_MARKERS:
            markers[rel] = (V1_SUPPORT / rel).is_file()
    return {
        "v1_path": _as_posix(V1_SUPPORT),
        "v1_on_disk": present,
        "markers": markers,
        "v1_read_mirror_only": True,
        "viv_executes_v1": False,
        "viv_writes_d": False,
        "note": (
            "V1 support_core is a read-mirror survey only (embed/cache/health bus legacy). "
            "Viv health uses foundation_health + sandbox/CARMA; do not import V1 modules."
        ),
    }


def status() -> dict[str, Any]:
    """V1 mirror + Viv health surfaces. Returns {ok, evidence}."""
    try:
        mem = membrane_status()
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "registry_id": REGISTRY_ID,
                "op": "status",
                "at": _utc(),
                "s_n": _s_n(),
                "membrane": mem,
                "v1": _v1_mirror(),
                "viv_surfaces": {
                    "sandbox": _dir_stats(SANDBOX_ROOT),
                    "carma": _dir_stats(CARMA_ARTIFACTS),
                    "auto": _dir_stats(AUTO_ARTIFACTS),
                },
                "viv_modules": {
                    "foundation_health": "lib.foundation_health.evaluate_foundation_gate",
                    "membrane": "lib.security_membrane.membrane_status",
                    "cpu_planner": "lib.support_core.diagnostic_report",
                },
                "cpu_planner": cpu_module_status(),
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "status",
                "at": _utc(),
                "error": str(exc),
            },
        }


def cpu_plan(
    checks: list[dict[str, Any]],
    cache_entries: list[dict[str, Any]],
    *,
    sample_text: str | None = None,
) -> dict[str, Any]:
    """Evaluate supplied support evidence without probing or mutating live state."""
    report = diagnostic_report(checks, cache_entries, sample_text=sample_text)
    return {
        "ok": bool(report.get("ok")),
        "report": report,
        "live_probe_performed": False,
        "writes_performed": False,
        "execution_performed": False,
        "llm_authority": False,
    }


def health() -> dict[str, Any]:
    """Viv foundation health bus (no stress burn) + cache/sandbox presence."""
    sn = _s_n()
    try:
        gate = evaluate_foundation_gate(include_stress=False)
        mem = membrane_status()
        sandbox = _dir_stats(SANDBOX_ROOT)
        carma = _dir_stats(CARMA_ARTIFACTS)
        code_dir = SANDBOX_ROOT / "code"
        code_n = 0
        if code_dir.is_dir():
            try:
                code_n = sum(1 for p in code_dir.iterdir() if p.is_file())
            except OSError:
                code_n = 0
        checks = gate.get("checks") or []
        failed = gate.get("failed") or []
        # Support-bus health: foundation gate + sandbox home present
        ok = bool(gate.get("allow")) and bool(sandbox.get("exists"))
        return {
            "ok": ok,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "health",
                "at": _utc(),
                "s_n": sn,
                "foundation_allow": bool(gate.get("allow")),
                "foundation_failed": failed,
                "foundation_checks": checks,
                "include_stress": False,
                "membrane_armed": bool(mem.get("armed")),
                "sandbox": sandbox,
                "sandbox_code_files": code_n,
                "carma": carma,
                "v1_read_mirror_only": True,
                "viv_executes_v1": False,
                "via": "foundation_health.evaluate_foundation_gate",
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "health",
                "at": _utc(),
                "s_n": sn,
                "error": str(exc),
                "v1_read_mirror_only": True,
                "viv_executes_v1": False,
            },
        }


def run_smoke() -> dict[str, Any]:
    """Prove status + health; affirm V1 is read-mirror only."""
    st = status()
    sev = st.get("evidence") or {}
    hv = health()
    hev = hv.get("evidence") or {}
    v1 = sev.get("v1") or {}
    ok = (
        bool(st.get("ok"))
        and bool(hv.get("ok"))
        and v1.get("v1_read_mirror_only") is True
        and v1.get("viv_executes_v1") is False
        and v1.get("viv_writes_d") is False
        and hev.get("v1_read_mirror_only") is True
        and bool((sev.get("viv_surfaces") or {}).get("sandbox", {}).get("exists"))
    )
    evidence = {
        "adapter": ADAPTER_ID,
        "op": "smoke",
        "at": _utc(),
        "s_n": sev.get("s_n") or hev.get("s_n"),
        "status_ok": bool(st.get("ok")),
        "health_ok": bool(hv.get("ok")),
        "foundation_allow": hev.get("foundation_allow"),
        "foundation_failed": hev.get("foundation_failed"),
        "v1_on_disk": v1.get("v1_on_disk"),
        "v1_read_mirror_only": v1.get("v1_read_mirror_only"),
        "viv_executes_v1": v1.get("viv_executes_v1"),
        "sandbox_entries": ((sev.get("viv_surfaces") or {}).get("sandbox") or {}).get("entries"),
        "status": st,
        "health": hv,
    }
    try:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        slim = {
            "ok": ok,
            "at": evidence["at"],
            "health_ok": evidence["health_ok"],
            "foundation_allow": evidence["foundation_allow"],
            "foundation_failed": evidence["foundation_failed"],
            "v1_on_disk": evidence["v1_on_disk"],
            "v1_read_mirror_only": evidence["v1_read_mirror_only"],
            "viv_executes_v1": evidence["viv_executes_v1"],
        }
        ADAPTER_EVIDENCE.write_text(json.dumps(slim, indent=2), encoding="utf-8")
        evidence["evidence_path"] = _as_posix(ADAPTER_EVIDENCE)
    except OSError as exc:
        evidence["evidence_write_error"] = str(exc)
    return {"ok": ok, "evidence": evidence}


if __name__ == "__main__":
    result = run_smoke()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("ok") else 1)
