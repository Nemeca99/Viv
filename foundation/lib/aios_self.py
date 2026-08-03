"""Viv self-life: understand -> build only if needed -> log -> talk only if novel.

Honest mode: idle + silence when nothing changed. No status-parrot LLM loop.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.aios_sandbox import JOURNAL, SANDBOX_ROOT, ensure_sandbox_home
from lib.master_rid import load_master_rid
from lib.paths import AUTO_ARTIFACTS, FOUNDATION_ROOT
from lib.security_membrane import tool_gate

LIFE_LOG = AUTO_ARTIFACTS / "organism" / "life.jsonl"
LIFE_STATE = AUTO_ARTIFACTS / "organism" / "self_state.json"
FLIGHT = JOURNAL / "flight_recorder.jsonl"
SELF_MD = JOURNAL / "SELF.md"
SELF_MAP = AUTO_ARTIFACTS / "organism" / "self_map.json"


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


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def _count_txt(root: Path) -> tuple[int, int]:
    n, b = 0, 0
    if not root.is_dir():
        return 0, 0
    for f in root.rglob("*.txt"):
        n += 1
        try:
            b += f.stat().st_size
        except OSError:
            pass
    return n, b


def _load_life_state() -> dict[str, Any]:
    if not LIFE_STATE.is_file():
        return {}
    try:
        return json.loads(LIFE_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def understand_self() -> dict[str, Any]:
    ensure_sandbox_home()
    out: dict[str, Any] = {"at": _utc(), "who": "Viv"}

    try:
        m = load_master_rid()
        out["plant"] = {
            "master_s_n": m.master_s_n,
            "status": m.status,
            "rsr": m.master_rsr,
            "ltp": m.master_ltp,
            "rle": m.master_rle,
        }
        sn = float(m.master_s_n)
    except Exception as exc:  # noqa: BLE001
        out["plant"] = {"error": str(exc)}
        sn = 0.5

    code_dir = SANDBOX_ROOT / "code"
    tools = (
        sorted(p.stem.replace("_current", "") for p in code_dir.glob("*_current.txt"))
        if code_dir.is_dir()
        else []
    )
    out["tools_authored"] = tools
    dream_n, dream_b = _count_txt(SANDBOX_ROOT / "dream")
    out["dream"] = {"files": dream_n, "bytes": dream_b}
    out["dream_files"] = dream_n

    try:
        from lib.security_membrane import membrane_status

        st = membrane_status()
        out["security"] = {"armed": st.get("armed"), "version": st.get("version")}
    except Exception as exc:  # noqa: BLE001
        out["security"] = {"error": str(exc)}

    try:
        from voice_core.speak import speak_status

        vs = speak_status()
        out["voice"] = {
            "backend": vs.get("backend"),
            "served_name": vs.get("served_name"),
            "reachable": vs.get("reachable"),
        }
    except Exception as exc:  # noqa: BLE001
        out["voice"] = {"error": str(exc)}

    gaps: list[str] = []
    if "self_map" not in tools:
        gaps.append("self_map")
    if "flight_digest" not in tools:
        gaps.append("flight_digest")
    if "capability_audit" not in tools:
        gaps.append("capability_audit")
    if dream_n == 0:
        gaps.append("needs_dream")
    out["gaps"] = gaps
    out["s_n"] = sn
    out["understanding"] = (
        f"Viv S_n={sn:.4f} {(out.get('plant') or {}).get('status')} "
        f"tools={len(tools)} dreams={dream_n} gaps={','.join(gaps) or 'none'}"
    )
    return out


def _deltas(understanding: dict[str, Any], prev: dict[str, Any]) -> list[str]:
    last = (prev.get("last") or {}) if prev else {}
    plant = understanding.get("plant") or {}
    old_plant = last.get("plant") or {}
    deltas: list[str] = []
    try:
        sn = float(plant.get("master_s_n") or 0)
        old_sn = float(old_plant.get("master_s_n") or sn)
        if abs(sn - old_sn) >= 0.05:
            deltas.append(f"S_n {old_sn:.3f}->{sn:.3f}")
    except (TypeError, ValueError):
        pass
    if str(plant.get("status")) != str(old_plant.get("status") or plant.get("status")):
        deltas.append(f"status {old_plant.get('status')}->{plant.get('status')}")
    old_tools = set(last.get("tools") or [])
    new_tools = set(understanding.get("tools_authored") or [])
    added = sorted(new_tools - old_tools)
    if added:
        deltas.append("new tools " + ",".join(added))
    dream_n = int(understanding.get("dream_files") or 0)
    old_dream = int(last.get("dream_files") or 0)
    if dream_n > old_dream:
        deltas.append(f"dreams {old_dream}->{dream_n}")
    if understanding.get("gaps"):
        deltas.append("gaps " + ",".join(understanding["gaps"]))
    return deltas


def _source_for_gap(gap: str) -> tuple[str, str]:
    if gap == "self_map":
        return "self_map", (
            "import json\nfrom pathlib import Path\n"
            "sb=Path(r'L:/Continue/Viv/sandbox')\n"
            "rid=Path(r'L:/Continue/Viv/foundation/artifacts/auto/master_rid.json')\n"
            "plant=json.loads(rid.read_text(encoding='utf-8')) if rid.is_file() else {}\n"
            "tools=sorted(p.name for p in (sb/'code').glob('*_current.txt')) if (sb/'code').is_dir() else []\n"
            "dreams=len(list((sb/'dream').glob('*.txt'))) if (sb/'dream').is_dir() else 0\n"
            "print('SELF_MAP', json.dumps({'who':'Viv','tools':tools,'dreams':dreams,"
            "'s_n':plant.get('master_s_n'),'status':plant.get('status')}))\n"
        )
    if gap == "flight_digest":
        return "flight_digest", (
            "from pathlib import Path\n"
            "p=Path(r'L:/Continue/Viv/sandbox/journal/flight_recorder.jsonl')\n"
            "lines=p.read_text(encoding='utf-8',errors='replace').splitlines() if p.is_file() else []\n"
            "print(f'FLIGHT_DIGEST events={len(lines)}')\n"
        )
    if gap == "capability_audit":
        return "capability_audit", (
            "from pathlib import Path\n"
            "checks={'sandbox':Path(r'L:/Continue/Viv/sandbox/HOME.txt').is_file(),"
            "'rid':Path(r'L:/Continue/Viv/foundation/artifacts/auto/master_rid.json').is_file(),"
            "'carma':Path(r'L:/Continue/Viv/foundation/artifacts/carma').is_dir(),"
            "'organism':Path(r'L:/Continue/Viv/foundation/aios_main.py').is_file()}\n"
            "print('CAPABILITY_AUDIT', checks, 'pass', all(checks.values()))\n"
        )
    if gap == "needs_dream":
        return "capability_audit", _source_for_gap("capability_audit")[1]
    return _source_for_gap("capability_audit")


def build_self(understanding: dict[str, Any]) -> dict[str, Any]:
    from lib.aios_coder import run_sandbox_tool, write_sandbox_tool

    sn = float(understanding.get("s_n") or 0.5)
    gaps = list(understanding.get("gaps") or [])
    prev = _load_life_state()
    deltas = _deltas(understanding, prev)
    understanding["deltas"] = deltas

    if not gaps:
        plant_delta = any(d.startswith("S_n ") or d.startswith("status ") for d in deltas)
        if plant_delta:
            rn = run_sandbox_tool(tool="plant_digest", s_n=sn)
            return {
                "ok": bool(rn.get("ok")),
                "kind": "observe",
                "gap": "plant_delta",
                "tool": "plant_digest",
                "stdout": (rn.get("stdout") or "")[:400],
                "deltas": deltas,
                "novel": True,
                "s_n": sn,
            }
        return {
            "ok": True,
            "kind": "idle",
            "gap": None,
            "reason": "no_gaps_no_significant_delta",
            "deltas": deltas,
            "novel": False,
            "s_n": sn,
        }

    gap = gaps[0]
    if gap == "needs_dream":
        from lib.aios_dream import perform_dream_cycle

        dream = perform_dream_cycle(force=True)
        return {
            "ok": bool(dream.get("ok")),
            "kind": "dream",
            "gap": gap,
            "result": {"cycle": dream.get("cycle"), "path": dream.get("dream_path")},
            "deltas": deltas,
            "novel": True,
            "s_n": sn,
        }

    name, source = _source_for_gap(gap)
    current = SANDBOX_ROOT / "code" / f"{name}_current.txt"
    if current.is_file() and name in (understanding.get("tools_authored") or []):
        rn = run_sandbox_tool(path=str(current), s_n=sn)
        return {
            "ok": bool(rn.get("ok")),
            "kind": "observe",
            "gap": gap,
            "tool": name,
            "stdout": (rn.get("stdout") or "")[:400],
            "deltas": deltas,
            "novel": True,
            "s_n": sn,
        }

    wr = write_sandbox_tool(tool=name, source=source, s_n=sn)
    if not wr.get("ok"):
        return {"ok": False, "kind": "code", "gap": gap, "write": wr, "deltas": deltas, "novel": True, "s_n": sn}
    rn = run_sandbox_tool(path=wr.get("current") or wr.get("path"), s_n=sn)
    return {
        "ok": bool(rn.get("ok")),
        "kind": "code",
        "gap": gap,
        "tool": name,
        "path": wr.get("path"),
        "stdout": (rn.get("stdout") or "")[:400],
        "deltas": deltas,
        "novel": True,
        "s_n": sn,
    }


def log_self(
    understanding: dict[str, Any],
    build: dict[str, Any],
    *,
    spoken: str | None = None,
) -> dict[str, Any]:
    ensure_sandbox_home()
    sn = float(understanding.get("s_n") or 0.5)
    novel = bool(build.get("novel"))
    row = {
        "event": "self_life",
        "at": _utc(),
        "understanding": understanding.get("understanding"),
        "gaps": understanding.get("gaps"),
        "deltas": understanding.get("deltas") or build.get("deltas"),
        "plant": understanding.get("plant"),
        "tools": understanding.get("tools_authored"),
        "dream_files": understanding.get("dream_files"),
        "build": {
            "ok": build.get("ok"),
            "kind": build.get("kind"),
            "gap": build.get("gap"),
            "tool": build.get("tool"),
            "stdout": (build.get("stdout") or "")[:240],
            "result": build.get("result"),
            "novel": novel,
        },
        "spoken": (spoken or "")[:280],
        "s_n": sn,
    }
    _append_jsonl(LIFE_LOG, row)
    _append_jsonl(FLIGHT, row)

    map_body = {
        "updated_at": _utc(),
        "understanding": understanding.get("understanding"),
        "plant_s_n": (understanding.get("plant") or {}).get("master_s_n"),
        "plant_status": (understanding.get("plant") or {}).get("status"),
        "tools": understanding.get("tools_authored"),
        "gaps": understanding.get("gaps"),
        "deltas": row.get("deltas"),
        "last_kind": build.get("kind"),
    }
    ok_m, reason_m = _gated_write(SELF_MAP, json.dumps(map_body, indent=2), sn)
    md = "\n".join(
        [
            f"# Viv SELF — {_utc()}",
            f"**State:** {understanding.get('understanding')}",
            f"**Deltas:** {', '.join(row.get('deltas') or []) or '(none)'}",
            f"**Action:** {build.get('kind')} novel={novel}",
            f"**Out:** {(build.get('stdout') or build.get('reason') or build.get('result') or '')}",
            f"**Said:** {spoken or '(silent)'}",
            "",
        ]
    )
    ok_s, reason_s = _gated_write(SELF_MD, md, sn)

    remembered: dict[str, Any] = {"ok": False, "skipped": "not_novel"}
    if novel:
        try:
            from lib.carma_memory import remember

            remembered = remember(
                f"[self] deltas={row.get('deltas')} kind={build.get('kind')} "
                f"out={(build.get('stdout') or '')[:100]}",
                provenance="live",
                tags=["self", "delta"],
                s_n=sn,
            )
        except Exception as exc:  # noqa: BLE001
            remembered = {"ok": False, "error": str(exc)}

    LIFE_STATE.parent.mkdir(parents=True, exist_ok=True)
    LIFE_STATE.write_text(json.dumps({"updated_at": _utc(), "last": row}, indent=2), encoding="utf-8")
    return {
        "ok": bool(ok_s),
        "flight": str(FLIGHT).replace("\\", "/"),
        "self_md": str(SELF_MD).replace("\\", "/"),
        "map_write": reason_m,
        "md_write": reason_s,
        "remembered": remembered,
    }


def talk_self(understanding: dict[str, Any], build: dict[str, Any]) -> dict[str, Any]:
    """Speak only on novelty. Personality-shaped CPU line — no LLM status parrot."""
    sn = float(understanding.get("s_n") or 0.0)
    if sn < 0.37:
        return {"ok": False, "skipped": "s_n_dormancy", "source": "silence", "text": ""}
    if build.get("kind") == "idle" or not build.get("novel"):
        return {"ok": True, "skipped": "nothing_new", "source": "silence", "text": ""}

    deltas = list(build.get("deltas") or understanding.get("deltas") or [])
    status = str((understanding.get("plant") or {}).get("status") or "?")
    out = (build.get("stdout") or "").strip()[:120]
    try:
        from lib.aios_personality import render_cpu_line

        line = render_cpu_line(deltas=deltas, stdout=out, status=status, s_n=sn)
    except Exception:
        line = f"Change: {'; '.join(deltas) if deltas else build.get('gap')}. "
        if out:
            line += f"{out} "
        line += f"Status {status}; Master S_n is {sn:.4f}."
    if not line.strip():
        return {"ok": True, "skipped": "nothing_new", "source": "silence", "text": ""}
    return {"ok": True, "source": "cpu_honest+dna", "text": line.strip()[:400]}


def self_life_cycle(*, speak: bool = True) -> dict[str, Any]:
    ensure_sandbox_home()
    understanding = understand_self()
    build = build_self(understanding)
    spoken_rep: dict[str, Any] = {"ok": False, "skipped": "speak_off", "text": ""}
    if speak:
        spoken_rep = talk_self(understanding, build)
    log = log_self(understanding, build, spoken=(spoken_rep.get("text") or None))
    return {
        "ok": bool(understanding.get("understanding")) and bool(build.get("ok")),
        "at": _utc(),
        "understand": understanding,
        "build": build,
        "log": log,
        "talk": spoken_rep,
        "sandbox": "L:/Continue/Viv/sandbox/",
    }
