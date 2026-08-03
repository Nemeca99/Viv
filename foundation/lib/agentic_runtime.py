"""Viv agentic runtime — local task queue gated by Rust security_core.

All mutating actions call ``security_membrane.tool_gate`` first (fail-closed).
Queue/state live under foundation/artifacts/auto/agentic/ — not FSAA.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.master_rid import load_master_rid
from lib.paths import AUTO_ARTIFACTS, VIV_ROOT
from lib.security_membrane import membrane_status, require_membrane
from lib.triad_kernel import (
    TriadDenied,
    TriadEnvelope,
    dispatch,
    open_context,
)
from lib.aios_sandbox import JOURNAL, OPERATOR, SANDBOX_ROOT, WORK, ensure_sandbox_home

AGENTIC_ROOT = AUTO_ARTIFACTS / "agentic"
QUEUE_PATH = AGENTIC_ROOT / "task_queue.json"
STATE_PATH = AGENTIC_ROOT / "runtime_state.json"
EVENTS_PATH = AGENTIC_ROOT / "runtime_events.jsonl"
ARTIFACTS_AUTO = AUTO_ARTIFACTS


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Task:
    task_id: str
    title: str
    kind: str
    priority: int = 100
    status: str = "ready"  # ready | running | done | failed | blocked
    retries: int = 0
    max_retries: int = 2
    payload: dict[str, Any] = field(default_factory=dict)
    risk_class: str = "low"
    created_at: str = ""
    updated_at: str = ""
    last_error: str | None = None
    result: str | None = None

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> Task:
        return cls(
            task_id=str(row["task_id"]),
            title=str(row.get("title", "")),
            kind=str(row["kind"]),
            priority=int(row.get("priority", 100)),
            status=str(row.get("status", "ready")),
            retries=int(row.get("retries", 0)),
            max_retries=int(row.get("max_retries", 2)),
            payload=dict(row.get("payload") or {}),
            risk_class=str(row.get("risk_class", "low")),
            created_at=str(row.get("created_at") or _utc()),
            updated_at=str(row.get("updated_at") or _utc()),
            last_error=row.get("last_error"),
            result=row.get("result"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_files() -> None:
    ensure_sandbox_home()
    AGENTIC_ROOT.mkdir(parents=True, exist_ok=True)
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    if not QUEUE_PATH.is_file():
        QUEUE_PATH.write_text(json.dumps({"tasks": []}, indent=2), encoding="utf-8")
    if not STATE_PATH.is_file():
        _write_state(
            {
                "mode": "normal",
                "heartbeat_at": _utc(),
                "last_task_id": None,
                "last_task_status": None,
                "requires_operator_resume": False,
                "ticks": 0,
                "owner": "viv",
            }
        )


def _write_state(state: dict[str, Any]) -> None:
    state["updated_at"] = _utc()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def load_state() -> dict[str, Any]:
    ensure_files()
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"mode": "degraded", "requires_operator_resume": True}


def load_queue() -> list[Task]:
    ensure_files()
    try:
        raw = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [Task.from_dict(row) for row in raw.get("tasks", [])]


def save_queue(tasks: list[Task]) -> None:
    ensure_files()
    payload = {"tasks": [t.to_dict() for t in tasks], "updated_at": _utc()}
    tmp = QUEUE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(QUEUE_PATH)


def append_event(event: dict[str, Any]) -> None:
    ensure_files()
    event = dict(event)
    event.setdefault("timestamp", _utc())
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, default=str) + "\n")


def _current_s_n() -> float:
    try:
        return float(load_master_rid().master_s_n)
    except Exception:
        return 0.0


def enqueue(
    *,
    kind: str,
    title: str,
    payload: dict[str, Any] | None = None,
    priority: int = 100,
    risk_class: str = "low",
    max_retries: int = 2,
) -> Task:
    ensure_files()
    task = Task(
        task_id=f"t-{uuid.uuid4().hex[:10]}",
        title=title,
        kind=kind,
        priority=priority,
        payload=payload or {},
        risk_class=risk_class,
        max_retries=max_retries,
        created_at=_utc(),
        updated_at=_utc(),
    )
    tasks = load_queue()
    tasks.append(task)
    save_queue(tasks)
    append_event({"event": "enqueued", "task_id": task.task_id, "kind": kind, "title": title})
    return task


def resume() -> dict[str, Any]:
    state = load_state()
    state["requires_operator_resume"] = False
    state["mode"] = "normal"
    state["heartbeat_at"] = _utc()
    _write_state(state)
    append_event({"event": "resumed"})
    return {"ok": True, "state": state}


def needs_resume() -> bool:
    return bool(load_state().get("requires_operator_resume"))


def _autonomy_cfg() -> dict[str, Any]:
    try:
        from lib.paths import FOUNDATION_ROOT

        raw = json.loads((FOUNDATION_ROOT / "cpu_config.json").read_text(encoding="utf-8"))
        return dict(raw.get("autonomy") or {})
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def ensure_cpu_work_queue() -> dict[str, Any]:
    """Top up cpu_rid_observe only when the queue has no higher-value operator work."""
    cfg = _autonomy_cfg()
    if not cfg.get("cpu_rid_autofill", True):
        return {"filled": 0, "reason": "autofill_off"}
    tasks = load_queue()
    ready = [t for t in tasks if t.status == "ready"]
    # Never crowd out operator / pillar work with RID spam
    operator_kinds = {
        "operator_goal",
        "speak_brief",
        "uml_eval",
        "uml_workbook",
        "plant_brief",
        "memory_append",
        "append_journal",
        "write_note",
        "health_check",
        "rid_sample",
        "guardian_pulse",
        "voice_status",
        "memory_retrieve",
        "dream_cycle",
        "sandbox_code",
    }
    if any(t.kind in operator_kinds for t in ready):
        return {"filled": 0, "reason": "operator_work_pending", "ready": len(ready)}
    target = max(0, int(cfg.get("cpu_rid_ready_target") or 1))
    settle = float(cfg.get("cpu_rid_settle_s") or 1.5)
    ready_cpu = sum(1 for t in ready if t.kind == "cpu_rid_observe")
    need = max(0, target - ready_cpu)
    added: list[str] = []
    for i in range(need):
        t = enqueue(
            kind="cpu_rid_observe",
            title=f"CPU RID hold observe (auto #{i + 1})",
            priority=80 + i,
            payload={"settle_s": settle},
            max_retries=0,
        )
        added.append(t.task_id)
    if added:
        append_event({"event": "cpu_rid_autofill", "added": added, "target": target})
    return {"filled": len(added), "ready_before": ready_cpu, "target": target, "added": added}


def _gated_write(path: str, content: str, s_n: float) -> tuple[bool, str, dict[str, Any]]:
    target = Path(path)
    params = {"path": path, "content": content}
    try:
        context = open_context(
            TriadEnvelope.build(
                actor="agentic_runtime",
                source="aios_agent",
                target="filesystem",
                action="AGENTIC_WRITE",
                payload=params,
                s_n=s_n,
            )
        )

        def _write() -> str:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return str(target)

        _, receipt = dispatch(
            context,
            operation="agentic.write",
            params=params,
            handler=_write,
            tool_name="write_file",
        )
        return True, "write_ok", receipt.to_dict()
    except TriadDenied as exc:
        verdict = {
            "allowed": False,
            "reason": exc.reason,
            "evidence": exc.evidence,
        }
        return False, exc.reason, verdict


def _execute(task: Task, s_n: float) -> tuple[bool, str]:
    kind = task.kind
    payload = task.payload or {}

    if kind == "noop":
        return True, "noop_ok"

    if kind == "health_check":
        halt = require_membrane()
        if halt:
            return False, halt["reason"]
        st = membrane_status()
        if not st.get("armed"):
            return False, "security_membrane_disarmed"
        note_path = str(ARTIFACTS_AUTO / "agentic" / "last_health.json").replace("\\", "/")
        # Keep payload free of incidental path strings so nested path-smuggle scanners
        # do not treat embedded status paths as mutation targets.
        body = json.dumps(
            {
                "ok": True,
                "armed": st.get("armed"),
                "version": st.get("version"),
                "integrity_ok": (st.get("integrity") or {}).get("ok"),
                "s_n": s_n,
                "at": _utc(),
            },
            indent=2,
        )
        ok, reason, _v = _gated_write(note_path, body, s_n)
        return ok, reason if ok else reason

    if kind == "write_note":
        path = str(payload.get("path") or "").strip()
        content = str(payload.get("content") or "")
        if not path:
            return False, "missing_path"
        ok, reason, _v = _gated_write(path, content, s_n)
        return ok, reason

    if kind == "append_journal":
        # Write a unique note under sandbox (append via rewrite after gate on same path)
        path = str(
            payload.get("path")
            or (JOURNAL / "agent_journal.txt")
        ).replace("\\", "/")
        line = str(payload.get("line") or f"[{_utc()}] agent tick")
        existing = ""
        p = Path(path)
        if p.is_file():
            existing = p.read_text(encoding="utf-8")
        content = existing + line.rstrip() + "\n"
        ok, reason, _v = _gated_write(path, content, s_n)
        return ok, reason

    if kind == "memory_append":
        text = str(payload.get("text") or "").strip()
        if not text:
            return False, "missing_text"
        try:
            from lib.carma_memory import remember

            prov = str(payload.get("provenance") or "live")
            tags = payload.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            out = remember(text, provenance=prov, tags=tags, s_n=s_n)
            return bool(out.get("ok")), str(out.get("reason") or out.get("id") or "memory_ok")
        except Exception as exc:  # noqa: BLE001
            return False, f"memory_append_error:{exc}"

    if kind == "memory_retrieve":
        query = str(payload.get("query") or "").strip()
        if not query:
            return False, "missing_query"
        try:
            from lib.carma_memory import retrieve

            top = int(payload.get("top") or 5)
            hits = retrieve(query, top=top)
            return True, json.dumps({"hits": hits, "count": len(hits)})
        except Exception as exc:  # noqa: BLE001
            return False, f"memory_retrieve_error:{exc}"

    if kind == "cpu_core_probe":
        core_id = str(payload.get("core_id") or "").strip()
        operation = str(payload.get("operation") or "status").strip().casefold()
        if not core_id:
            return False, "missing_core_id"
        try:
            from lib.cpu_core_dispatch import probe

            result = probe(core_id, operation=operation)
            if result.get("state") == "DENIED":
                return False, str(result.get("reason") or "cpu_core_probe_denied")
            return result.get("state") == "PASS", json.dumps(result, sort_keys=True, default=str)
        except Exception as exc:  # noqa: BLE001
            return False, f"cpu_core_probe_error:{exc}"

    if kind == "cpu_core_survey":
        try:
            from lib.cpu_core_dispatch import available_cores, probe_many

            result = probe_many(available_cores(), operation="status")
            return result.get("ok") is True, json.dumps(result, sort_keys=True, default=str)
        except Exception as exc:  # noqa: BLE001
            return False, f"cpu_core_survey_error:{exc}"

    if kind == "cpu_reasoning_probe":
        value = payload.get("value")
        if value is None:
            return False, "missing_reasoning_input"
        try:
            from lib.cpu_reasoning_pipeline import compact, reason

            result = reason(
                value,
                s_n=s_n,
                manual_only=bool(payload.get("manual_only", False)),
                top_k=int(payload.get("top_k") or 5),
            )
            if result.get("state") == "DENIED":
                return False, compact(result)
            return True, compact(result)
        except Exception as exc:  # noqa: BLE001
            return False, f"cpu_reasoning_probe_error:{exc}"

    if kind == "cpu_rid_observe":
        # CPU-first teach tick — plant grades hold prediction; no GPU.
        try:
            from lib.cpu_rid_tick import rid_cpu_tick

            settle = float(payload.get("settle_s") or 1.5)
            out = rid_cpu_tick(settle_s=settle)
            # Observation success = cycle ran; PUNISH/NEUTRAL are grades, not executor faults.
            ok = bool(out.get("ok")) and not bool(out.get("excluded"))
            return ok, json.dumps(out, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            return False, f"cpu_rid_observe_error:{exc}"

    if kind == "uml_eval":
        expr = str(payload.get("expr") or "[3,4]").strip()
        try:
            from lib.uml_engine import evaluate, fmt, to_std, to_uml, verify

            result, node, nota, _ = evaluate(expr)
            alt = to_std(node) if nota == "uml" else to_uml(node)
            ok_v, report_v = verify(expr)
            body = {
                "expr": expr,
                "result": fmt(result),
                "notation": nota,
                "alt": alt,
                "verify_ok": bool(ok_v),
                "verify_report": report_v,
                "at": _utc(),
            }
            note_path = str(ARTIFACTS_AUTO / "agentic" / "last_uml.json").replace("\\", "/")
            ok, reason, _v = _gated_write(note_path, json.dumps(body, indent=2), s_n)
            if not ok:
                return False, reason
            return bool(ok_v), json.dumps(body, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            return False, f"uml_eval_error:{exc}"

    if kind == "rid_sample":
        try:
            from lib.master_rid import compute_master_rid, publish_master_rid
            from lib.rid_feed import pulse_once

            sample = pulse_once()
            master = compute_master_rid(sample)
            publish_master_rid(master)
            body = {
                "master_s_n": master.master_s_n,
                "status": master.status,
                "rsr": master.master_rsr,
                "ltp": master.master_ltp,
                "rle": master.master_rle,
                "at": _utc(),
            }
            note_path = str(ARTIFACTS_AUTO / "agentic" / "last_rid_sample.json").replace("\\", "/")
            ok, reason, _v = _gated_write(note_path, json.dumps(body, indent=2), s_n)
            return ok, reason if ok else reason
        except Exception as exc:  # noqa: BLE001
            return False, f"rid_sample_error:{exc}"

    if kind == "guardian_pulse":
        text = str(payload.get("text") or "Master S_n plant status ACTIVE").strip()
        try:
            from lib.guardian_v2 import evaluate_guardian

            g = evaluate_guardian(text, s_n=s_n)
            body = g.to_dict() if hasattr(g, "to_dict") else dict(g)
            note_path = str(ARTIFACTS_AUTO / "agentic" / "last_guardian.json").replace("\\", "/")
            ok, reason, _v = _gated_write(note_path, json.dumps(body, indent=2, default=str), s_n)
            if not ok:
                return False, reason
            # Curriculum pulse: recording the verdict is success; block is informational.
            return True, json.dumps(
                {"allowed": bool(body.get("allowed")), "stage": body.get("stage"), "at": _utc()},
                ensure_ascii=False,
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"guardian_pulse_error:{exc}"

    if kind == "voice_status":
        try:
            from voice_core.speak import speak_status

            st = speak_status()
            body = {
                "backend": st.get("backend"),
                "served_name": st.get("served_name"),
                "reachable": st.get("reachable"),
                "gguf_ready": (st.get("gguf") or {}).get("gguf_ready"),
                "at": _utc(),
            }
            note_path = str(ARTIFACTS_AUTO / "agentic" / "last_voice_status.json").replace("\\", "/")
            ok, reason, _v = _gated_write(note_path, json.dumps(body, indent=2), s_n)
            return ok and bool(st.get("reachable") or (st.get("gguf") or {}).get("gguf_ready")), (
                reason if ok else reason
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"voice_status_error:{exc}"

    if kind == "speak_brief":
        query = str(payload.get("query") or "state summary").strip()
        try:
            from voice_core.speak import speak as viv_speak

            sp = viv_speak(query, memory_top=2, max_tokens=72)
            body = {
                "ok": sp.get("ok"),
                "source": sp.get("voice_source"),
                "text": sp.get("text"),
                "query": query,
                "at": _utc(),
            }
            note_path = str(ARTIFACTS_AUTO / "agentic" / "last_speak.json").replace("\\", "/")
            ok, reason, _v = _gated_write(note_path, json.dumps(body, indent=2, default=str), s_n)
            if not ok:
                return False, reason
            return bool(sp.get("text")), json.dumps(
                {"source": body.get("source"), "chars": len(str(body.get("text") or ""))},
                ensure_ascii=False,
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"speak_brief_error:{exc}"

    if kind == "plant_brief":
        try:
            from lib.master_rid import load_master_rid

            m = load_master_rid()
            text = (
                f"[{_utc()}] Plant brief — Master S_n={m.master_s_n:.4f} status={m.status} "
                f"RSR={m.master_rsr:.4f} LTP={m.master_ltp:.4f} RLE={m.master_rle:.4f}\n"
            )
            path = str((WORK / "plant_brief.txt")).replace("\\", "/")
            # append via rewrite
            existing = ""
            p = Path(path)
            if p.is_file():
                existing = p.read_text(encoding="utf-8")
            ok, reason, _v = _gated_write(path, existing + text, s_n)
            return ok, reason if ok else reason
        except Exception as exc:  # noqa: BLE001
            return False, f"plant_brief_error:{exc}"

    if kind == "operator_goal":
        goal = str(payload.get("goal") or "").strip()
        if not goal:
            return False, "missing_goal"
        try:
            plan = (
                f"[{_utc()}] OPERATOR GOAL\n"
                f"goal: {goal}\n"
                f"s_n: {s_n:.4f}\n"
                f"plan:\n"
                f"  1) measure plant (RID)\n"
                f"  2) remember goal in CARMA\n"
                f"  3) write sandbox note\n"
                f"  4) report on task board / outbox\n"
            )
            path = str((OPERATOR / "goals.txt")).replace("\\", "/")
            existing = ""
            p = Path(path)
            if p.is_file():
                existing = p.read_text(encoding="utf-8")
            ok, reason, _v = _gated_write(path, existing + plan + "\n", s_n)
            if not ok:
                return False, reason
            try:
                from lib.carma_memory import remember

                remember(f"[goal] {goal}", provenance="operator", tags=["goal", "operator"], s_n=s_n)
            except Exception:  # noqa: BLE001
                pass
            return True, "goal_recorded"
        except Exception as exc:  # noqa: BLE001
            return False, f"operator_goal_error:{exc}"

    if kind == "uml_workbook":
        n = max(1, min(5, int(payload.get("n") or 3)))
        exprs = ["[3,4]", "{10,3}", ">3,4<", "[1,>2,3<]", "%[10,3]"][:n]
        try:
            from lib.uml_engine import evaluate, fmt, verify

            rows = []
            for expr in exprs:
                result, _node, nota, _ = evaluate(expr)
                ok_v, _rep = verify(expr)
                rows.append({"expr": expr, "result": fmt(result), "notation": nota, "ok": bool(ok_v)})
            body = {"at": _utc(), "rows": rows}
            path = str((WORK / "uml_workbook.txt")).replace("\\", "/")
            lines = [f"[{body['at']}] UML workbook"] + [
                f"  {r['expr']} => {r['result']} ({'ok' if r['ok'] else 'fail'})" for r in rows
            ]
            existing = ""
            p = Path(path)
            if p.is_file():
                existing = p.read_text(encoding="utf-8")
            ok, reason, _v = _gated_write(path, existing + "\n".join(lines) + "\n\n", s_n)
            if not ok:
                return False, reason
            note_path = str(ARTIFACTS_AUTO / "agentic" / "last_uml_workbook.json").replace("\\", "/")
            _gated_write(note_path, json.dumps(body, indent=2), s_n)
            return all(r["ok"] for r in rows), json.dumps({"n": len(rows), "ok": True})
        except Exception as exc:  # noqa: BLE001
            return False, f"uml_workbook_error:{exc}"

    if kind == "dream_cycle":
        try:
            from lib.aios_dream import perform_dream_cycle

            out = perform_dream_cycle(force=bool(payload.get("force")))
            note_path = str(ARTIFACTS_AUTO / "agentic" / "last_dream.json").replace("\\", "/")
            _gated_write(note_path, json.dumps(out, indent=2, default=str), s_n)
            if out.get("skipped"):
                return True, json.dumps({"skipped": out.get("skipped"), "s_n": out.get("s_n")})
            return bool(out.get("ok")), json.dumps(
                {
                    "cycle": out.get("cycle"),
                    "dream_path": out.get("dream_path"),
                    "live_chars": out.get("live_chars"),
                },
                ensure_ascii=False,
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"dream_cycle_error:{exc}"

    if kind == "sandbox_code":
        try:
            from lib.aios_coder import write_and_run

            tool = payload.get("tool")
            out = write_and_run(tool=str(tool) if tool else None)
            note_path = str(ARTIFACTS_AUTO / "agentic" / "last_sandbox_code.json").replace("\\", "/")
            _gated_write(note_path, json.dumps(out, indent=2, default=str), s_n)
            run = out.get("run") or {}
            return bool(out.get("ok")), json.dumps(
                {
                    "tool": (out.get("write") or {}).get("tool"),
                    "stdout": (run.get("stdout") or "")[:200],
                    "path": (out.get("write") or {}).get("path"),
                },
                ensure_ascii=False,
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"sandbox_code_error:{exc}"

    return False, f"unknown_kind:{kind}"


def run_once(max_tasks: int = 1) -> dict[str, Any]:
    """Process up to max_tasks ready items. Returns structured tick report."""
    ensure_files()
    state = load_state()
    report: dict[str, Any] = {
        "ok": True,
        "owner": "viv",
        "processed": [],
        "skipped": None,
    }

    halt = require_membrane()
    if halt:
        report["ok"] = False
        report["skipped"] = {"reason": "security_membrane", "detail": halt}
        state["mode"] = "halted"
        state["requires_operator_resume"] = True
        _write_state(state)
        append_event({"event": "tick_halted", "reason": halt})
        return report

    if state.get("requires_operator_resume"):
        report["ok"] = False
        report["skipped"] = {"reason": "requires_operator_resume"}
        append_event({"event": "tick_paused"})
        return report

    s_n = _current_s_n()
    try:
        from lib.paths import FOUNDATION_ROOT

        raw = json.loads((FOUNDATION_ROOT / "cpu_config.json").read_text(encoding="utf-8"))
        dormancy = float(raw.get("dormancy_threshold") or 0.37)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        dormancy = 0.37
    if s_n < dormancy:
        report["ok"] = False
        report["skipped"] = {"reason": "dormant", "s_n": s_n, "floor": dormancy}
        append_event({"event": "tick_dormant", "s_n": s_n, "floor": dormancy})
        state["heartbeat_at"] = _utc()
        state["mode"] = "degraded"
        _write_state(state)
        return report

    tasks = load_queue()
    ready = sorted(
        [t for t in tasks if t.status == "ready"],
        key=lambda t: (t.priority, t.created_at),
    )
    budget = max(1, int(max_tasks))
    taken = ready[:budget]

    if not taken:
        # Autofill CPU RID work then retry once so empty queue does not idle forever.
        fill = ensure_cpu_work_queue()
        report["autofill"] = fill
        if fill.get("filled"):
            tasks = load_queue()
            ready = sorted(
                [t for t in tasks if t.status == "ready"],
                key=lambda t: (t.priority, t.created_at),
            )
            taken = ready[:budget]
        if not taken:
            report["skipped"] = {"reason": "empty_queue"}
            state["heartbeat_at"] = _utc()
            state["ticks"] = int(state.get("ticks") or 0) + 1
            state["mode"] = "normal"
            _write_state(state)
            append_event({"event": "tick_idle", "s_n": s_n})
            return report

    for task in taken:
        task.status = "running"
        task.updated_at = _utc()
        save_queue(tasks)
        append_event({"event": "task_start", "task_id": task.task_id, "kind": task.kind, "s_n": s_n})

        ok, reason = _execute(task, s_n)
        task.updated_at = _utc()
        task.result = reason
        if ok:
            task.status = "done"
            task.last_error = None
        else:
            task.retries += 1
            task.last_error = reason
            denial_reason = str(reason).casefold()
            if (
                "law" in denial_reason
                or "security" in denial_reason
                or "tool_gate" in denial_reason
                or "sandbox" in denial_reason
            ):
                task.status = "blocked"
            elif task.retries > task.max_retries:
                task.status = "failed"
            else:
                task.status = "ready"
        save_queue(tasks)
        append_event(
            {
                "event": "task_finish",
                "task_id": task.task_id,
                "kind": task.kind,
                "ok": ok,
                "status": task.status,
                "reason": reason,
                "s_n": s_n,
            }
        )
        report["processed"].append(
            {
                "task_id": task.task_id,
                "kind": task.kind,
                "ok": ok,
                "status": task.status,
                "reason": reason,
            }
        )
        state["last_task_id"] = task.task_id
        state["last_task_status"] = task.status

    state["heartbeat_at"] = _utc()
    state["ticks"] = int(state.get("ticks") or 0) + 1
    state["mode"] = "normal"
    _write_state(state)
    report["s_n"] = s_n
    report["exit_code"] = 0 if report["ok"] else 1
    return report


def status() -> dict[str, Any]:
    ensure_files()
    tasks = load_queue()
    by = {}
    for t in tasks:
        by[t.status] = by.get(t.status, 0) + 1
    return {
        "owner": "viv",
        "queue_path": str(QUEUE_PATH),
        "state": load_state(),
        "counts": by,
        "tasks": len(tasks),
        "security": membrane_status(),
        "events_path": str(EVENTS_PATH),
    }
