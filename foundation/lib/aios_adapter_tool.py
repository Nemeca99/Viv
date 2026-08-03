"""Callable tool_core adapter — gated list/read/write/shell for Viv AIOS rebuild.

Wraps Viv-native gates only:
  - lib/security_membrane.tool_gate
  - lib/viv_ide.tool_read / tool_write / tool_shell (bounded shell + write roots)

Does NOT import V2 ToolExecutor or bridge_client TCP.
Does NOT mutate security_core / Rust.
"""
from __future__ import annotations

import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.paths import AUTO_ARTIFACTS, FOUNDATION_ROOT, SANDBOX_ROOT, VIV_ROOT  # noqa: E402
from lib.security_membrane import membrane_status, tool_gate  # noqa: E402
from lib.viv_ide import tool_read as _viv_read  # noqa: E402
from lib.viv_ide import tool_shell as _viv_shell  # noqa: E402
from lib.viv_ide import tool_write as _viv_write  # noqa: E402

ADAPTER_ID = "tool_core"
_SMOKE_MARKER = "TOOL_ADAPTER_SMOKE"

# Write surface: sandbox + foundation artifacts only (Law 7; no .cursor / no foundation lib)
_WRITE_ROOTS = (
    SANDBOX_ROOT,
    FOUNDATION_ROOT / "artifacts",
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_posix(p: Path | str) -> str:
    return str(p).replace("\\", "/")


def _norm(p: Path | str) -> str:
    return str(Path(p).resolve()).replace("\\", "/")


def _s_n_default() -> float:
    try:
        from lib.master_rid import load_master_rid

        return float(load_master_rid().master_s_n)
    except Exception:  # noqa: BLE001
        return 0.5


def _under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _under_viv(path: Path) -> bool:
    return _under_root(path, VIV_ROOT)


def _allowed_write(path: Path) -> tuple[bool, str]:
    n = _norm(path)
    for bad in ("/security_core/", "\\security_core\\", "constitution", "cpu_config.json"):
        if bad.replace("\\", "/") in n.replace("\\", "/"):
            return False, f"deny_write:{bad}"
    for root in _WRITE_ROOTS:
        if _under_root(path, root):
            return True, "ok"
    return False, "outside_write_roots_sandbox_or_artifacts_only"


def _deny(op: str, reason: str, *, s_n: float, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "adapter": ADAPTER_ID,
        "op": op,
        "at": _utc(),
        "s_n": float(s_n),
        "error": reason,
    }
    if extra:
        ev.update(extra)
    return {"ok": False, "evidence": ev}


def status() -> dict[str, Any]:
    """Membrane + write-root snapshot. Returns {ok, evidence}."""
    try:
        mem = membrane_status()
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "status",
                "at": _utc(),
                "s_n": _s_n_default(),
                "viv_root": _as_posix(VIV_ROOT),
                "write_roots": [_as_posix(r) for r in _WRITE_ROOTS],
                "membrane": mem,
                "viv_modules": {
                    "security_membrane": "lib.security_membrane.tool_gate",
                    "viv_ide": "lib.viv_ide.tool_read|tool_write|tool_shell",
                },
                "v2_tool_executor": False,
                "bridge_client_tcp": False,
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


def list_dir(path: str, s_n: float) -> dict[str, Any]:
    """Gated directory listing under L:/Continue/Viv only."""
    sn = float(s_n)
    target = Path(path)
    gate = tool_gate("list_dir", {"path": _as_posix(target)}, sn)
    if not gate.get("allowed"):
        return _deny("list_dir", str(gate.get("reason") or "denied"), s_n=sn, extra={"gate": gate})
    if not _under_viv(target):
        return _deny("list_dir", "outside_viv_root", s_n=sn, extra={"path": _as_posix(target)})
    if not target.exists():
        return _deny("list_dir", "not_found", s_n=sn, extra={"path": _norm(target)})
    if not target.is_dir():
        return _deny("list_dir", "not_a_directory", s_n=sn, extra={"path": _norm(target)})
    try:
        entries: list[dict[str, Any]] = []
        for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            entries.append(
                {
                    "name": child.name,
                    "path": _norm(child),
                    "kind": "dir" if child.is_dir() else "file",
                }
            )
            if len(entries) >= 200:
                break
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "list_dir",
                "at": _utc(),
                "s_n": sn,
                "path": _norm(target),
                "n": len(entries),
                "truncated": len(entries) >= 200,
                "entries": entries,
                "gate": {"allowed": True, "stage": gate.get("stage")},
            },
        }
    except OSError as exc:
        return _deny("list_dir", str(exc), s_n=sn, extra={"path": _as_posix(target)})


def read_file(path: str, s_n: float, *, max_chars: int = 12000) -> dict[str, Any]:
    """Gate via security_membrane.tool_gate then read (viv_ide.tool_read wrap)."""
    sn = float(s_n)
    target = Path(path)
    gate = tool_gate("read_file", {"path": _as_posix(target)}, sn)
    if not gate.get("allowed"):
        return _deny("read_file", str(gate.get("reason") or "denied"), s_n=sn, extra={"gate": gate})
    # Prefer Viv root for agentic reads; still allow after gate if viv_ide accepts
    out = _viv_read(str(target), max_chars=max_chars)
    ok = bool(out.get("ok"))
    return {
        "ok": ok,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "read_file",
            "at": _utc(),
            "s_n": sn,
            "path": out.get("path") or _as_posix(target),
            "chars": out.get("chars"),
            "truncated": out.get("truncated"),
            "text": out.get("text") if ok else None,
            "error": out.get("error"),
            "via": "viv_ide.tool_read",
            "gate": {"allowed": True, "stage": gate.get("stage")},
        },
    }


