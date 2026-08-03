"""Callable nox_forge_core adapter — DLL presence status ONLY (REAL, safe).

Registry id: nox_forge_core
V2 source: L:/Continue/FSAA/Luna/AIOS_V2/nox_forge_core

API: status(), run_smoke()

Reports Cargo.toml + built DLL path/size via filesystem metadata only.
NEVER LoadLibrary / ctypes / import / pyo3-load the DLL (unsafe governor/sensory code).
Does not mutate security_core. Does not write to D:.
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

from lib.paths import AUTO_ARTIFACTS  # noqa: E402

ADAPTER_ID = "nox_forge_core"
REGISTRY_ID = "nox_forge_core"

V2_NOX = Path(r"L:/Continue/FSAA/Luna/AIOS_V2/nox_forge_core")
DLL_CANDIDATES = (
    V2_NOX / "target" / "release" / "nox_forge_core.dll",
    V2_NOX / "target" / "debug" / "nox_forge_core.dll",
    V2_NOX / "nox_forge_core.dll",
)
EVIDENCE_DIR = AUTO_ARTIFACTS / "nox"
ADAPTER_EVIDENCE = EVIDENCE_DIR / "adapter_smoke.json"


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


def _file_meta(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    return {
        "path": _as_posix(path),
        "bytes": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
    }


def _survey_dll() -> dict[str, Any]:
    """Filesystem presence only — never load the binary."""
    found: list[dict[str, Any]] = []
    for cand in DLL_CANDIDATES:
        meta = _file_meta(cand)
        if meta:
            found.append(meta)
    primary = found[0] if found else None
    return {
        "dll_present": primary is not None,
        "dll": primary,
        "dll_candidates_checked": [_as_posix(p) for p in DLL_CANDIDATES],
        "dll_hits": found,
        "loaded": False,
        "load_attempted": False,
        "note": "Status-only; DLL never loaded (ctypes/LoadLibrary/pyo3 forbidden).",
    }


def status() -> dict[str, Any]:
    """Report nox_forge crate + DLL presence without loading. Returns {ok, evidence}."""
    try:
        cargo = V2_NOX / "Cargo.toml"
        src_lib = V2_NOX / "src" / "lib.rs"
        governor = V2_NOX / "src" / "governor.rs"
        dll = _survey_dll()
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "registry_id": REGISTRY_ID,
                "op": "status",
                "at": _utc(),
                "s_n": _s_n(),
                "v2_root": _as_posix(V2_NOX),
                "v2_root_exists": V2_NOX.is_dir(),
                "cargo_toml": _file_meta(cargo),
                "src_lib_rs": src_lib.is_file(),
                "src_governor_rs": governor.is_file(),
                "crate_type": "cdylib",
                "role": "Rust sensory/governor DLL (legacy Luna)",
                **dll,
                "viv_loads_dll": False,
                "security_core_mutated": False,
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
                "loaded": False,
                "load_attempted": False,
            },
        }


def run_smoke() -> dict[str, Any]:
    """Prove status reports presence metadata and never claims a load."""
    st = status()
    sev = st.get("evidence") or {}
    ok = (
        bool(st.get("ok"))
        and sev.get("loaded") is False
        and sev.get("load_attempted") is False
        and sev.get("viv_loads_dll") is False
        and sev.get("security_core_mutated") is False
        and bool(sev.get("v2_root_exists"))
        and bool(sev.get("src_lib_rs"))
        # DLL may or may not be built; presence is informational
        and isinstance(sev.get("dll_present"), bool)
    )
    evidence = {
        "adapter": ADAPTER_ID,
        "op": "smoke",
        "at": _utc(),
        "s_n": sev.get("s_n"),
        "status_ok": bool(st.get("ok")),
        "dll_present": sev.get("dll_present"),
        "dll_path": (sev.get("dll") or {}).get("path") if isinstance(sev.get("dll"), dict) else None,
        "dll_bytes": (sev.get("dll") or {}).get("bytes") if isinstance(sev.get("dll"), dict) else None,
        "loaded": sev.get("loaded"),
        "load_attempted": sev.get("load_attempted"),
        "viv_loads_dll": sev.get("viv_loads_dll"),
        "status": st,
    }
    try:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        slim = {
            "ok": ok,
            "at": evidence["at"],
            "dll_present": evidence["dll_present"],
            "dll_path": evidence["dll_path"],
            "dll_bytes": evidence["dll_bytes"],
            "loaded": False,
            "load_attempted": False,
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
