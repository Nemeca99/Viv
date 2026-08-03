"""AIOS builder — Viv invents sandbox modules that expand the organism.

Law 4: source as .txt under sandbox/code/, execute via python stdin.
Foundation lib stays immutable. She builds AIOS capability in Law 7 sandbox.
Architect promotes later — she does not rewrite foundation/.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.aios_coder import run_sandbox_tool, write_sandbox_tool
from lib.aios_sandbox import CODE, JOURNAL, WORK, ensure_sandbox_home
from lib.security_membrane import tool_gate

BUILD = WORK / "aios_build"
MANIFEST = BUILD / "MANIFEST.md"
BUILT_LOG = BUILD / "BUILT.jsonl"
SCORECARD = BUILD / "scorecard.json"

# Real AIOS construction modules — not plant_brief theater.
# Each expands Level-3 autonomy evidence or operator visibility.
_MODULES: dict[str, dict[str, str]] = {
    "goal_board_status": {
        "why": "Expose standing goals + step progress for Architect review",
        "source": '''# Viv AIOS build - goal_board_status
import json
from pathlib import Path
p = Path(r"L:/Continue/Viv/sandbox/work/goals.json")
if not p.is_file():
    print("GOAL_BOARD missing")
else:
    data = json.loads(p.read_text(encoding="utf-8"))
    goals = data.get("goals") or []
    print(f"GOAL_BOARD n={len(goals)} updated={data.get('updated_at')}")
    for g in goals:
        plan = g.get("plan") or []
        done = sum(1 for s in plan if s.get("status") == "done")
        print(f"  [{g.get('status')}] {g.get('goal_id')} p={g.get('priority')} "
              f"steps={done}/{len(plan)} :: {(g.get('objective') or '')[:80]}")
''',
    },
    "attempt_replay": {
        "why": "Replay autonomy_attempts.jsonl — prove multi-step agency",
        "source": '''# Viv AIOS build - attempt_replay
import json
from pathlib import Path
p = Path(r"L:/Continue/Viv/sandbox/journal/autonomy_attempts.jsonl")
if not p.is_file():
    print("ATTEMPT_REPLAY missing_log")
else:
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"ATTEMPT_REPLAY n={len(rows)}")
    for r in rows[-12:]:
        print(f"  {r.get('at')} {r.get('event')} step={r.get('step')} ok={r.get('ok')} "
              f"goal={r.get('goal_id')}")
''',
    },
    "plant_trend": {
        "why": "Scorecard: trend last-N Master S_n / dormancy / load from plant RID artifacts",
        "source": '''# Viv AIOS build - plant_trend
# REBUILD SCORECARD — wraps foundation lib/plant_trend_scorecard
import json
import sys
from pathlib import Path
_FOUNDATION = Path(r"L:/Continue/Viv/foundation")
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))
from lib.plant_trend_scorecard import run_smoke
result = run_smoke()
ev = result.get("evidence") or {}
sn = ((ev.get("trend") or {}).get("s_n") or {})
print(
    f"PLANT_TREND verdict={result.get('verdict')} ok={bool(result.get('ok'))} "
    f"n_s_n={ev.get('n_s_n')} source={ev.get('primary_source')} "
    f"last={sn.get('last')} delta={sn.get('delta')} "
    f"evidence={ev.get('evidence_path')}"
)
print(json.dumps({"ok": result.get("ok"), "verdict": result.get("verdict"),
                  "n_s_n": ev.get("n_s_n")}, default=str))
''',
    },
    "build_scorecard": {
        "why": "Score which AIOS pillars have sandbox evidence vs gaps",
        "source": '''# Viv AIOS build - build_scorecard
import json
from pathlib import Path
sb = Path(r"L:/Continue/Viv/sandbox")
code = sb / "code"
build = sb / "work" / "aios_build"
pillars = {
    "goals_board": (sb / "work" / "goals.json").is_file(),
    "attempt_log": (sb / "journal" / "autonomy_attempts.jsonl").is_file(),
    "dream": any((sb / "dream").glob("dream_*.txt")) if (sb / "dream").is_dir() else False,
    "sandbox_tools": len(list(code.glob("*_current.txt"))) if code.is_dir() else 0,
    "build_manifest": (build / "MANIFEST.md").is_file(),
    "plant_brief": (sb / "work" / "plant_brief.txt").is_file(),
}
print("BUILD_SCORECARD", json.dumps(pillars))
gaps = [k for k, v in pillars.items() if v in (False, 0)]
print("GAPS", gaps or ["none"])
''',
    },
    "handoff_packet": {
        "why": "Write Architect handoff when stuck / dormancy / out-of-zone",
        "source": '''# Viv AIOS build - handoff_packet
import json
from datetime import datetime, timezone
from pathlib import Path
out = Path(r"L:/Continue/Viv/sandbox/work/aios_build/HANDOFF_LATEST.json")
out.parent.mkdir(parents=True, exist_ok=True)
goals = Path(r"L:/Continue/Viv/sandbox/work/goals.json")
payload = {
    "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "kind": "handoff_packet",
    "message": "CPU authored handoff packet for Architect",
    "goals_present": goals.is_file(),
}
if goals.is_file():
    data = json.loads(goals.read_text(encoding="utf-8"))
    act = [g for g in (data.get("goals") or []) if g.get("status") == "active"]
    payload["active_goals"] = [
        {"id": g.get("goal_id"), "objective": (g.get("objective") or "")[:120],
         "step": g.get("step_index"), "error": g.get("last_error")}
        for g in act[:5]
    ]
out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(f"HANDOFF_PACKET wrote={out}")
''',
    },
    "organism_state_probe": {
        "why": "Probe organism_state.json — living loop health for AIOS spine",
        "source": '''# Viv AIOS build - organism_state_probe
import json
from pathlib import Path
p = Path(r"L:/Continue/Viv/foundation/artifacts/auto/organism/organism_state.json")
if not p.is_file():
    print("ORGANISM_PROBE missing")
else:
    d = json.loads(p.read_text(encoding="utf-8"))
    print(f"ORGANISM_PROBE mode={d.get('mode')} S_n={d.get('master_s_n')} "
          f"life={d.get('life_beat')} online={d.get('online')}")
    agent = ((d.get("last_beat") or {}).get("agent") or {})
    reason = agent.get("reason") or {}
    print(f"  last_agent decision={reason.get('decision')} step={reason.get('step')}")
''',
    },
    "next_build_ticket": {
        "why": "Emit next AIOS build ticket from gaps — self-directed construction queue",
        "source": '''# Viv AIOS build - next_build_ticket
import json
from datetime import datetime, timezone
from pathlib import Path
code = Path(r"L:/Continue/Viv/sandbox/code")
build = Path(r"L:/Continue/Viv/sandbox/work/aios_build")
build.mkdir(parents=True, exist_ok=True)
have = {p.name.replace("_current.txt", "") for p in code.glob("*_current.txt")} if code.is_dir() else set()
wanted = [
    "goal_board_status", "attempt_replay", "plant_trend", "build_scorecard",
    "handoff_packet", "organism_state_probe", "next_build_ticket", "session_digest",
]
missing = [w for w in wanted if w not in have]
ticket = {
    "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "have": sorted(have),
    "missing": missing,
    "next": missing[0] if missing else "extend_beyond_catalog",
}
path = build / "NEXT_TICKET.json"
path.write_text(json.dumps(ticket, indent=2), encoding="utf-8")
print(f"NEXT_TICKET next={ticket['next']} missing={len(missing)} path={path}")
''',
    },
    "session_digest": {
        "why": "Digest sandbox/sessions for continuity across Architect sessions",
        "source": '''# Viv AIOS build - session_digest
from pathlib import Path
s = Path(r"L:/Continue/Viv/sandbox/sessions")
if not s.is_dir():
    print("SESSION_DIGEST missing_dir")
else:
    entries = sorted(s.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    print(f"SESSION_DIGEST n={len(entries)}")
    for e in entries[:10]:
        print(f"  {e.name} {'dir' if e.is_dir() else 'file'}")
''',
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_build_home() -> Path:
    ensure_sandbox_home()
    BUILD.mkdir(parents=True, exist_ok=True)
    if not MANIFEST.is_file():
        MANIFEST.write_text(
            "# AIOS Build Manifest\n\nViv invents modules here. Foundation stays immutable.\n\n",
            encoding="utf-8",
        )
    return BUILD


def survey_gaps() -> dict[str, Any]:
    """Perceive which AIOS build modules are missing."""
    ensure_build_home()
    have = {
        p.name.replace("_current.txt", "")
        for p in CODE.glob("*_current.txt")
    } if CODE.is_dir() else set()
    missing = [name for name in _MODULES if name not in have]
    # Prefer modules that are not yet built
    next_name = missing[0] if missing else None
    report = {
        "ok": True,
        "have": sorted(have),
        "missing": missing,
        "next": next_name,
        "catalog": list(_MODULES.keys()),
        "at": _utc(),
    }
    SCORECARD.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def invent_next_module(*, s_n: float, force_name: str | None = None) -> dict[str, Any]:
    """Author the next missing AIOS module as sandbox .txt (novel build, not maintenance)."""
    ensure_build_home()
    survey = survey_gaps()
    name = force_name or survey.get("next")
    if not name:
        # Catalog exhausted — invent a stamped extension probe from scorecard
        name = f"aios_ext_{datetime.now(timezone.utc).strftime('%H%M%S')}"
        source = (
            "# Viv AIOS build - extension probe\n"
            "from pathlib import Path\n"
            "import json\n"
            "p = Path(r'L:/Continue/Viv/sandbox/work/aios_build/scorecard.json')\n"
            "print('AIOS_EXT', p.read_text(encoding='utf-8')[:400] if p.is_file() else 'no_scorecard')\n"
        )
        why = "Catalog complete — extension probe from live scorecard"
    else:
        spec = _MODULES.get(name)
        if not spec:
            return {"ok": False, "error": f"unknown_module:{name}"}
        source = spec["source"]
        why = spec["why"]

    wr = write_sandbox_tool(tool=name, source=source, s_n=s_n)
    if not wr.get("ok"):
        return {"ok": False, "error": wr.get("reason"), "write": wr, "module": name}

    row = {
        "event": "invent",
        "at": _utc(),
        "module": name,
        "why": why,
        "path": wr.get("path"),
        "current": wr.get("current"),
        "s_n": s_n,
    }
    with BUILT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")

    return {
        "ok": True,
        "module": name,
        "why": why,
        "path": wr.get("path"),
        "current": wr.get("current"),
        "stdout": f"invented {name} -> {wr.get('path')}",
    }


def run_module(*, module: str, s_n: float) -> dict[str, Any]:
    ensure_build_home()
    rn = run_sandbox_tool(tool=module, s_n=s_n)
    ok = bool(rn.get("ok"))
    row = {
        "event": "run",
        "at": _utc(),
        "module": module,
        "ok": ok,
        "stdout": (rn.get("stdout") or "")[:400],
        "s_n": s_n,
    }
    with BUILT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return {
        "ok": ok,
        "module": module,
        "stdout": (rn.get("stdout") or "")[:400],
        "error": None if ok else (rn.get("reason") or rn.get("stderr") or "run_fail"),
        "run": rn,
    }


def write_manifest(*, module: str, path: str, why: str, run_stdout: str, s_n: float) -> dict[str, Any]:
    ensure_build_home()
    line = (
        f"- [{_utc()}] **{module}** — {why}\n"
        f"  - source: `{path}`\n"
        f"  - run: `{(run_stdout or '').strip()[:200]}`\n"
        f"  - s_n={s_n:.4f}\n"
    )
    gate = str(MANIFEST).replace("\\", "/")
    existing = MANIFEST.read_text(encoding="utf-8") if MANIFEST.is_file() else "# AIOS Build Manifest\n\n"
    content = existing.rstrip() + "\n" + line + "\n"
    verdict = tool_gate("write_file", {"path": gate, "content": content}, s_n)
    if not verdict.get("allowed"):
        return {"ok": False, "error": str(verdict.get("reason", "denied"))}
    MANIFEST.write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "stdout": f"manifest_updated {MANIFEST}",
        "path": str(MANIFEST).replace("\\", "/"),
    }


def verify_last_build() -> dict[str, Any]:
    ensure_build_home()
    if not BUILT_LOG.is_file():
        return {"ok": False, "error": "no_built_log"}
    rows = [json.loads(l) for l in BUILT_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    invents = [r for r in rows if r.get("event") == "invent"]
    runs = [r for r in rows if r.get("event") == "run" and r.get("ok")]
    if not invents:
        return {"ok": False, "error": "no_invent_events"}
    last = invents[-1]
    path = Path(str(last.get("path") or ""))
    if not path.is_file():
        return {"ok": False, "error": f"missing_source:{path}"}
    if not MANIFEST.is_file():
        return {"ok": False, "error": "missing_manifest"}
    return {
        "ok": True,
        "stdout": f"verified module={last.get('module')} path={path} runs_ok={len(runs)} invents={len(invents)}",
        "module": last.get("module"),
        "path": str(path).replace("\\", "/"),
    }