def write_file(path: str, content: str, s_n: float) -> dict[str, Any]:
    """Gate then write under sandbox/artifacts only (viv_ide write safety subset)."""
    sn = float(s_n)
    target = Path(path)
    ok_root, why = _allowed_write(target)
    if not ok_root:
        return _deny("write_file", why, s_n=sn, extra={"path": _as_posix(target)})
    gate = tool_gate("write_file", {"path": _as_posix(target), "content": content}, sn)
    if not gate.get("allowed"):
        return _deny("write_file", str(gate.get("reason") or "denied"), s_n=sn, extra={"gate": gate})
    # viv_ide.tool_write re-checks roots + membrane; path already constrained to sandbox/artifacts
    out = _viv_write(str(target), content, wait_s=45.0)
    ok = bool(out.get("ok"))
    return {
        "ok": ok,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "write_file",
            "at": _utc(),
            "s_n": sn,
            "path": out.get("path") or _norm(target),
            "bytes": out.get("bytes"),
            "error": out.get("error"),
            "via": "viv_ide.tool_write",
            "write_roots": [_as_posix(r) for r in _WRITE_ROOTS],
            "gate": {"allowed": True, "stage": gate.get("stage")},
        },
    }


def run_shell(argv: list[str] | str, s_n: float, *, cwd: str | None = None, timeout_s: float = 60) -> dict[str, Any]:
    """Gate then bounded shell via viv_ide.tool_shell (argv list or cmd string)."""
    sn = float(s_n)
    if isinstance(argv, str):
        cmd = argv.strip()
        if not cmd:
            return _deny("run_shell", "empty_cmd", s_n=sn)
        try:
            args = shlex.split(cmd, posix=False)
        except ValueError as exc:
            return _deny("run_shell", f"bad_cmd:{exc}", s_n=sn)
    else:
        args = [str(a) for a in (argv or [])]
    if not args:
        return _deny("run_shell", "empty_cmd", s_n=sn)
    gate = tool_gate("run_shell", {"cmd": args}, sn)
    if not gate.get("allowed"):
        return _deny("run_shell", str(gate.get("reason") or "denied"), s_n=sn, extra={"gate": gate})
    work = cwd or str(FOUNDATION_ROOT)
    out = _viv_shell(args, cwd=work, timeout_s=timeout_s)
    ok = bool(out.get("ok"))
    return {
        "ok": ok,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "run_shell",
            "at": _utc(),
            "s_n": sn,
            "argv": args,
            "cwd": work,
            "returncode": out.get("returncode"),
            "stdout": out.get("stdout"),
            "stderr": out.get("stderr"),
            "error": out.get("error"),
            "via": "viv_ide.tool_shell",
            "gate": {"allowed": True, "stage": gate.get("stage")},
        },
    }


def run_smoke() -> dict[str, Any]:
    """Exercise list/read/write/run; return ok=True with evidence when all pass."""
    sn = _s_n_default()
    marker = f"{_SMOKE_MARKER}_{_utc().replace(':', '').replace('-', '')}"
    smoke_dir = SANDBOX_ROOT / "work" / "aios_build"
    smoke_path = smoke_dir / f"adapter_tool_smoke_{marker}.txt"
    body = f"{marker} tool_core adapter smoke proof\n"

    st = status()
    listed = list_dir(str(SANDBOX_ROOT / "code"), sn)
    written = write_file(str(smoke_path), body, sn)
    read = read_file(str(smoke_path), sn)
    text = ((read.get("evidence") or {}).get("text") or "")
    found = marker in text
    # Bounded, non-destructive: venv python -c print
    py = Path(r"L:/Continue/.venv/Scripts/python.exe")
    shelled = run_shell(
        [str(py), "-c", f"print({marker!r})"],
        sn,
        cwd=str(FOUNDATION_ROOT),
        timeout_s=30,
    )
    shell_out = ((shelled.get("evidence") or {}).get("stdout") or "")
    shell_ok = bool(shelled.get("ok")) and marker in shell_out

    # Outside-Viv list must fail
    outside = list_dir(r"L:/Continue/FSAA", sn)
    outside_denied = not bool(outside.get("ok"))

    ok = (
        bool(st.get("ok"))
        and bool(listed.get("ok"))
        and bool(written.get("ok"))
        and bool(read.get("ok"))
        and found
        and shell_ok
        and outside_denied
        and (st.get("evidence") or {}).get("v2_tool_executor") is False
        and (st.get("evidence") or {}).get("bridge_client_tcp") is False
    )
    return {
        "ok": ok,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "smoke",
            "at": _utc(),
            "s_n": sn,
            "marker": marker,
            "smoke_path": _as_posix(smoke_path),
            "status_ok": bool(st.get("ok")),
            "list_ok": bool(listed.get("ok")),
            "list_n": (listed.get("evidence") or {}).get("n"),
            "write_ok": bool(written.get("ok")),
            "read_ok": bool(read.get("ok")),
            "found": found,
            "shell_ok": shell_ok,
            "outside_viv_denied": outside_denied,
            "v2_tool_executor": (st.get("evidence") or {}).get("v2_tool_executor"),
            "bridge_client_tcp": (st.get("evidence") or {}).get("bridge_client_tcp"),
            "status": st,
            "list_dir": listed,
            "write_file": written,
            "read_file": read,
            "run_shell": shelled,
            "outside_list": outside,
        },
    }


if __name__ == "__main__":
    import json

    result = run_smoke()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("ok") else 1)
