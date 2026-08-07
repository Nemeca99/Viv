"""Callable utils_core adapter — Viv path helpers + V1 read-mirror (REAL).

Registry id: utils_core
V1 source (READ-ONLY mirror): D:/LocalAi/AIOS_V1/utils_core
V2: no utils_core tree on disk (surveyed absent)

API: status(), resolve_path(path), list_roots(), run_smoke()

Maps V1 bridges/monitoring utils onto Viv lib.paths + safe path resolve within
L:/Continue. V1 is surveyed read-only (markers only) — never imported, executed,
or written. Does not mutate security_core. Does not write to D:.
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

from lib.paths import (  # noqa: E402
    ARTIFACTS,
    AUTO_ARTIFACTS,
    CARMA_ARTIFACTS,
    CONTINUE_ROOT,
    FOUNDATION_ROOT,
    RID_ARTIFACTS,
    SANDBOX_ROOT,
    VIV_ROOT,
)
from lib.utils_core import (  # noqa: E402
    classify_path,
    module_status as cpu_module_status,
    plan_bridge_call,
    plan_file_operation,
    plan_retry,
    timestamp_age,
    validate_input,
    validate_message_envelope,
)

ADAPTER_ID = "utils_core"
REGISTRY_ID = "utils_core"

V1_UTILS = Path(r"D:/LocalAi/AIOS_V1/utils_core")
V2_UTILS = Path(r"L:/Continue/FSAA/Luna/AIOS_V2/utils_core")
EVIDENCE_DIR = AUTO_ARTIFACTS / "utils"
ADAPTER_EVIDENCE = EVIDENCE_DIR / "adapter_smoke.json"

_V1_MARKERS = (
    "core.py",
    "README.md",
    "unicode_safe_output.py",
    "model_config_loader.py",
    "bridges/__init__.py",
    "bridges/powershell_bridge.py",
    "monitoring/__init__.py",
    "monitoring/provenance.py",
    "validation/json_standards.py",
    "resilience/resilience_policies.py",
)

# Resolve allowed only under Continue plane (never escalate to D: writes)
_RESOLVE_ROOTS = (CONTINUE_ROOT, VIV_ROOT, FOUNDATION_ROOT)


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
    """Read-only presence survey of V1 utils_core. Never import/execute."""
    present = V1_UTILS.is_dir()
    markers: dict[str, bool] = {}
    if present:
        for rel in _V1_MARKERS:
            markers[rel] = (V1_UTILS / rel).is_file()
    return {
        "v1_path": _as_posix(V1_UTILS),
        "v1_on_disk": present,
        "markers": markers,
        "marker_hits": sum(1 for v in markers.values() if v),
        "v1_read_mirror_only": True,
        "viv_executes_v1": False,
        "viv_writes_d": False,
        "v2_utils_on_disk": V2_UTILS.is_dir(),
        "note": (
            "V1 utils_core is bridges/monitoring legacy — read-mirror only. "
            "Viv uses lib.paths + resolve_path; do not import V1 bridges."
        ),
    }


def _canonical_roots() -> dict[str, dict[str, Any]]:
    return {
        "continue": _dir_stats(CONTINUE_ROOT),
        "viv": _dir_stats(VIV_ROOT),
        "foundation": _dir_stats(FOUNDATION_ROOT),
        "artifacts": _dir_stats(ARTIFACTS),
        "auto": _dir_stats(AUTO_ARTIFACTS),
        "sandbox": _dir_stats(SANDBOX_ROOT),
        "carma": _dir_stats(CARMA_ARTIFACTS),
        "rid": _dir_stats(RID_ARTIFACTS),
    }


def status() -> dict[str, Any]:
    """Canonical Viv roots + V1 mirror. Returns {ok, evidence}."""
    try:
        roots = _canonical_roots()
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "registry_id": REGISTRY_ID,
                "op": "status",
                "at": _utc(),
                "s_n": _s_n(),
                "v1": _v1_mirror(),
                "roots": roots,
                "viv_modules": {
                    "paths": "lib.paths",
                    "resolve": "lib.aios_adapter_utils.resolve_path",
                    "cpu_planner": "lib.utils_core",
                },
                "cpu_planner": cpu_module_status(),
                "viv_ports_v1_bridges": False,
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
    *,
    value: Any = None,
    value_kind: str = "json",
    retry: dict[str, Any] | None = None,
    path: str | None = None,
    path_operation: str = "inspect",
    allowed_roots: tuple[str, ...] = (),
    message: dict[str, Any] | None = None,
    bridge: str | None = None,
    bridge_action: str | None = None,
    observed_at: str | None = None,
    now: str | None = None,
    stale_after_seconds: float = 3.0,
) -> dict[str, Any]:
    """Combine pure utility plans without touching live state."""
    sections: dict[str, Any] = {
        "module": cpu_module_status(),
        "input": validate_input(value, kind=value_kind),
    }
    if retry is not None:
        sections["retry"] = plan_retry(**retry)
    if path is not None:
        sections["path"] = classify_path(path, allowed_roots=allowed_roots, operation=path_operation)
        sections["file_operation"] = plan_file_operation(
            path,
            operation=path_operation,
            allowed_roots=allowed_roots,
        )
    if message is not None:
        sections["message"] = validate_message_envelope(message)
    if bridge is not None or bridge_action is not None:
        sections["bridge"] = plan_bridge_call(bridge or "", bridge_action or "")
    if observed_at is not None and now is not None:
        sections["freshness"] = timestamp_age(
            observed_at,
            now,
            stale_after_seconds=stale_after_seconds,
        )
    failed = [name for name, result in sections.items() if name != "module" and result.get("ok") is False]
    return {
        "ok": not failed,
        "sections": sections,
        "failed_sections": failed,
        "filesystem_read_performed": False,
        "filesystem_write_performed": False,
        "execution_performed": False,
        "network_probe_performed": False,
        "sleep_performed": False,
        "llm_authority": False,
    }


def list_roots() -> dict[str, Any]:
    """List Viv canonical path roots with existence/entry counts."""
    try:
        roots = _canonical_roots()
        present = sum(1 for r in roots.values() if r.get("exists"))
        return {
            "ok": present >= 4,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "list_roots",
                "at": _utc(),
                "s_n": _s_n(),
                "n_roots": len(roots),
                "n_present": present,
                "roots": roots,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "list_roots",
                "at": _utc(),
                "error": str(exc),
            },
        }


def resolve_path(path: str) -> dict[str, Any]:
    """Normalize a path under L:/Continue; reject traversal outside Continue plane."""
    raw = (path or "").strip()
    if not raw:
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "resolve_path",
                "at": _utc(),
                "error": "empty_path",
            },
        }
    try:
        # Expand known aliases used by bridges/monitoring utils
        aliases = {
            "@foundation": FOUNDATION_ROOT,
            "@viv": VIV_ROOT,
            "@sandbox": SANDBOX_ROOT,
            "@artifacts": ARTIFACTS,
            "@auto": AUTO_ARTIFACTS,
            "@continue": CONTINUE_ROOT,
        }
        candidate = Path(raw)
        for key, root in aliases.items():
            if raw == key or raw.startswith(key + "/") or raw.startswith(key + "\\"):
                rest = raw[len(key) :].lstrip("/\\")
                candidate = root / rest if rest else root
                break
        resolved = candidate.resolve()
        under: str | None = None
        for root in _RESOLVE_ROOTS:
            try:
                resolved.relative_to(root.resolve())
                under = _as_posix(root)
                break
            except ValueError:
                continue
        if under is None:
            return {
                "ok": False,
                "evidence": {
                    "adapter": ADAPTER_ID,
                    "op": "resolve_path",
                    "at": _utc(),
                    "input": raw,
                    "resolved": _as_posix(resolved),
                    "error": "outside_continue_plane",
                    "viv_writes_d": False,
                },
            }
        exists = resolved.exists()
        kind = (
            "dir"
            if resolved.is_dir()
            else ("file" if resolved.is_file() else ("missing" if not exists else "other"))
        )
        meta: dict[str, Any] = {
            "adapter": ADAPTER_ID,
            "op": "resolve_path",
            "at": _utc(),
            "input": raw,
            "resolved": _as_posix(resolved),
            "under_root": under,
            "exists": exists,
            "kind": kind,
            "posix": _as_posix(resolved),
        }
        if resolved.is_file():
            try:
                meta["bytes"] = resolved.stat().st_size
            except OSError:
                pass
        return {"ok": True, "evidence": meta}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "resolve_path",
                "at": _utc(),
                "input": raw,
                "error": str(exc),
            },
        }


def run_smoke() -> dict[str, Any]:
    """Prove real path resolve + root listing; affirm V1 is read-mirror only."""
    st = status()
    lr = list_roots()
    rp_f = resolve_path("@foundation/lib/paths.py")
    rp_s = resolve_path(str(SANDBOX_ROOT / "work" / "aios_build" / "MANIFEST.md"))
    # Must deny D: write-plane resolve as "ok under Continue" — D: utils is outside
    rp_deny = resolve_path(r"D:/LocalAi/AIOS_V1/utils_core/core.py")
    sev = st.get("evidence") or {}
    v1 = sev.get("v1") or {}
    fev = rp_f.get("evidence") or {}
    sev2 = rp_s.get("evidence") or {}
    den = rp_deny.get("evidence") or {}
    ok = (
        bool(st.get("ok"))
        and bool(lr.get("ok"))
        and bool(rp_f.get("ok"))
        and bool(fev.get("exists"))
        and fev.get("kind") == "file"
        and bool(rp_s.get("ok"))
        and bool(sev2.get("exists"))
        and rp_deny.get("ok") is False
        and den.get("error") == "outside_continue_plane"
        and v1.get("v1_read_mirror_only") is True
        and v1.get("viv_executes_v1") is False
        and v1.get("viv_writes_d") is False
        and sev.get("viv_ports_v1_bridges") is False
    )
    evidence = {
        "adapter": ADAPTER_ID,
        "op": "smoke",
        "at": _utc(),
        "s_n": sev.get("s_n"),
        "status_ok": bool(st.get("ok")),
        "list_roots_ok": bool(lr.get("ok")),
        "resolve_foundation_ok": bool(rp_f.get("ok")),
        "resolve_manifest_ok": bool(rp_s.get("ok")),
        "deny_d_ok": rp_deny.get("ok") is False,
        "foundation_resolved": fev.get("resolved"),
        "manifest_resolved": sev2.get("resolved"),
        "v1_on_disk": v1.get("v1_on_disk"),
        "v1_marker_hits": v1.get("marker_hits"),
        "v1_read_mirror_only": v1.get("v1_read_mirror_only"),
        "viv_executes_v1": v1.get("viv_executes_v1"),
        "status": st,
        "list_roots": lr,
        "resolve_foundation": rp_f,
        "resolve_manifest": rp_s,
        "resolve_deny_d": rp_deny,
    }
    try:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        slim = {
            "ok": ok,
            "at": evidence["at"],
            "resolve_foundation_ok": evidence["resolve_foundation_ok"],
            "resolve_manifest_ok": evidence["resolve_manifest_ok"],
            "deny_d_ok": evidence["deny_d_ok"],
            "v1_on_disk": evidence["v1_on_disk"],
            "v1_marker_hits": evidence["v1_marker_hits"],
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
