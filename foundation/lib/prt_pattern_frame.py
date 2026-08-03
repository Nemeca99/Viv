"""Action-conditioned plant pattern frames for PRT prediction.

Helps Viv form patterns: normalize plant state + attach per-act priors
(observe ≈ hold, speak ≈ RLE/S_n dip from GPU crystallize, life ≈ mild load).

Not training. Representation — so she can predict against task shape.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from lib.paths import ARTIFACTS

PRT_CYCLES_PATH = ARTIFACTS / "models" / "prt_cycles.jsonl"

# Curriculum fallbacks when history is thin (from Architect plant observation)
_CURRICULUM_DELTA: dict[str, dict[str, float]] = {
    "observe": {"master_rsr": 0.0, "master_ltp": 0.0, "master_rle": 0.0, "master_s_n": 0.0},
    # Speak loads GPU → VRAM RLE crush + mild S_n drop (measured on this host)
    "speak": {"master_rsr": 0.005, "master_ltp": 0.0, "master_rle": -0.06, "master_s_n": -0.03},
    "life": {"master_rsr": -0.01, "master_ltp": -0.005, "master_rle": -0.01, "master_s_n": -0.02},
    # Bounded CPU burst: load/structure + headroom dip while burning
    "pulse": {"master_rsr": -0.005, "master_ltp": -0.02, "master_rle": -0.02, "master_s_n": -0.02},
}

# B3/S23 live_cells survival by seed pattern (measured on Viv PRT history)
_LIFE_SURVIVAL: dict[str, float] = {
    "glider": 1.0,
    "blinker": 1.0,
    "pulsar_seed": 1.5,
    "random": 0.45,
    "dense": 0.26,
}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _f(d: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(d.get(key) if d.get(key) is not None else default)
    except (TypeError, ValueError):
        return default


def enrich_observe(before: dict[str, Any]) -> dict[str, Any]:
    """Add GPU/Corsair headroom fields when available (pattern vocabulary)."""
    out = dict(before)
    try:
        from lib.corsair_telemetry import read_latest

        cue = read_latest()
        pkg = cue.get("cpu_package_c")
        cool = cue.get("coolant_c")
        if pkg is not None:
            out["cpu_package_c"] = float(pkg)
        if cool is not None:
            out["coolant_c"] = float(cool)
        if pkg is not None and cool is not None:
            out["pkg_minus_coolant_c"] = round(float(pkg) - float(cool), 2)
    except Exception:  # noqa: BLE001
        pass
    try:
        from lib.gpu_plant import read_gpu

        g = read_gpu(0)
        out["gpu_util_pct"] = float(g.util_pct)
        out["gpu_power_w"] = float(g.power_w)
        total = max(int(g.mem_total_mib), 1)
        out["gpu_vram_used_mib"] = int(g.mem_used_mib)
        out["gpu_vram_total_mib"] = total
        out["gpu_vram_free_frac"] = round(float(g.mem_free_mib) / float(total), 4)
        out["gpu_temp_c"] = float(g.temp_c)
    except Exception:  # noqa: BLE001
        pass
    # Normalized headroom channels (0-1 patterns)
    out["norm_rsr"] = round(_clamp01(_f(out, "master_rsr")), 4)
    out["norm_ltp"] = round(_clamp01(_f(out, "master_ltp")), 4)
    out["norm_rle"] = round(_clamp01(_f(out, "master_rle")), 4)
    out["norm_s_n"] = round(_clamp01(_f(out, "master_s_n")), 4)
    vfree = out.get("gpu_vram_free_frac")
    if vfree is not None:
        out["norm_gpu_rle"] = round(_clamp01(float(vfree)), 4)
    gap = out.get("pkg_minus_coolant_c")
    if gap is not None:
        out["norm_cool_rle"] = round(_clamp01(1.0 - float(gap) / 30.0), 4)
    return out


def empirical_act_deltas(*, tail: int = 240, min_n: int = 8) -> dict[str, dict[str, float]]:
    """Mean Δ(after−before) per act from recent scored cycles."""
    path = PRT_CYCLES_PATH
    if not path.is_file():
        return {k: dict(v) for k, v in _CURRICULUM_DELTA.items()}
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-tail:]
    except OSError:
        return {k: dict(v) for k, v in _CURRICULUM_DELTA.items()}
    for ln in lines:
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if row.get("excluded"):
            continue
        act_obj = row.get("act")
        act = act_obj.get("act") if isinstance(act_obj, dict) else act_obj
        if act not in ("observe", "speak", "life", "pulse"):
            continue
        b = row.get("observe_before") or {}
        a = row.get("observe_after") or {}
        if not b or not a:
            continue
        for key in ("master_rsr", "master_ltp", "master_rle", "master_s_n"):
            buckets[str(act)][key].append(_f(a, key) - _f(b, key))

    out: dict[str, dict[str, float]] = {}
    for act, keys in _CURRICULUM_DELTA.items():
        out[act] = {}
        for key, fallback in keys.items():
            xs = buckets.get(act, {}).get(key) or []
            if len(xs) >= min_n:
                out[act][key] = round(sum(xs) / len(xs), 4)
            else:
                out[act][key] = float(fallback)
            out[act][f"{key}_n"] = len(xs)
    return out


def empirical_life_survival(*, tail: int = 400, min_n: int = 6) -> dict[str, float]:
    """Mean (live_after / live_before) per Conway seed pattern."""
    out = dict(_LIFE_SURVIVAL)
    path = PRT_CYCLES_PATH
    if not path.is_file():
        return out
    buckets: dict[str, list[float]] = defaultdict(list)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-tail:]
    except OSError:
        return out
    for ln in lines:
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        act_obj = row.get("act")
        if not isinstance(act_obj, dict) or act_obj.get("act") != "life":
            continue
        life = act_obj.get("life") or {}
        before = life.get("before") or {}
        after = life.get("after") or {}
        lb = before.get("live_cells")
        la = after.get("live_cells")
        if not lb or la is None:
            continue
        pat = str(before.get("pattern") or life.get("pattern") or "random")
        buckets[pat].append(float(la) / float(lb))
    for pat, xs in buckets.items():
        if len(xs) >= min_n:
            out[pat] = round(sum(xs) / len(xs), 4)
    return out


def prior_after(before: dict[str, Any], act: str, deltas: dict[str, dict[str, float]] | None = None) -> dict[str, float]:
    """Action-shaped prior for post-settle triad (pattern scaffold)."""
    dmap = deltas or empirical_act_deltas()
    d = dmap.get(act) or _CURRICULUM_DELTA.get(act) or _CURRICULUM_DELTA["observe"]
    pred = {
        "predicted_master_rsr": round(_clamp01(_f(before, "master_rsr") + float(d.get("master_rsr", 0))), 4),
        "predicted_master_ltp": round(_clamp01(_f(before, "master_ltp") + float(d.get("master_ltp", 0))), 4),
        "predicted_master_rle": round(_clamp01(_f(before, "master_rle") + float(d.get("master_rle", 0))), 4),
    }
    # Inline geom composite — avoid circular import with prt_cycle
    from lib.master_rid import sn_from_channels

    pred["predicted_master_s_n"] = round(
        float(
            sn_from_channels(
                pred["predicted_master_rsr"],
                pred["predicted_master_ltp"],
                pred["predicted_master_rle"],
            )
        ),
        4,
    )
    return pred


def build_pattern_frame(
    before: dict[str, Any],
    act: str,
    *,
    life_hint: dict[str, Any] | None = None,
    pulse_hint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = enrich_observe(before)
    deltas = empirical_act_deltas()
    prior = prior_after(enriched, act, deltas)
    frame = {
        "act": act,
        "norm": {
            "rsr": enriched.get("norm_rsr"),
            "ltp": enriched.get("norm_ltp"),
            "rle": enriched.get("norm_rle"),
            "s_n": enriched.get("norm_s_n"),
            "gpu_rle": enriched.get("norm_gpu_rle"),
            "cool_rle": enriched.get("norm_cool_rle"),
        },
        "plant": {
            "status": enriched.get("status"),
            "cpu_load_pct": enriched.get("cpu_load_pct"),
            "cpu_package_c": enriched.get("cpu_package_c") or enriched.get("cpu_temp_c"),
            "coolant_c": enriched.get("coolant_c"),
            "pkg_minus_coolant_c": enriched.get("pkg_minus_coolant_c"),
            "gpu_temp_c": enriched.get("gpu_temp_c"),
            "gpu_util_pct": enriched.get("gpu_util_pct"),
            "gpu_vram_free_frac": enriched.get("gpu_vram_free_frac"),
        },
        "act_delta_prior": {
            "rsr": deltas.get(act, {}).get("master_rsr"),
            "ltp": deltas.get(act, {}).get("master_ltp"),
            "rle": deltas.get(act, {}).get("master_rle"),
            "s_n": deltas.get(act, {}).get("master_s_n"),
        },
        "act_prior_after": prior,
        "note": "Symbiote: host CPU prior — refine from plant norms; never solo omniscience.",
    }
    try:
        from lib.prt_cpu_sample import generate_cpu_sample

        frame["cpu_sample"] = generate_cpu_sample(enriched, act)
    except Exception:  # noqa: BLE001
        frame["cpu_sample"] = None
    if act == "life" and life_hint:
        b = life_hint.get("before") or {}
        live0 = int(b.get("live_cells") or 0)
        gens = int(life_hint.get("generations") or 24)
        pat = str(b.get("pattern") or "random")
        survival = empirical_life_survival()
        ratio = float(survival.get(pat, _LIFE_SURVIVAL.get(pat, 0.45)))
        # Short runs decay less toward extinction for chaotic seeds
        if gens < 16 and pat in ("random", "dense"):
            ratio = min(1.0, ratio + 0.12)
        prior_live = max(0, int(round(live0 * ratio)))
        frame["life"] = {
            "live_before": live0,
            "density": b.get("density"),
            "pattern": pat,
            "generations": gens,
            "survival_ratio": round(ratio, 4),
            "prior_live_after": prior_live,
        }
        prior["predicted_live_cells"] = prior_live
        frame["act_prior_after"] = prior
        if frame.get("cpu_sample"):
            # same survival prior + tiny integer jitter so life guide isn't oracle
            import random as _rnd

            jitter = _rnd.randint(-1, 1)
            frame["cpu_sample"]["predicted_live_cells"] = max(0, prior_live + jitter)
    if act == "pulse" and pulse_hint:
        from lib.pulse_plant import prior_mean_load

        b = pulse_hint.get("before") or {}
        prior_load = prior_mean_load(b)
        frame["pulse"] = {
            "duty": b.get("duty"),
            "seconds": b.get("seconds"),
            "cores": b.get("cores"),
            "total_cores": b.get("total_cores"),
            "baseline_load_pct": b.get("baseline_load_pct"),
            "prior_mean_load_pct": prior_load,
        }
        prior["predicted_mean_load_pct"] = prior_load
        frame["act_prior_after"] = prior
        if frame.get("cpu_sample"):
            import random as _rnd

            frame["cpu_sample"]["predicted_mean_load_pct"] = round(
                float(prior_load) + _rnd.uniform(-1.0, 1.0), 2
            )
    return frame


def format_pattern_prompt_block(frame: dict[str, Any]) -> str:
    """Compact teachable block for the predict prompt."""
    n = frame.get("norm") or {}
    p = frame.get("plant") or {}
    d = frame.get("act_delta_prior") or {}
    a = frame.get("act_prior_after") or {}
    lines = [
        "Pattern frame (normalized 0-1 + act prior). Form your prediction against this.",
        f"norm rsr={n.get('rsr')} ltp={n.get('ltp')} rle={n.get('rle')} s_n={n.get('s_n')} "
        f"gpu_rle={n.get('gpu_rle')} cool_rle={n.get('cool_rle')}",
        f"plant status={p.get('status')} load={p.get('cpu_load_pct')} "
        f"pkg={p.get('cpu_package_c')} cool={p.get('coolant_c')} dT={p.get('pkg_minus_coolant_c')} "
        f"gpu={p.get('gpu_temp_c')}C util={p.get('gpu_util_pct')} vram_free={p.get('gpu_vram_free_frac')}",
        f"act={frame.get('act')} expected_delta rsr={d.get('rsr')} ltp={d.get('ltp')} "
        f"rle={d.get('rle')} s_n={d.get('s_n')}",
        f"act_prior_after rsr={a.get('predicted_master_rsr')} ltp={a.get('predicted_master_ltp')} "
        f"rle={a.get('predicted_master_rle')} s_n={a.get('predicted_master_s_n')}",
    ]
    life = frame.get("life")
    if life:
        lines.append(
            f"life_pattern live_before={life.get('live_before')} "
            f"survival={life.get('survival_ratio')} "
            f"prior_live_after={life.get('prior_live_after')} gens={life.get('generations')} "
            f"pattern={life.get('pattern')}"
        )
    pulse = frame.get("pulse")
    if pulse:
        lines.append(
            f"pulse_pattern duty={pulse.get('duty')} secs={pulse.get('seconds')} "
            f"cores={pulse.get('cores')}/{pulse.get('total_cores')} "
            f"baseline_load={pulse.get('baseline_load_pct')} "
            f"prior_mean_load={pulse.get('prior_mean_load_pct')}"
        )
    return "\n".join(lines) + "\n"
