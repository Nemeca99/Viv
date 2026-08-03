"""Growth ceiling gate — Architect-static policy; optional Rust veto."""
from __future__ import annotations

import json
import time
from typing import Any

from lib.growth_strain import is_near_dead, load_policy, load_state, sample_plant
from lib.paths import FOUNDATION_ROOT

ADAPTER_CONFIG = FOUNDATION_ROOT / "models" / "gpu" / "viv_voice_lora" / "adapter_config.json"


def current_lora_r() -> int:
    if ADAPTER_CONFIG.is_file():
        try:
            data = json.loads(ADAPTER_CONFIG.read_text(encoding="utf-8"))
            return int(data.get("r") or 16)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return 16


def check_growth(
    actuator: str,
    *,
    delta_r: int = 0,
    skip_cooldown: bool = False,
) -> dict[str, Any]:
    """Return allowed + reason. Python enforces policy; Rust veto if available.

    skip_cooldown: operator --force may bypass grow_cooldown only — never ceilings or near_dead.
    """
    policy = load_policy()
    plant = sample_plant()
    state = load_state()
    cur_r = current_lora_r()
    new_r = cur_r + max(0, int(delta_r))
    allowed_acts = set(policy.get("allowed_actuators") or ["lora_widen"])

    out: dict[str, Any] = {
        "actuator": actuator,
        "current_lora_r": cur_r,
        "proposed_lora_r": new_r,
        "max_lora_r": int(policy.get("max_lora_r") or 64),
        "plant_s_n": plant.get("master_s_n"),
        "python_policy": True,
    }

    if actuator not in allowed_acts:
        out.update({"allowed": False, "reason": "actuator_not_allowlisted", "gate": "python"})
        return out

    if policy.get("deny_grow_when_near_dead", True) and is_near_dead(plant, policy):
        out.update({"allowed": False, "reason": "near_dead_protect_host", "gate": "python"})
        return out

    if new_r > int(policy.get("max_lora_r") or 64):
        out.update({"allowed": False, "reason": "max_lora_r_ceiling", "gate": "python"})
        return out

    last = state.get("last_grow_at")
    min_gap = float(policy.get("min_seconds_between_grows") or 300)
    if last and not skip_cooldown:
        try:
            from datetime import datetime

            t_last = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            age = time.time() - t_last.timestamp()
            if age < min_gap:
                out.update(
                    {
                        "allowed": False,
                        "reason": "grow_cooldown",
                        "age_s": round(age, 1),
                        "min_gap_s": min_gap,
                        "gate": "python",
                    }
                )
                return out
        except (TypeError, ValueError, OSError):
            pass

    try:
        from lib.security_membrane import growth_gate as rust_check

        rust = rust_check(actuator, float(new_r), float(policy.get("max_lora_r") or 64))
        out["rust"] = rust
        if rust is not None and not bool(rust.get("allowed", True)):
            out.update(
                {
                    "allowed": False,
                    "reason": rust.get("reason") or "rust_growth_veto",
                    "gate": "rust",
                }
            )
            return out
    except Exception as exc:  # noqa: BLE001
        out["rust_error"] = str(exc)

    out.update({"allowed": True, "reason": "OK", "gate": "python"})
    return out
