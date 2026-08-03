"""Symbiote doctrine — GPU refines CPU/host help; never solo omniscience.

The model is stateless. The CPU owns telemetry, priors, and tags. PRT teaches
her to *use* host help and adapt it to live plant norms — not ignore it (solo
arrogance) and not blindly copy it (no reading).
"""
from __future__ import annotations

from typing import Any


def symbiote_enabled(cfg: dict[str, Any] | None = None) -> bool:
    if cfg is None:
        try:
            from lib.prt_cycle import _load_prt_cfg

            cfg = _load_prt_cfg()
        except Exception:  # noqa: BLE001
            return True
    return bool(cfg.get("symbiote_hint", True))


def symbiote_doctrine_lines() -> str:
    return (
        "[TAG:symbiote] Host CPU help — not your memory. You are stateless; the plant is truth.\n"
        "Use host_prior + act_delta as bait; refine against norm/plant readings. "
        "Solo guess without host context is wrong doctrine.\n"
        "Blind copy without plant check is also wrong — symbiote adapts, does not obey blindly.\n"
    )


def format_symbiote_block(frame: dict[str, Any]) -> str:
    """Explicit tagged host packet the model learns to read."""
    d = frame.get("act_delta_prior") or {}
    a = frame.get("act_prior_after") or {}
    n = frame.get("norm") or {}
    act = frame.get("act") or "observe"
    lines = [
        symbiote_doctrine_lines().rstrip(),
        f"[TAG:host_prior] act={act} "
        f"rsr={a.get('predicted_master_rsr')} ltp={a.get('predicted_master_ltp')} "
        f"rle={a.get('predicted_master_rle')} s_n={a.get('predicted_master_s_n')}",
        f"[TAG:host_delta] rsr={d.get('rsr')} ltp={d.get('ltp')} "
        f"rle={d.get('rle')} s_n={d.get('s_n')}",
        f"[TAG:plant_norm] rsr={n.get('rsr')} ltp={n.get('ltp')} "
        f"rle={n.get('rle')} s_n={n.get('s_n')}",
    ]
    life = frame.get("life")
    if life:
        lines.append(
            f"[TAG:host_life] pattern={life.get('pattern')} "
            f"survival={life.get('survival_ratio')} prior_live={life.get('prior_live_after')}"
        )
    pulse = frame.get("pulse")
    if pulse:
        lines.append(
            f"[TAG:host_pulse] duty={pulse.get('duty')} prior_load={pulse.get('prior_mean_load_pct')}"
        )
    try:
        from lib.prt_cpu_sample import format_cpu_sample_block

        lines.append(format_cpu_sample_block(frame.get("cpu_sample")).rstrip())
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines) + "\n"
