"""Bridge from Viv Python foundation to Rust security_core.

Fail-closed if the installed .pyd does not match the audit hash sidecar
(self-tamper / module-swap protection).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

_RUST = None
_RUST_ERROR: str | None = None
_INTEGRITY: dict[str, Any] = {"ok": False, "detail": "not_checked"}

_LOCAL_PYD = Path(r"L:\Continue\Viv\security_core\runtime\security_core.pyd")
_LOCAL_HASH = Path(r"L:\Continue\Viv\security_core\runtime\security_core.pyd.sha256")
_LEGACY_PYD = Path(r"L:\Continue\.venv\Lib\site-packages\security_core.pyd")
_LEGACY_HASH = Path(r"L:\Continue\.venv\Lib\site-packages\security_core.pyd.sha256")
_HASH_AUDIT = Path(r"L:\Continue\Viv\foundation\artifacts\audit\security_core.pyd.sha256")


def _select_runtime() -> tuple[Path, Path]:
    if _LOCAL_PYD.is_file():
        return _LOCAL_PYD, _LOCAL_HASH
    return _LEGACY_PYD, _LEGACY_HASH


_PYD, _HASH_SIDE = _select_runtime()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def _expected_hash() -> str | None:
    for path in (_HASH_SIDE, _HASH_AUDIT):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if text.startswith("sha256="):
            for line in text.splitlines():
                if line.startswith("sha256="):
                    return line.split("=", 1)[1].strip().lower()
        if len(text) == 64 and all(c in "0123456789abcdef" for c in text.lower()):
            return text.lower()
    return None


def _verify_integrity() -> tuple[bool, str]:
    if not _PYD.is_file():
        return False, "security_core.pyd missing"
    expected = _expected_hash()
    if expected is None:
        return False, "integrity hash sidecar missing — rebuild with scripts/build.ps1"
    actual = _file_sha256(_PYD)
    if actual != expected:
        return False, f"pyd hash mismatch (expected {expected[:12]}… got {actual[:12]}…) — possible tamper"
    return True, f"sha256={actual} path={_PYD}"


try:
    ok, detail = _verify_integrity()
    _INTEGRITY = {"ok": ok, "detail": detail}
    if not ok:
        _RUST_ERROR = f"integrity_fail: {detail}"
    else:
        spec = importlib.util.spec_from_file_location("security_core", _PYD)
        if spec is None or spec.loader is None:
            raise ImportError(f"unable to load security_core from {_PYD}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["security_core"] = module
        spec.loader.exec_module(module)
        _RUST = module
except (ImportError, OSError) as exc:
    _RUST_ERROR = str(exc)
    _INTEGRITY = {"ok": False, "detail": str(exc)}


def rust_available() -> bool:
    return _RUST is not None and bool(_INTEGRITY.get("ok"))


def rust_module() -> Any:
    """Return the verified Viv-local Rust module for operator surfaces."""
    if not rust_available():
        raise RuntimeError(f"security_core unavailable: {_RUST_ERROR}")
    return _RUST


def runtime_path() -> str:
    """Return the selected runtime module path for evidence and diagnostics."""
    return str(_PYD)


def rust_error() -> str | None:
    return _RUST_ERROR


def integrity_status() -> dict[str, Any]:
    return dict(_INTEGRITY)


def check_ingress(text: str, s_n: float) -> dict[str, Any]:
    if not rust_available():
        return {
            "allowed": False,
            "direction": "IN",
            "stage": "security_in",
            "reason": f"security_core unavailable: {_RUST_ERROR}",
            "s_n": s_n,
        }
    return dict(_RUST.check_ingress(text, float(s_n)))


def check_egress(text: str, s_n: float) -> dict[str, Any]:
    if not rust_available():
        return {
            "allowed": False,
            "direction": "OUT",
            "stage": "security_out",
            "reason": f"security_core unavailable: {_RUST_ERROR}",
            "s_n": s_n,
        }
    return dict(_RUST.check_egress(text, float(s_n)))


def enforce_morality(
    tool_name: str,
    params: dict[str, Any] | str,
    s_n: float,
    forensic_buffer: str = "",
    raw_input: str = "",
) -> dict[str, Any]:
    if not rust_available():
        return {
            "allowed": False,
            "reason": f"security_core unavailable: {_RUST_ERROR}",
            "law": "membrane",
        }
    params_json = params if isinstance(params, str) else json.dumps(params)
    return dict(
        _RUST.enforce_morality(
            tool_name,
            params_json,
            float(s_n),
            forensic_buffer,
            raw_input or None,
        )
    )


def dormancy_threshold() -> float:
    if not rust_available():
        return 0.45
    return float(_RUST.dormancy_threshold())


def check_growth(actuator: str, proposed_r: float, max_r: float) -> dict[str, Any] | None:
    """Rust growth ceiling veto. Returns None if Rust unavailable (Python policy still applies)."""
    if not rust_available():
        return None
    fn = getattr(_RUST, "check_growth", None)
    if fn is None:
        return None
    return dict(fn(str(actuator), float(proposed_r), float(max_r)))


def authorize_backup(request: dict[str, Any] | str) -> dict[str, Any]:
    """Authorize one typed backup operation through the Rust membrane."""
    if not rust_available():
        return {
            "allowed": False,
            "disposition": "DENY",
            "reason": f"security_core unavailable: {_RUST_ERROR}",
            "rule": "membrane",
        }
    fn = getattr(_RUST, "authorize_backup", None)
    if fn is None:
        return {
            "allowed": False,
            "disposition": "DENY",
            "reason": "installed security_core lacks backup security API",
            "rule": "api_version",
        }
    raw = request if isinstance(request, str) else json.dumps(request, separators=(",", ":"))
    return dict(fn(raw))


def verify_backup_ledger() -> dict[str, Any]:
    """Return the Rust backup-ledger hash-chain status."""
    if not rust_available():
        return {"ok": False, "error": f"security_core unavailable: {_RUST_ERROR}"}
    fn = getattr(_RUST, "verify_backup_ledger", None)
    if fn is None:
        return {"ok": False, "error": "installed security_core lacks backup ledger API"}
    try:
        return dict(json.loads(str(fn())))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"malformed backup ledger status: {exc}"}


def authorize_training(request: dict[str, Any] | str) -> dict[str, Any]:
    if not rust_available():
        return {
            "allowed": False,
            "disposition": "DENY",
            "reason": f"security_core unavailable: {_RUST_ERROR}",
            "rule": "membrane",
        }
    fn = getattr(_RUST, "authorize_training", None)
    if fn is None:
        return {
            "allowed": False,
            "disposition": "DENY",
            "reason": "installed security_core lacks training security API",
            "rule": "api_version",
        }
    raw = request if isinstance(request, str) else json.dumps(request, separators=(",", ":"))
    return dict(fn(raw))


def begin_training_lease(request: dict[str, Any] | str) -> dict[str, Any]:
    if not rust_available():
        return authorize_training(request)
    fn = getattr(_RUST, "begin_training_lease", None)
    if fn is None:
        return authorize_training(request)
    raw = request if isinstance(request, str) else json.dumps(request, separators=(",", ":"))
    return dict(fn(raw))


def commit_training_lease(token: str, request: dict[str, Any] | str) -> dict[str, Any]:
    if not rust_available():
        return authorize_training(request)
    fn = getattr(_RUST, "commit_training_lease", None)
    if fn is None:
        return authorize_training(request)
    raw = request if isinstance(request, str) else json.dumps(request, separators=(",", ":"))
    return dict(fn(str(token), raw))


def freeze_training_registry(request: dict[str, Any] | str, payload: str) -> dict[str, Any]:
    if not rust_available():
        return authorize_training(request)
    fn = getattr(_RUST, "freeze_training_registry", None)
    if fn is None:
        return {
            "allowed": False, "disposition": "DENY",
            "reason": "installed security_core lacks freeze API", "rule": "api_version",
        }
    raw = request if isinstance(request, str) else json.dumps(request, separators=(",", ":"))
    return dict(fn(raw, str(payload)))


def quarantine_training_payload(token: str, record_id: str, plaintext: str) -> dict[str, Any]:
    if not rust_available():
        return {
            "allowed": False, "disposition": "DENY",
            "reason": f"security_core unavailable: {_RUST_ERROR}", "rule": "membrane",
        }
    fn = getattr(_RUST, "quarantine_training_payload", None)
    if fn is None:
        return {
            "allowed": False, "disposition": "DENY",
            "reason": "installed security_core lacks quarantine API", "rule": "api_version",
        }
    return dict(fn(str(token), str(record_id), str(plaintext)))


def read_training_quarantine(token: str, record_id: str) -> dict[str, Any]:
    if not rust_available():
        return {
            "allowed": False, "disposition": "DENY",
            "reason": f"security_core unavailable: {_RUST_ERROR}", "rule": "membrane",
        }
    fn = getattr(_RUST, "read_training_quarantine", None)
    if fn is None:
        return {
            "allowed": False, "disposition": "DENY",
            "reason": "installed security_core lacks quarantine API", "rule": "api_version",
        }
    return dict(fn(str(token), str(record_id)))


def verify_training_ledger() -> dict[str, Any]:
    if not rust_available():
        return {"ok": False, "error": f"security_core unavailable: {_RUST_ERROR}"}
    fn = getattr(_RUST, "verify_training_ledger", None)
    if fn is None:
        return {"ok": False, "error": "installed security_core lacks ledger API"}
    try:
        return dict(json.loads(str(fn())))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"malformed ledger status: {exc}"}


def constitution() -> dict[str, Any]:
    if not rust_available():
        return {
            "architect": "Travis Miner",
            "version": "unavailable",
            "armed": False,
            "error": _RUST_ERROR,
            "integrity": integrity_status(),
        }
    fn = getattr(_RUST, "get_constitution", None) or getattr(_RUST, "constitution", None)
    if fn is None:
        return {
            "architect": "Travis Miner",
            "armed": True,
            "version": getattr(_RUST, "__version__", "?"),
            "integrity": integrity_status(),
        }
    data = dict(fn())
    data["armed"] = True
    data["integrity"] = integrity_status()
    return data
