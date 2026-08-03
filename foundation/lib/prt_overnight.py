"""Autonomous overnight PRT training loop — bounded, halt-gated, evidence-first.

Does not flip cpu_config.autonomy.voice_speak. Reads Architect setting.
Operator halt/resume is mandatory on HALT/degraded.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.dormancy_config import load_threshold
from lib.paths import ARTIFACTS, AUTO_ARTIFACTS, FOUNDATION_ROOT
from lib.prt_cycle import HALT_FLAG, halted, observe_state

CONFIG_PATH = ARTIFACTS / "models" / "prt_overnight_config.json"
AUTONOMOUS_AUDIT = ARTIFACTS / "audit" / "prt_autonomous.log"
STATE_PATH = AUTO_ARTIFACTS / "prt_overnight_state.json"
EVENTS_PATH = AUTO_ARTIFACTS / "prt_overnight_events.jsonl"
LOCK_PATH = AUTO_ARTIFACTS / "prt_overnight.lock"
OVERNIGHT_HALT = AUTO_ARTIFACTS / "prt_overnight_halt.flag"
AUDIT_DIR = ARTIFACTS / "audit"
PYTHON = Path(r"L:\Continue\.venv\Scripts\python.exe")
PRT_MAIN = FOUNDATION_ROOT / "prt_main.py"

_DEFAULTS: dict[str, Any] = {
    "max_rounds": 8,
    "max_hours": 8.0,
    "cooldown_s": 600,
    "observe_cycles": 12,
    "speak_cycles": 6,
    "life_cycles": 12,
    "pulse_cycles": 8,
    "settle_s": 4.0,
    "steps": 400,
    "lr": 5e-5,
    "min_master_s_n_margin": 0.02,
    "s_n_wait_timeout_s": 1800,
    "s_n_poll_s": 30,
    "max_consecutive_failures": 2,
    "integrity_halt_flags": ["near_dead"],
    "skip_speak_if_dormant": True,
    "require_active": True,
    "piston_background": False,
    "piston_interval_s": 1.0,
    "begin_telemetry_epoch": False,
    "pre_integrity_settle_s": 25.0,
    "recover_on_near_dead": True,
    "near_dead_recover_timeout_s": 1800,
}

# Integrity flags that are transient plant-heat conditions, not corruption.
_RECOVERABLE_FLAGS = {"near_dead", "live_dormant"}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _operator_voice_speak() -> bool:
    """Respect Architect cpu_config — never invent on/off."""
    try:
        raw = json.loads((FOUNDATION_ROOT / "cpu_config.json").read_text(encoding="utf-8"))
        return bool((raw.get("autonomy") or {}).get("voice_speak", False))
    except (OSError, json.JSONDecodeError, TypeError):
        return False


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg = dict(_DEFAULTS)
    src = path or CONFIG_PATH
    if src.is_file():
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if not str(k).startswith("_")})
        except (OSError, json.JSONDecodeError):
            pass
    cfg["voice_speak"] = _operator_voice_speak()
    return cfg


def _emit(event: str, **payload: Any) -> None:
    row = {"timestamp": _utc(), "actor": "prt_overnight", "event": event, **payload}
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _autonomous_audit(message: str, **payload: Any) -> None:
    """Integrity / loop evidence for `prt_main.py autonomous`."""
    AUTONOMOUS_AUDIT.parent.mkdir(parents=True, exist_ok=True)
    row = {"timestamp": _utc(), "message": message, **payload}
    with AUTONOMOUS_AUDIT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def read_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def overnight_halted() -> bool:
    return OVERNIGHT_HALT.is_file() or halted()


def request_halt(reason: str = "operator") -> Path:
    OVERNIGHT_HALT.parent.mkdir(parents=True, exist_ok=True)
    OVERNIGHT_HALT.write_text(f"{_utc()} {reason}\n", encoding="utf-8")
    _emit("halt_requested", reason=reason)
    return OVERNIGHT_HALT


def clear_overnight_halt() -> bool:
    """Clear overnight-specific halt only (not global halt.flag)."""
    if OVERNIGHT_HALT.is_file():
        OVERNIGHT_HALT.unlink()
        _emit("halt_cleared", kind="overnight")
        return True
    return False


def _lock_pid() -> int | None:
    if not LOCK_PATH.is_file():
        return None
    try:
        data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        return int(data.get("pid") or 0) or None
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:  # noqa: BLE001
            pass
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return str(pid) in (out.stdout or "") and "No tasks" not in (out.stdout or "")
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_lock() -> dict[str, Any]:
    pid = _lock_pid()
    if pid and _pid_alive(pid) and pid != os.getpid():
        raise RuntimeError(f"overnight already running pid={pid}")
    payload = {"pid": os.getpid(), "started_at": _utc(), "host": os.environ.get("COMPUTERNAME")}
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def release_lock() -> None:
    if LOCK_PATH.is_file():
        try:
            data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
            if int(data.get("pid") or 0) == os.getpid():
                LOCK_PATH.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            LOCK_PATH.unlink(missing_ok=True)


def status_snapshot() -> dict[str, Any]:
    cfg = load_config()
    obs = observe_state()
    lock_pid = _lock_pid()
    return {
        "ok": True,
        "timestamp": _utc(),
        "overnight_halted": overnight_halted(),
        "global_halt": halted(),
        "overnight_halt_flag": OVERNIGHT_HALT.is_file(),
        "global_halt_flag": HALT_FLAG.is_file(),
        "lock_pid": lock_pid,
        "lock_alive": bool(lock_pid and _pid_alive(lock_pid)),
        "voice_speak": _operator_voice_speak(),
        "config": cfg,
        "state": read_state(),
        "observe": obs,
        "events_path": str(EVENTS_PATH).replace("\\", "/"),
        "state_path": str(STATE_PATH).replace("\\", "/"),
        "config_path": str(CONFIG_PATH).replace("\\", "/"),
    }


def _min_s_n(cfg: dict[str, Any]) -> float:
    return float(load_threshold()) + float(cfg.get("min_master_s_n_margin") or 0.02)


def wait_for_plant(cfg: dict[str, Any]) -> dict[str, Any]:
    """Block until Master S_n clears dormancy margin, or timeout / halt."""
    floor = _min_s_n(cfg)
    timeout = float(cfg.get("s_n_wait_timeout_s") or 1800)
    poll = max(5.0, float(cfg.get("s_n_poll_s") or 30))
    t0 = time.time()
    last: dict[str, Any] = {}
    while True:
        if overnight_halted():
            return {"ok": False, "reason": "halted", "observe": observe_state()}
        last = observe_state()
        sn = float(last.get("master_s_n") or 0.0)
        status = str(last.get("status") or "")
        active_ok = (not cfg.get("require_active")) or status.upper() == "ACTIVE"
        if sn >= floor and active_ok:
            return {"ok": True, "observe": last, "waited_s": round(time.time() - t0, 1), "floor": floor}
        if time.time() - t0 >= timeout:
            return {
                "ok": False,
                "reason": "s_n_wait_timeout",
                "observe": last,
                "floor": floor,
                "waited_s": round(time.time() - t0, 1),
            }
        _emit("waiting_s_n", master_s_n=sn, floor=floor, status=status)
        time.sleep(poll)


def _integrity_gate(cfg: dict[str, Any]) -> dict[str, Any]:
    from lib.integrity_review import review

    rep = review(prt_tail=40, voice_tail=20)
    halt_flags = set(cfg.get("integrity_halt_flags") or ["near_dead"])
    hit = [f for f in (rep.get("flags") or []) if f in halt_flags]
    return {"ok": not hit, "halt_flags_hit": hit, "report": rep}


def _kill_process_tree(pid: int) -> None:
    """Force-stop apply subprocess (Windows process tree)."""
    if pid <= 0:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return
    try:
        os.kill(pid, 15)
    except OSError:
        pass


def force_halt(reason: str = "operator_force") -> dict[str, Any]:
    """Write halt flag and kill overnight process tree immediately (seconds, not a full round)."""
    path = request_halt(reason)
    state = read_state()
    pid = int(state.get("pid") or 0)
    killed = False
    if pid and _pid_alive(pid):
        _kill_process_tree(pid)
        killed = True
        time.sleep(0.5)
    # Drop lock even if this CLI process is not the overnight owner
    if LOCK_PATH.is_file():
        LOCK_PATH.unlink(missing_ok=True)
    out = {
        "ok": True,
        "halt": str(path).replace("\\", "/"),
        "reason": reason,
        "force": True,
        "killed_pid": pid if killed else None,
        "pid_alive_after": _pid_alive(pid) if pid else False,
    }
    _emit("halt_force", **out)
    # Mark state halted if a run was active
    if state.get("status") == "RUNNING":
        state = dict(state)
        state.update(
            {
                "ok": False,
                "status": "HALTED",
                "reason": f"force_halt:{reason}",
                "finished_at": _utc(),
            }
        )
        _write_state(state)
    return out


def run_apply_round(cfg: dict[str, Any], *, round_id: int, speak_cycles: int) -> dict[str, Any]:
    """One apply via subprocess so GPU memory releases between rounds.

    Polls overnight halt while apply runs; kills the apply tree within ~2s of halt.
    """
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = AUDIT_DIR / f"prt_overnight_r{round_id:03d}.log"
    # Same interpreter as overnight parent (venv trampoline → Python312 on Windows)
    py = Path(sys.executable)
    _life = cfg.get("life_cycles")
    life_n = 0 if _life is None else int(_life)
    _pulse = cfg.get("pulse_cycles")
    pulse_n = 0 if _pulse is None else int(_pulse)
    _obs = cfg.get("observe_cycles")
    observe_n = 10 if _obs is None else int(_obs)
    obs = observe_state()
    if cfg.get("skip_speak_if_dormant") and str(obs.get("status") or "").upper() != "ACTIVE":
        life_n = 0
        pulse_n = 0
    cmd = [
        str(py),
        "-u",
        str(PRT_MAIN),
        "apply",
        "--observe-cycles",
        str(observe_n),
        "--life-cycles",
        str(life_n),
        "--speak-cycles",
        str(int(speak_cycles)),
        "--pulse-cycles",
        str(pulse_n),
        "--settle",
        str(float(cfg.get("settle_s") or 4.0)),
        "--steps",
        str(int(cfg.get("steps") or 120)),
        "--lr",
        str(float(cfg.get("lr") or 8e-5)),
    ]
    _emit("apply_start", round=round_id, cmd=cmd, log=str(log_path).replace("\\", "/"))
    t0 = time.time()
    halted_mid = False
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    with log_path.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(
            cmd,
            stdout=fh,
            stderr=subprocess.STDOUT,
            cwd=str(FOUNDATION_ROOT),
            env=env,
        )
        while True:
            ret = proc.poll()
            if ret is not None:
                break
            if overnight_halted():
                halted_mid = True
                _emit("apply_halt_kill", round=round_id, pid=proc.pid)
                _kill_process_tree(int(proc.pid))
                try:
                    proc.wait(timeout=15)
                except Exception:  # noqa: BLE001
                    pass
                break
            time.sleep(1.0)
        returncode = proc.returncode if proc.returncode is not None else (1 if halted_mid else 0)
    elapsed = round(time.time() - t0, 1)
    ok = (returncode == 0) and not halted_mid
    result = {
        "ok": ok,
        "returncode": returncode,
        "elapsed_s": elapsed,
        "log": str(log_path).replace("\\", "/"),
        "speak_cycles": speak_cycles,
        "round": round_id,
        "halted_mid_apply": halted_mid,
    }
    _emit("apply_end", **result)
    return result


def run_overnight(
    *,
    max_rounds: int | None = None,
    max_hours: float | None = None,
    cooldown_s: float | None = None,
    dry_run: bool = False,
    config_path: Path | None = None,
    perpetual: bool = False,
    capability_expansion: bool = False,
    min_speak_reward_for_expand: float | None = None,
    force_voice_speak_off: bool = False,
    autonomous_audit: bool = False,
    ide_inbox: bool = False,
) -> dict[str, Any]:
    """Main sleep-safe loop. Returns final state dict.

    perpetual=True: ignore max_rounds ceiling; run until halt / max_hours / failures.
    capability_expansion=True: after integrity pass, optional PRT-scored sandbox expand.
    force_voice_speak_off=True: autonomous path — never enable external speak.
    ide_inbox=True: after each round, drain Architect inbox via Viv IDE tools/skills.
    """
    cfg = load_config(config_path)
    if max_rounds is not None:
        cfg["max_rounds"] = int(max_rounds)
    if max_hours is not None:
        cfg["max_hours"] = float(max_hours)
    if cooldown_s is not None:
        cfg["cooldown_s"] = float(cooldown_s)
    cfg["perpetual"] = bool(perpetual)
    cfg["capability_expansion"] = bool(capability_expansion or cfg.get("capability_expansion"))
    if min_speak_reward_for_expand is not None:
        cfg["min_speak_reward_for_expand"] = float(min_speak_reward_for_expand)
    cfg.setdefault("min_speak_reward_for_expand", 0.6)
    if force_voice_speak_off:
        cfg["voice_speak"] = False
    else:
        cfg["voice_speak"] = _operator_voice_speak()
    cfg["autonomous_audit"] = bool(autonomous_audit or perpetual)
    cfg["ide_inbox"] = bool(ide_inbox)

    # CPU-first gate: refuse GPU overnight unless explicitly enabled in cpu_config.prt
    try:
        from lib.prt_cycle import _load_prt_cfg

        prt_cfg = _load_prt_cfg()
        if not bool(prt_cfg.get("gpu_overnight_enabled", False)) and not dry_run:
            out = {
                "ok": False,
                "status": "REFUSED",
                "reason": "gpu_overnight_parked_cpu_first",
                "hint": "Set cpu_config.prt.gpu_overnight_enabled=true for real LoRA apply (autonomous needs GPU train).",
            }
            _emit("refused_start", **out)
            if cfg.get("autonomous_audit"):
                _autonomous_audit("refused_start", **out)
            _write_state({**out, "timestamp": _utc()})
            return out
    except Exception as exc:  # noqa: BLE001
        _emit("gpu_overnight_gate_error", error=str(exc))

    if overnight_halted():
        out = {
            "ok": False,
            "status": "HALTED",
            "reason": "halt_flag_present",
            "hint": "prt_main.py night resume  (clears prt_overnight_halt.flag)",
        }
        _emit("refused_start", **out)
        if cfg.get("autonomous_audit"):
            _autonomous_audit("refused_start", **out)
        _write_state({**out, "timestamp": _utc()})
        return out

    try:
        acquire_lock()
    except RuntimeError as exc:
        out = {"ok": False, "status": "BUSY", "reason": str(exc)}
        _emit("refused_start", **out)
        if cfg.get("autonomous_audit"):
            _autonomous_audit("refused_start", **out)
        return out

    started = time.time()
    rounds_done = 0
    fails = 0
    history: list[dict[str, Any]] = []
    status = "RUNNING"
    reason = ""

    voice_flag = False if force_voice_speak_off else _operator_voice_speak()
    state = {
        "ok": True,
        "status": status,
        "mode": "autonomous" if perpetual else "overnight",
        "started_at": _utc(),
        "pid": os.getpid(),
        "dry_run": dry_run,
        "config": cfg,
        "rounds_done": 0,
        "consecutive_failures": 0,
        "history": history,
        "voice_speak": voice_flag,
        "capability_expansion": bool(cfg.get("capability_expansion")),
    }
    _write_state(state)
    _emit("loop_start", dry_run=dry_run, config=cfg, perpetual=perpetual)
    if cfg.get("autonomous_audit"):
        _autonomous_audit(
            "autonomous_start",
            profile=cfg.get("profile"),
            voice_speak=voice_flag,
            capability_expansion=bool(cfg.get("capability_expansion")),
            dry_run=dry_run,
        )

    piston_started = False
    piston_beats = 0
    telemetry_epoch: dict[str, Any] | None = None
    if cfg.get("piston_background"):
        try:
            from lib.piston_background import start_piston_background

            piston_started = start_piston_background(
                interval=float(cfg.get("piston_interval_s") or 1.0),
                journal=False,
            )
            _emit("piston_background_start", started=piston_started)
        except Exception as exc:  # noqa: BLE001
            _emit("piston_background_error", error=str(exc))

    if cfg.get("begin_telemetry_epoch"):
        try:
            from lib.prt_stage import begin_live_telemetry_epoch

            telemetry_epoch = begin_live_telemetry_epoch(
                note=str(cfg.get("telemetry_epoch_note") or "overnight live piston_background"),
                ghost_baseline_path=cfg.get("ghost_baseline_run"),
            )
            _emit("telemetry_epoch_begin", **{k: telemetry_epoch[k] for k in telemetry_epoch if k != "releases"})
        except Exception as exc:  # noqa: BLE001
            _emit("telemetry_epoch_error", error=str(exc))

    try:
        max_r = int(cfg.get("max_rounds") or 10)
        # Perpetual unbound only when operator did not pass a finite proof bound
        proof_bound = max_rounds is not None and int(max_rounds) < 1_000_000
        if perpetual and not proof_bound:
            max_r = 10**9
        max_h = float(cfg.get("max_hours") or 0.0)
        if perpetual and max_h <= 0 and not proof_bound:
            max_h = 8760.0  # 1 year ceiling unless operator sets max_hours
        cool = float(cfg.get("cooldown_s") or 900)
        max_fail = int(cfg.get("max_consecutive_failures") or 2)

        i = 0
        while True:
            i += 1
            if overnight_halted():
                status, reason = "HALTED", "operator_or_global_halt"
                break
            if max_h > 0 and (time.time() - started) / 3600.0 >= max_h:
                status, reason = "TIME_BUDGET", "max_hours"
                break
            if i > max_r:
                status, reason = "COMPLETE", "max_rounds"
                break

            if dry_run:
                plant = {"ok": True, "observe": observe_state(), "dry_run": True, "floor": _min_s_n(cfg)}
            else:
                plant = wait_for_plant(cfg)
            if not plant.get("ok"):
                fails += 1
                history.append({"round": i, "phase": "wait_plant", **plant})
                _emit("plant_wait_failed", round=i, **plant)
                if fails >= max_fail:
                    status, reason = "HALTED", "plant_wait_failures"
                    request_halt(reason)
                    break
                continue

            _sp = cfg.get("speak_cycles")
            speak_n = 5 if _sp is None else int(_sp)
            obs = plant.get("observe") or {}
            if cfg.get("skip_speak_if_dormant") and str(obs.get("status") or "").upper() != "ACTIVE":
                speak_n = 0

            if dry_run:
                result = {
                    "ok": True,
                    "dry_run": True,
                    "round": i,
                    "speak_cycles": speak_n,
                    "observe": obs,
                }
            else:
                result = run_apply_round(cfg, round_id=i, speak_cycles=speak_n)

            settle_s = float(cfg.get("pre_integrity_settle_s") or 0)
            if settle_s > 0 and not dry_run:
                _emit("pre_integrity_settle", round=i, seconds=settle_s)
                cool_until = time.time() + settle_s
                while time.time() < cool_until:
                    if overnight_halted():
                        break
                    time.sleep(min(5.0, cool_until - time.time()))

            if dry_run:
                integ = {
                    "ok": True,
                    "halt_flags_hit": [],
                    "report": {"verdict": "dry_run", "prt_past": {"speak_reward_rate": None}},
                }
            else:
                integ = _integrity_gate(cfg)
            speak_rr = ((integ.get("report") or {}).get("prt_past") or {}).get("speak_reward_rate")
            result["integrity"] = {
                "ok": integ.get("ok"),
                "halt_flags_hit": integ.get("halt_flags_hit"),
                "verdict": (integ.get("report") or {}).get("verdict"),
                "speak_reward_rate": speak_rr,
            }
            history.append(result)
            rounds_done = i
            if cfg.get("autonomous_audit"):
                _autonomous_audit(
                    "integrity",
                    round=i,
                    speak_reward_rate=speak_rr,
                    ok=integ.get("ok"),
                    flags=integ.get("halt_flags_hit"),
                    apply_ok=result.get("ok"),
                    elapsed_s=result.get("elapsed_s"),
                )

            if not result.get("ok"):
                fails += 1
            else:
                fails = 0

            if not integ.get("ok"):
                hit = set(integ.get("halt_flags_hit") or [])
                only_transient = hit and hit.issubset(_RECOVERABLE_FLAGS)
                if only_transient and cfg.get("recover_on_near_dead") and not overnight_halted():
                    _emit("integrity_recover_wait", round=i, flags=sorted(hit))
                    recover_cfg = dict(cfg)
                    recover_cfg["s_n_wait_timeout_s"] = float(
                        cfg.get("near_dead_recover_timeout_s") or 1800
                    )
                    recovery = wait_for_plant(recover_cfg)
                    result["integrity_recovery"] = {
                        "ok": recovery.get("ok"),
                        "waited_s": recovery.get("waited_s"),
                        "flags": sorted(hit),
                    }
                    if recovery.get("ok"):
                        _emit("integrity_recovered", round=i, waited_s=recovery.get("waited_s"))
                    else:
                        status, reason = "HALTED", f"integrity_unrecovered:{sorted(hit)}"
                        request_halt(reason)
                        break
                else:
                    status, reason = "HALTED", f"integrity:{sorted(hit)}"
                    request_halt(reason)
                    break

            # Optional capability expansion — after integrity; not on dry_run
            if (
                cfg.get("capability_expansion")
                and integ.get("ok")
                and not overnight_halted()
                and not dry_run
            ):
                try:
                    from lib.prt_capability_expand import run_capability_expansion

                    expand = run_capability_expansion(
                        s_n=float((plant.get("observe") or {}).get("master_s_n") or 0.5),
                        min_speak_reward_rate=float(cfg.get("min_speak_reward_for_expand") or 0.6),
                        speak_reward_rate=float(speak_rr) if speak_rr is not None else None,
                    )
                    result["capability_expansion"] = expand
                    _emit(
                        "capability_expansion",
                        round=i,
                        skipped=expand.get("skipped"),
                        label=((expand.get("score") or {}).get("label")),
                        module=((expand.get("gap") or {}).get("module")),
                    )
                    if cfg.get("autonomous_audit"):
                        _autonomous_audit(
                            "capability_expansion",
                            round=i,
                            skipped=expand.get("skipped"),
                            label=((expand.get("score") or {}).get("label")),
                            module=((expand.get("gap") or {}).get("module")),
                            committed=((expand.get("commit") or {}).get("committed")),
                        )
                except Exception as exc:  # noqa: BLE001
                    result["capability_expansion"] = {"ok": False, "error": str(exc)}
                    _emit("capability_expansion_error", round=i, error=str(exc))
                    if cfg.get("autonomous_audit"):
                        _autonomous_audit("capability_expansion_error", round=i, error=str(exc))

            # Viv IDE: process Architect inbox (Cursor-replacement work between PRT rounds)
            if cfg.get("ide_inbox") and not overnight_halted() and not dry_run:
                try:
                    from lib.viv_ide import drain_inbox

                    ide = drain_inbox(max_turns=1, speak=False)
                    result["ide_inbox"] = {
                        "ok": ide.get("ok"),
                        "processed": ide.get("processed"),
                    }
                    _emit("ide_inbox", round=i, processed=ide.get("processed"))
                    if cfg.get("autonomous_audit"):
                        _autonomous_audit("ide_inbox", round=i, processed=ide.get("processed"))
                except Exception as exc:  # noqa: BLE001
                    result["ide_inbox"] = {"ok": False, "error": str(exc)}
                    _emit("ide_inbox_error", round=i, error=str(exc))

            growth_note: dict[str, Any] = {}
            if not dry_run:
                try:
                    from lib.growth_strain import load_growth_config, strain_tick

                    gcfg = load_growth_config()
                    ticks = int(gcfg.get("overnight_strain_ticks") or 0)
                    apply = bool(gcfg.get("apply_on_overnight"))
                    last_tick: dict[str, Any] = {}
                    for _ in range(max(0, ticks)):
                        last_tick = strain_tick(apply_growth=apply)
                        if last_tick.get("near_dead") or last_tick.get("fired"):
                            break
                    growth_note = last_tick
                    result["growth"] = growth_note
                    _emit("growth_tick", round=i, **{k: v for k, v in growth_note.items() if k != "plant"})
                except Exception as exc:  # noqa: BLE001
                    growth_note = {"ok": False, "error": str(exc)}
                    result["growth"] = growth_note
                    _emit("growth_tick_error", round=i, error=str(exc))

            if fails >= max_fail:
                status, reason = "HALTED", "consecutive_apply_failures"
                request_halt(reason)
                break

            state.update(
                {
                    "status": "RUNNING",
                    "rounds_done": rounds_done,
                    "consecutive_failures": fails,
                    "last_round": result,
                    "updated_at": _utc(),
                    "elapsed_h": round((time.time() - started) / 3600.0, 3),
                }
            )
            _write_state(state)

            if i >= max_r:
                status, reason = "COMPLETE", "max_rounds"
                break
            if max_h > 0 and (time.time() - started) / 3600.0 >= max_h:
                status, reason = "TIME_BUDGET", "max_hours"
                break

            _emit("cooldown", seconds=cool, next_round=i + 1)
            until = time.time() + cool
            while time.time() < until:
                if overnight_halted():
                    status, reason = "HALTED", "halt_during_cooldown"
                    break
                time.sleep(min(15.0, until - time.time()))
            if status == "HALTED":
                break

        final = {
            "ok": status in ("COMPLETE", "TIME_BUDGET"),
            "status": status,
            "reason": reason,
            "mode": "autonomous" if perpetual else "overnight",
            "rounds_done": rounds_done,
            "consecutive_failures": fails,
            "elapsed_h": round((time.time() - started) / 3600.0, 3),
            "finished_at": _utc(),
            "history": history,
            "voice_speak": voice_flag,
            "capability_expansion": bool(cfg.get("capability_expansion")),
            "dry_run": dry_run,
            "config": cfg,
            "events_path": str(EVENTS_PATH).replace("\\", "/"),
            "state_path": str(STATE_PATH).replace("\\", "/"),
            "autonomous_audit": str(AUTONOMOUS_AUDIT).replace("\\", "/")
            if cfg.get("autonomous_audit")
            else None,
        }
        _write_state(final)
        _emit("loop_end", **{k: v for k, v in final.items() if k != "history"})
        if cfg.get("autonomous_audit"):
            _autonomous_audit(
                "loop_end",
                status=status,
                reason=reason,
                rounds_done=rounds_done,
                elapsed_h=final.get("elapsed_h"),
            )
        return final
    finally:
        if cfg.get("piston_background"):
            try:
                from lib.piston_background import stop_piston_background

                piston_beats = stop_piston_background()
                _emit("piston_background_stop", beats=piston_beats, started=piston_started)
            except Exception as exc:  # noqa: BLE001
                _emit("piston_background_stop_error", error=str(exc))
        release_lock()


def run_autonomous(
    *,
    max_hours: float | None = None,
    cooldown_s: float | None = None,
    dry_run: bool = False,
    config_path: Path | None = None,
    capability_expansion: bool = False,
    min_speak_reward_for_expand: float | None = None,
    max_rounds: int | None = None,
    force_voice_speak_off: bool = True,
    autonomous_audit: bool = True,
    ide_inbox: bool = True,
) -> dict[str, Any]:
    """Perpetual PRT self-improvement loop (fully autonomous PRT-driven).

    Same collect→apply→integrity→cooldown as overnight, without round ceiling
    unless max_rounds is set for a bounded proof. voice_speak off by default.
    ide_inbox: drain Architect asks via Viv IDE between rounds.
    """
    return run_overnight(
        max_rounds=max_rounds if max_rounds is not None else 10**9,
        max_hours=max_hours if max_hours is not None else 0.0,  # 0 → perpetual year ceiling inside
        cooldown_s=cooldown_s,
        dry_run=dry_run,
        config_path=config_path,
        perpetual=True,
        capability_expansion=capability_expansion,
        min_speak_reward_for_expand=min_speak_reward_for_expand,
        force_voice_speak_off=force_voice_speak_off,
        autonomous_audit=autonomous_audit,
        ide_inbox=ide_inbox,
    )