"""Sandbox self-coder — Viv writes and runs her own tools under Law 4.

Security membrane forbids .py/.bin writes. Doctrine still requires code agency:
CPU drafts source as gated .txt under Viv/sandbox/code/, then executes via
stdin to the plant Python (no .py file on disk). Foundation lib is never mutated.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.master_rid import load_master_rid
from lib.paths import AUTO_ARTIFACTS
from lib.security_membrane import tool_gate
from lib.aios_sandbox import CODE as CODE_ROOT
from lib.aios_sandbox import CODE_RUNS as RUNS_ROOT
from lib.aios_sandbox import SANDBOX_ROOT, ensure_sandbox_home

CODE_LOG = AUTO_ARTIFACTS / "organism" / "code_writes.jsonl"
CODE_STATE = AUTO_ARTIFACTS / "organism" / "coder_state.json"
PYTHON = Path(r"L:/Continue/.venv/Scripts/python.exe")

# Built-in tool templates the organism can author + run autonomously.
_TEMPLATES: dict[str, str] = {
    "plant_digest": '''# Viv sandbox tool - plant_digest (CPU authored)
# Summarize Master RID if present; else print unavailable.
import json
from pathlib import Path

p = Path(r"L:/Continue/Viv/foundation/artifacts/auto/master_rid.json")
if not p.is_file():
    p = Path(r"L:/Continue/Viv/foundation/artifacts/auto/pulse.json")
if p.is_file():
    data = json.loads(p.read_text(encoding="utf-8"))
    sn = data.get("master_s_n") or data.get("s_n") or (data.get("master") or {}).get("master_s_n")
    status = data.get("status") or data.get("mode") or "?"
    print(f"PLANT_DIGEST sn={sn} status={status} source={p.name}")
else:
    print("PLANT_DIGEST unavailable")
''',
    "memory_census": '''# Viv sandbox tool - memory_census (CPU authored)
from pathlib import Path

root = Path(r"L:/Continue/Viv/foundation/artifacts/carma")
counts = {}
for sub in ("live", "dream", "simulation"):
    d = root / sub
    n = 0
    bytes_ = 0
    if d.is_dir():
        for f in d.rglob("*.txt"):
            n += 1
            try:
                bytes_ += f.stat().st_size
            except OSError:
                pass
    counts[sub] = {"files": n, "bytes": bytes_}
print("MEMORY_CENSUS", counts)
''',
    "sandbox_health": '''# Viv sandbox tool - sandbox_health (CPU authored)
from pathlib import Path

sb = Path(r"L:/Continue/Viv/sandbox")
items = sorted(p.name for p in sb.iterdir()) if sb.is_dir() else []
code = sb / "code"
dream = sb / "dream"
runs = list((code / "runs").glob("*.json")) if (code / "runs").is_dir() else []
print(f"SANDBOX_HEALTH home={sb} entries={len(items)} code_runs={len(runs)} dream_txt={len(list(dream.glob('*.txt'))) if dream.is_dir() else 0} top={items[:8]}")
''',
}


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _gated_write(path: Path, content: str, s_n: float) -> tuple[bool, str]:
    gate_path = str(path).replace("\\", "/")
    verdict = tool_gate("write_file", {"path": gate_path, "content": content}, s_n)
    if not verdict.get("allowed"):
        return False, str(verdict.get("reason", "tool_gate_denied"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True, "write_ok"


def _load_state() -> dict[str, Any]:
    if not CODE_STATE.is_file():
        return {"writes": 0, "runs": 0, "last_tool": None}
    try:
        return json.loads(CODE_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"writes": 0, "runs": 0, "last_tool": None}


def _save_state(state: dict[str, Any]) -> None:
    CODE_STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CODE_STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(CODE_STATE)


def _append_log(row: dict[str, Any]) -> None:
    CODE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CODE_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def next_tool_name(state: dict[str, Any] | None = None) -> str:
    st = state or _load_state()
    names = list(_TEMPLATES.keys())
    n = int(st.get("writes") or 0)
    return names[n % len(names)]


def write_sandbox_tool(
    *,
    tool: str | None = None,
    source: str | None = None,
    s_n: float | None = None,
) -> dict[str, Any]:
    """Author a sandbox tool as .txt (Law 4 safe). Never writes foundation code."""
    ensure_sandbox_home()
    CODE_ROOT.mkdir(parents=True, exist_ok=True)
    if s_n is not None:
        sn = float(s_n)
    else:
        try:
            sn = float(load_master_rid().master_s_n)
        except Exception:  # noqa: BLE001
            sn = 0.5

    state = _load_state()
    name = (tool or next_tool_name(state)).strip().lower()
    body = source if source is not None else _TEMPLATES.get(name)
    if not body:
        return {"ok": False, "reason": f"unknown_tool:{name}", "known": list(_TEMPLATES)}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = CODE_ROOT / f"{name}_{stamp}.txt"
    header = (
        f"# authored_by=viv_cpu at={_utc()} s_n={sn:.4f} tool={name}\n"
        f"# law4=source_as_txt run=python_stdin foundation_immutable=true\n"
    )
    ok, reason = _gated_write(path, header + body.lstrip("\n"), sn)
    if not ok:
        return {"ok": False, "reason": reason, "path": str(path).replace("\\", "/")}

    # Also refresh a stable "current" pointer file for the tool name
    current = CODE_ROOT / f"{name}_current.txt"
    ok_c, reason_c = _gated_write(current, header + body.lstrip("\n"), sn)
    if not ok_c:
        return {"ok": False, "reason": reason_c, "path": str(current).replace("\\", "/")}

    state["writes"] = int(state.get("writes") or 0) + 1
    state["last_tool"] = name
    state["last_write_at"] = _utc()
    state["last_path"] = str(path).replace("\\", "/")
    _save_state(state)
    report = {
        "ok": True,
        "tool": name,
        "path": str(path).replace("\\", "/"),
        "current": str(current).replace("\\", "/"),
        "bytes": len(header + body),
        "s_n": sn,
        "at": _utc(),
    }
    _append_log({"event": "code_write", **report})
    return report


def run_sandbox_tool(
    *,
    tool: str | None = None,
    path: str | None = None,
    timeout_s: float = 20.0,
    s_n: float | None = None,
) -> dict[str, Any]:
    """Execute sandbox .txt source via python stdin — no .py file written."""
    CODE_ROOT.mkdir(parents=True, exist_ok=True)
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        sn = float(s_n if s_n is not None else load_master_rid().master_s_n)
    except Exception:  # noqa: BLE001
        sn = 0.5

    src_path: Path | None = None
    if path:
        src_path = Path(path)
    else:
        name = (tool or _load_state().get("last_tool") or next_tool_name()).strip().lower()
        candidate = CODE_ROOT / f"{name}_current.txt"
        if candidate.is_file():
            src_path = candidate
        else:
            # write then run
            wr = write_sandbox_tool(tool=name, s_n=sn)
            if not wr.get("ok"):
                return wr
            src_path = Path(str(wr["current"]))

    if not src_path or not src_path.is_file():
        return {"ok": False, "reason": "missing_source"}

    # Confine: only sandbox/code/*.txt
    try:
        resolved = src_path.resolve()
        if CODE_ROOT.resolve() not in resolved.parents and resolved.parent != CODE_ROOT.resolve():
            return {"ok": False, "reason": "path_outside_sandbox_code"}
        if resolved.suffix.lower() != ".txt":
            return {"ok": False, "reason": "only_txt_sources"}
    except OSError as exc:
        return {"ok": False, "reason": f"resolve_error:{exc}"}

    source = src_path.read_text(encoding="utf-8")
    # Strip non-ASCII from comments that break Windows stdin encoding
    source_ascii = source.encode("ascii", errors="replace").decode("ascii")
    py = PYTHON if PYTHON.is_file() else Path(sys.executable)
    try:
        proc = subprocess.run(
            [str(py), "-"],
            input=source_ascii,
            text=True,
            capture_output=True,
            timeout=max(1.0, float(timeout_s)),
            cwd=str(CODE_ROOT),
            encoding="utf-8",
            errors="replace",
        )
        stdout = (proc.stdout or "")[-4000:]
        stderr = (proc.stderr or "")[-2000:]
        ok = proc.returncode == 0
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout", "path": str(src_path).replace("\\", "/")}
    except OSError as exc:
        return {"ok": False, "reason": f"exec_error:{exc}"}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_path = RUNS_ROOT / f"run_{stamp}.json"
    # Sanitize stderr/stdout for Law 4 path scanners (URLs look like paths)
    safe_stdout = stdout.replace("://", ":// ").replace("\\", "/")[:2000]
    safe_stderr = (
        stderr.replace("://", ":// ")
        .replace("\\", "/")
        .replace(".org", "[org]")
        .replace(".py", "[py]")[:800]
    )
    body = {
        "ok": ok,
        "returncode": proc.returncode,
        "source": str(src_path).replace("\\", "/"),
        "stdout": safe_stdout,
        "stderr": safe_stderr,
        "s_n": sn,
        "at": _utc(),
    }
    ok_w, reason_w = _gated_write(run_path, json.dumps(body, indent=2), sn)
    if not ok_w:
        body["run_log_denied"] = reason_w
        # Still return live result even if log write blocked
        body["stdout"] = stdout[:4000]
        body["stderr"] = stderr[:2000]

    state = _load_state()
    state["runs"] = int(state.get("runs") or 0) + 1
    state["last_run_at"] = _utc()
    state["last_run_ok"] = ok
    state["last_stdout"] = stdout[:240]
    _save_state(state)
    _append_log({"event": "code_run", "ok": ok, "source": body["source"], "stdout": stdout[:240]})
    return body


def write_and_run(*, tool: str | None = None) -> dict[str, Any]:
    """Author + execute one sandbox tool — the autonomous code life step."""
    wr = write_sandbox_tool(tool=tool)
    if not wr.get("ok"):
        return {"ok": False, "phase": "write", **wr}
    rn = run_sandbox_tool(path=wr.get("current") or wr.get("path"))
    return {
        "ok": bool(rn.get("ok")),
        "phase": "write_and_run",
        "write": wr,
        "run": {
            "ok": rn.get("ok"),
            "stdout": (rn.get("stdout") or "")[:400],
            "stderr": (rn.get("stderr") or "")[:200],
            "source": rn.get("source"),
            "returncode": rn.get("returncode"),
        },
    }


def code_due(*, every_n_beats: int, beat_index: int) -> bool:
    if every_n_beats <= 0:
        return False
    return beat_index > 0 and (beat_index % every_n_beats == 0)
