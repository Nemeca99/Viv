"""PC AIOS growth strain — phone control law rewritten onto Master RID.

Phone sim used /proc thermals. Here the teacher is Master S_n + RSR/LTP/RLE.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.dormancy_config import load_threshold
from lib.paths import ARTIFACTS, AUTO_ARTIFACTS
from lib.prt_cycle import observe_state

GROWTH_CONFIG = ARTIFACTS / "models" / "growth_config.json"
BASELINE_PATH = AUTO_ARTIFACTS / "growth_baseline.json"
STATE_PATH = AUTO_ARTIFACTS / "growth_state.json"
EVENTS_PATH = AUTO_ARTIFACTS / "growth_events.jsonl"
POLICY_PATH = AUTO_ARTIFACTS / "growth_policy.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_growth_config() -> dict[str, Any]:
    defaults = {
        "stage": "hatchling",
        "lora_r": 16,
        "lora_alpha": 32,
        "cascade_experts": 8,
        "idle_margin": 0.03,
        "strain_threshold": 0.04,
        "step_dt_s": 1.0,
        "calibrate_seconds": 30,
        "voice_speak": False,
    }
    if GROWTH_CONFIG.is_file():
        try:
            data = json.loads(GROWTH_CONFIG.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                defaults.update(data)
        except (OSError, json.JSONDecodeError):
            pass
    return defaults


def save_growth_config(cfg: dict[str, Any]) -> None:
    GROWTH_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    GROWTH_CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def load_policy() -> dict[str, Any]:
    defaults = {
        "allowed_actuators": ["lora_widen"],
        "max_lora_r": 64,
        "max_cascade_experts": 32,
        "min_seconds_between_grows": 300,
        "deny_grow_when_near_dead": True,
        "critical_s_n": 0.15,
    }
    if POLICY_PATH.is_file():
        try:
            data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                defaults.update(data)
        except (OSError, json.JSONDecodeError):
            pass
    return defaults


def load_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "strain": 0.0,
        "pending_growth": False,
        "pending_delta_r": 0,
        "last_grow_at": None,
        "events": 0,
    }


def write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state = dict(state)
    state["updated_at"] = _utc()
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _emit(event: str, **payload: Any) -> None:
    row = {"timestamp": _utc(), "actor": "growth_strain", "event": event, **payload}
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def sample_plant() -> dict[str, Any]:
    obs = observe_state()
    return {
        "timestamp": obs.get("timestamp"),
        "master_s_n": float(obs.get("master_s_n") or 0.0),
        "master_rsr": float(obs.get("master_rsr") or 0.0),
        "master_ltp": float(obs.get("master_ltp") or 0.0),
        "master_rle": float(obs.get("master_rle") or 0.0),
        "status": str(obs.get("status") or ""),
        "dormancy_threshold": float(obs.get("dormancy_threshold") or load_threshold()),
        "cpu_load_pct": float(obs.get("cpu_load_pct") or 0.0),
        "cpu_temp_c": float(obs.get("cpu_temp_c") or 0.0),
        "gpu_temp_c": float(obs.get("gpu_temp_c") or 0.0),
    }


def is_near_dead(plant: dict[str, Any], policy: dict[str, Any] | None = None) -> bool:
    pol = policy or load_policy()
    sn = float(plant.get("master_s_n") or 0.0)
    crit = float(pol.get("critical_s_n") or 0.15)
    dorm = float(plant.get("dormancy_threshold") or load_threshold())
    return sn <= crit or sn < 0.05


def calibrate(*, seconds: int = 30, interval: float = 1.0) -> dict[str, Any]:
    """Idle Master S_n baseline on PC plant (AIOS), not phone /proc."""
    samples: list[float] = []
    triad: list[dict[str, float]] = []
    n = max(5, int(seconds))
    for i in range(n):
        p = sample_plant()
        samples.append(float(p["master_s_n"]))
        triad.append(
            {
                "rsr": float(p["master_rsr"]),
                "ltp": float(p["master_ltp"]),
                "rle": float(p["master_rle"]),
            }
        )
        print(f"calib {i+1:2d}: S_n={p['master_s_n']:.4f} rsr={p['master_rsr']:.4f} "
              f"ltp={p['master_ltp']:.4f} rle={p['master_rle']:.4f} status={p['status']}", flush=True)
        time.sleep(max(0.2, interval))
    samples_sorted = sorted(samples)
    mid = samples_sorted[len(samples_sorted) // 2]
    cfg = load_growth_config()
    margin = float(cfg.get("idle_margin") or 0.03)
    target = mid - margin
    payload = {
        "timestamp": _utc(),
        "source": "aios_master_rid",
        "seconds": n,
        "baseline_master_s_n": round(mid, 4),
        "target_master_s_n": round(target, 4),
        "idle_margin": margin,
        "samples": [round(x, 4) for x in samples],
        "triad_median": {
            "rsr": round(sorted(t["rsr"] for t in triad)[len(triad) // 2], 4),
            "ltp": round(sorted(t["ltp"] for t in triad)[len(triad) // 2], 4),
            "rle": round(sorted(t["rle"] for t in triad)[len(triad) // 2], 4),
        },
        "note": "Phone sim validated control law; this baseline is PC AIOS plant.",
    }
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _emit("calibrate", **{k: payload[k] for k in ("baseline_master_s_n", "target_master_s_n", "source")})
    return payload


def load_baseline() -> dict[str, Any] | None:
    if not BASELINE_PATH.is_file():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def strain_tick(*, apply_growth: bool = False) -> dict[str, Any]:
    """One strain sample step — for PRT overnight between crystallize rounds."""
    cfg = load_growth_config()
    policy = load_policy()
    baseline = load_baseline()
    if not baseline:
        return {"ok": False, "reason": "no_baseline"}

    target = float(baseline["target_master_s_n"])
    thr = float(cfg.get("strain_threshold") or 0.04)
    dt = float(cfg.get("step_dt_s") or 1.0)
    state = load_state()
    strain = float(state.get("strain") or 0.0)
    plant = sample_plant()
    sn = float(plant["master_s_n"])

    if is_near_dead(plant, policy) and policy.get("deny_grow_when_near_dead", True):
        state["strain"] = 0.0
        state["pending_growth"] = False
        state["pending_delta_r"] = 0
        write_state(state)
        _emit("strain_cleared_near_dead", plant=plant, source="tick")
        return {"ok": True, "near_dead": True, "pending_growth": False, "plant": plant}

    # Cool when above target — residual strain must not fire idle growth
    if sn >= target:
        strain = max(0.0, strain - thr * dt)
        state["strain"] = round(strain, 6)
        write_state(state)
        return {
            "ok": True,
            "near_dead": False,
            "fired": False,
            "cooled": True,
            "strain": state["strain"],
            "pending_growth": bool(state.get("pending_growth")),
            "pending_delta_r": state.get("pending_delta_r"),
            "master_s_n": sn,
            "target": target,
        }

    strain += max(0.0, target - sn) * dt
    fired = False
    if strain >= thr and not state.get("pending_growth"):
        n_new = min(4, max(1, int(round(strain / thr))))
        state["pending_growth"] = True
        state["pending_delta_r"] = int(n_new)
        state["pending_actuator"] = "lora_widen"
        fired = True
        _emit("growth_pending", delta_r=n_new, strain=round(strain, 4), plant=plant, source="tick")
        strain = 0.0

    state["strain"] = round(strain, 6)
    write_state(state)
    result: dict[str, Any] = {
        "ok": True,
        "near_dead": False,
        "fired": fired,
        "strain": state["strain"],
        "pending_growth": bool(state.get("pending_growth")),
        "pending_delta_r": state.get("pending_delta_r"),
        "master_s_n": sn,
        "target": target,
    }
    if fired and apply_growth and cfg.get("apply_on_overnight"):
        from lib.growth_lora_widen import apply_pending_widen

        result["apply"] = apply_pending_widen()
    return result


def run_strain_loop(
    *,
    seconds: float = 120.0,
    apply_growth: bool = False,
) -> dict[str, Any]:
    """Accumulate strain from Master S_n dips; optionally apply lora_widen when pending."""
    cfg = load_growth_config()
    policy = load_policy()
    baseline = load_baseline()
    if not baseline:
        raise SystemExit("no growth baseline — run: growth_main.py calibrate")

    target = float(baseline["target_master_s_n"])
    thr = float(cfg.get("strain_threshold") or 0.04)
    dt = float(cfg.get("step_dt_s") or 1.0)
    state = load_state()
    strain = float(state.get("strain") or 0.0)
    growth_events = 0
    t0 = time.time()
    step = 0
    history: list[dict[str, Any]] = []

    while time.time() - t0 < seconds:
        plant = sample_plant()
        sn = float(plant["master_s_n"])
        if is_near_dead(plant, policy) and policy.get("deny_grow_when_near_dead", True):
            strain = 0.0
            state["pending_growth"] = False
            state["pending_delta_r"] = 0
            state["strain"] = strain
            write_state(state)
            _emit("strain_cleared_near_dead", plant=plant)
            row = {"step": step, "near_dead": True, **plant, "strain": strain}
            history.append(row)
            print(f"step {step:3d} | NEAR_DEAD S_n={sn:.4f} — no grow", flush=True)
            step += 1
            time.sleep(dt)
            continue

        if sn >= target:
            strain = max(0.0, strain - thr * dt)
            state["strain"] = round(strain, 6)
            write_state(state)
            if step % 10 == 0:
                print(
                    f"step {step:3d} | S_n={sn:.4f} ABOVE target={target:.4f} "
                    f"| strain={strain:.3f} (cooling) | pending={state.get('pending_growth')}",
                    flush=True,
                )
            history.append(
                {
                    "step": step,
                    "master_s_n": sn,
                    "strain": round(strain, 4),
                    "pending": bool(state.get("pending_growth")),
                    "cooled": True,
                }
            )
            step += 1
            time.sleep(dt)
            continue

        strain += max(0.0, target - sn) * dt
        fired = False
        if strain >= thr and not state.get("pending_growth"):
            n_new = max(1, int(round(strain / thr)))
            # Cap single event delta
            n_new = min(n_new, 4)
            state["pending_growth"] = True
            state["pending_delta_r"] = int(n_new)
            state["pending_actuator"] = "lora_widen"
            growth_events += 1
            fired = True
            _emit(
                "growth_pending",
                delta_r=n_new,
                strain=round(strain, 4),
                plant=plant,
                target=target,
            )
            print(
                f"\n*** GROWTH PENDING step {step} *** "
                f"S_n={sn:.4f} target={target:.4f} strain={strain:.3f} "
                f"delta_r=+{n_new}",
                flush=True,
            )
            strain = 0.0
            if apply_growth:
                from lib.growth_lora_widen import apply_pending_widen

                result = apply_pending_widen()
                print(json.dumps(result, indent=2, default=str), flush=True)

        state["strain"] = round(strain, 6)
        write_state(state)
        if step % 10 == 0 or fired:
            print(
                f"step {step:3d} | S_n={sn:.4f} rsr={plant['master_rsr']:.3f} "
                f"ltp={plant['master_ltp']:.3f} rle={plant['master_rle']:.3f} "
                f"| strain={strain:.3f} | pending={state.get('pending_growth')}",
                flush=True,
            )
        history.append(
            {
                "step": step,
                "master_s_n": sn,
                "strain": round(strain, 4),
                "pending": bool(state.get("pending_growth")),
            }
        )
        step += 1
        time.sleep(dt)

    summary = {
        "ok": True,
        "seconds": seconds,
        "steps": step,
        "target": target,
        "baseline": baseline.get("baseline_master_s_n"),
        "growth_events": growth_events,
        "final_strain": round(strain, 4),
        "pending_growth": bool(state.get("pending_growth")),
        "pending_delta_r": state.get("pending_delta_r"),
        "state_path": str(STATE_PATH).replace("\\", "/"),
        "events_path": str(EVENTS_PATH).replace("\\", "/"),
        "plant_teacher": "aios_master_rid",
    }
    _emit("run_end", **{k: summary[k] for k in summary if k != "ok"})
    return summary


def status_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "timestamp": _utc(),
        "config": load_growth_config(),
        "policy": load_policy(),
        "baseline": load_baseline(),
        "state": load_state(),
        "plant": sample_plant(),
        "contract": "SUPERCOOLING_GROWTH_CONTRACT.md",
        "voice_speak": False,
    }
