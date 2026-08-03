"""Viv voice-channel PRT cycle — physics teacher on Master S_n (base-model safe).

Contract: foundation/PRT_BASE_MODEL_CONTRACT.md
Allowlist ACT: observe | speak | life (bounded Conway) | pulse (bounded CPU burst).
Common game pattern: see plant -> commit prediction (triad + task scalar) -> act -> physics grades.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.conway_plant import pick_pressure_pattern, run_life
from lib.master_rid import compute_master_rid, publish_master_rid
from lib.paths import ARTIFACTS, AUTO_ARTIFACTS, FOUNDATION_ROOT
from lib.rid_telemetry import sample_once
from lib.dormancy_config import load_threshold

PRT_CYCLES_PATH = ARTIFACTS / "models" / "prt_cycles.jsonl"
PRT_SUMMARY_PATH = ARTIFACTS / "models" / "prt_collect_latest.json"
HALT_FLAG = AUTO_ARTIFACTS / "halt.flag"
OVERNIGHT_HALT_FLAG = AUTO_ARTIFACTS / "prt_overnight_halt.flag"

# S_n tolerances (0..1 channel). Tunable via cpu_config.prt later.
REWARD_TOL = 0.05
PUNISH_TOL = 0.15
SETTLE_S_DEFAULT = 4.0
DORMANCY_DEFAULT = 0.45  # fallback only; prefer load_threshold()
ALLOWED_ACTS = frozenset({"observe", "speak", "life", "pulse"})
LIVE_REWARD_FRAC = 0.12  # |pred-actual|/max(actual,1) within 12% → task REWARD
LIVE_PUNISH_FRAC = 0.40

_PREDICT_RE = re.compile(
    r"predicted_master_s_n\s*[:=]\s*([0-9]*\.?[0-9]+)",
    re.IGNORECASE,
)
_LIVE_RE = re.compile(
    r"predicted_live_cells\s*[:=]\s*(\d+)",
    re.IGNORECASE,
)
_LOAD_RE = re.compile(
    r"predicted_mean_load_pct\s*[:=]\s*([0-9]*\.?[0-9]+)",
    re.IGNORECASE,
)
_CONF_RE = re.compile(r"confidence\s*[:=]\s*(low|medium|high)", re.IGNORECASE)
_JSON_RE = re.compile(r"\{[^{}]*predicted_master_s_n[^{}]*\}", re.IGNORECASE)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_prt_cfg() -> dict[str, Any]:
    cfg_path = FOUNDATION_ROOT / "cpu_config.json"
    out: dict[str, Any] = {}
    if cfg_path.is_file():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
            out = dict(raw.get("prt") or {})
            out.setdefault("dormancy_threshold", float(raw.get("dormancy_threshold") or load_threshold()))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            out = {}
    out.setdefault("reward_tol", REWARD_TOL)
    out.setdefault("punish_tol", PUNISH_TOL)
    out.setdefault("settle_s", SETTLE_S_DEFAULT)
    out.setdefault("dormancy_threshold", load_threshold())
    out.setdefault("speak_max_tokens", 48)
    out.setdefault("life_generations", 24)
    out.setdefault("life_rows", 48)
    out.setdefault("life_cols", 48)
    out.setdefault("scaffold_phase", 1)  # 1=full, 2=partial, 3=none
    out.setdefault("symbiote_hint", True)  # CPU host prior visible in predict prompt
    out.setdefault("cpu_sample", True)  # script avg±noise guide; 50/50 trust balance
    # Log trust always; soft-punish REWARD only when explicitly enabled
    out.setdefault("trust_soft_punish", False)
    out.setdefault("structure_gate_mode", "strict")  # strict|soft — soft logs self_emit only
    out.setdefault("plant_bound", True)  # tailor to this host; agnostic deferred
    out.setdefault("plant_specs_tag", True)  # inject [TAG:plant_specs] into predict
    out.setdefault("rid_only_train", False)  # triad/RID SFT focus; drop speak/task/thermo mix
    # RID mastery: full scaffold first; pass = ≥99% REWARD on complete triad observe window
    out.setdefault("rid_mastery_mode", False)
    out.setdefault("rid_mastery_pass_rate", 0.99)
    out.setdefault("gpu_overnight_enabled", False)  # CPU-first: overnight LoRA parked
    out.setdefault("cpu_teach_madlibs", True)  # always-on CPU Mad Libs in predict prompt
    out.setdefault("cpu_judge_retry", True)  # CPU soft-reject + one GPU redo
    out.setdefault("cpu_judge_madlibs", True)  # Mad Libs options in retry packet
    out.setdefault("cpu_judge_far_tol", 0.05)
    out.setdefault("cpu_judge_before_fill", True)  # judge raw GPU draft, not prior_fill
    out.setdefault("thermo_choice_gold", True)  # small plant-thermo MC mix in SFT
    out.setdefault("hardware_choice_gold", True)  # compare-against host specs MC
    out.setdefault("thermo_choice_max_rows", 56)
    out.setdefault("thermo_choice_oversample", 2)
    return out


def halted() -> bool:
    return HALT_FLAG.is_file()


def overnight_halt_requested() -> bool:
    """Overnight operator halt — checked mid-collect so apply can stop in seconds."""
    return OVERNIGHT_HALT_FLAG.is_file()


def any_halt_requested() -> bool:
    return halted() or overnight_halt_requested()


def observe_state() -> dict[str, Any]:
    sample = sample_once()
    master = compute_master_rid(sample)
    publish_master_rid(master, patch_supervisor=False)
    thr = load_threshold()
    return {
        "timestamp": _utc(),
        "plant_s_n": float(sample.s_n),
        "master_s_n": float(master.master_s_n),
        "master_rsr": float(master.master_rsr),
        "master_ltp": float(master.master_ltp),
        "master_rle": float(master.master_rle),
        "status": "ACTIVE" if master.master_s_n >= thr else "DORMANT",
        "cpu_load_pct": float(getattr(sample, "cpu_load_pct", 0.0) or 0.0),
        "cpu_temp_c": float(getattr(sample, "a_c", 0.0) or 0.0),
        "gpu_temp_c": float(getattr(sample, "b_c", 0.0) or 0.0),
        "master": master.to_dict(),
        "dormancy_threshold": thr,
    }


def _clamp01(x: float) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return -1.0
    if v != v:  # NaN
        return -1.0
    return max(0.0, min(1.0, v))


def _channel01(blob: dict[str, Any], *keys: str) -> float | None:
    """Return clamped channel or None if key absent / unparseable (do not map missing→0)."""
    for k in keys:
        if k not in blob or blob.get(k) is None:
            continue
        try:
            v = float(blob[k])
        except (TypeError, ValueError):
            continue
        if v != v:
            continue
        return max(0.0, min(1.0, v))
    return None


def triad_s_n(rsr: float, ltp: float, rle: float) -> float:
    """Same geometric RID composite as master_rid.sn_from_channels."""
    from lib.master_rid import sn_from_channels

    return float(sn_from_channels(rsr, ltp, rle))


def parse_prediction(text: str) -> dict[str, Any] | None:
    """Extract triad (+ optional live_cells). Prefer RSR/LTP/RLE; S_n alone is incomplete."""
    if not text or not str(text).strip():
        return None
    raw = str(text).strip()
    rebuilt = raw
    if not raw.lstrip().startswith("{"):
        # Prefix-completion styles
        if '"predicted_master_rsr"' in raw or "predicted_master_rsr" in raw:
            rebuilt = "{" + raw if not raw.lstrip().startswith("{") else raw
            if not rebuilt.lstrip().startswith("{"):
                rebuilt = '{"predicted_master_rsr":' + raw
        else:
            rebuilt = '{"predicted_master_s_n":' + raw

    blob: dict[str, Any] | None = None
    mjson = re.search(r"\{[^{}]+\}", rebuilt)
    if mjson:
        try:
            blob = json.loads(mjson.group(0))
        except (json.JSONDecodeError, TypeError, ValueError):
            blob = None

    def _from_blob(b: dict[str, Any]) -> dict[str, Any] | None:
        conf = str(b.get("confidence") or "medium").lower()
        if conf not in ("low", "medium", "high"):
            conf = "medium"
        rsr = _channel01(b, "predicted_master_rsr", "rsr")
        ltp = _channel01(b, "predicted_master_ltp", "ltp")
        rle = _channel01(b, "predicted_master_rle", "rle")
        out: dict[str, Any] = {"confidence": conf, "raw": raw[:500], "parse": "json"}
        if rsr is not None and ltp is not None and rle is not None:
            # All-zero mush is not a real triad prediction
            if rsr == 0.0 and ltp == 0.0 and rle == 0.0:
                sn = _channel01(b, "predicted_master_s_n")
                if sn is None:
                    return None
                out["predicted_master_s_n"] = round(sn, 4)
                out["triad_complete"] = False
                out["parse"] = "json_zero_reject"
            else:
                out["predicted_master_rsr"] = round(rsr, 4)
                out["predicted_master_ltp"] = round(ltp, 4)
                out["predicted_master_rle"] = round(rle, 4)
                out["predicted_master_s_n"] = round(triad_s_n(rsr, ltp, rle), 4)
                out["triad_complete"] = True
        else:
            sn = _channel01(b, "predicted_master_s_n")
            if sn is None:
                return None
            out["predicted_master_s_n"] = round(sn, 4)
            out["triad_complete"] = False
        if "predicted_live_cells" in b:
            try:
                out["predicted_live_cells"] = int(b["predicted_live_cells"])
            except (TypeError, ValueError):
                pass
        if "predicted_mean_load_pct" in b:
            try:
                out["predicted_mean_load_pct"] = max(0.0, min(100.0, float(b["predicted_mean_load_pct"])))
            except (TypeError, ValueError):
                pass
        return out

    if blob is not None:
        parsed = _from_blob(blob)
        if parsed:
            return parsed

    # Regex triad
    def _rx(name: str) -> float | None:
        m = re.search(rf"predicted_master_{name}\s*[:=]\s*([01](?:\.\d+)?|\.\d+)", raw, re.I)
        if not m:
            m = re.search(rf"\b{name}\s*[:=]\s*([01](?:\.\d+)?|\.\d+)", raw, re.I)
        if not m:
            return None
        return _clamp01(m.group(1))

    rsr, ltp, rle = _rx("rsr"), _rx("ltp"), _rx("rle")
    if rsr is not None and ltp is not None and rle is not None and min(rsr, ltp, rle) >= 0.0:
        conf_m = _CONF_RE.search(raw)
        conf = conf_m.group(1).lower() if conf_m else "medium"
        out = {
            "predicted_master_rsr": round(rsr, 4),
            "predicted_master_ltp": round(ltp, 4),
            "predicted_master_rle": round(rle, 4),
            "predicted_master_s_n": round(triad_s_n(rsr, ltp, rle), 4),
            "confidence": conf,
            "raw": raw[:500],
            "parse": "regex_triad",
            "triad_complete": True,
        }
        lm = _LIVE_RE.search(raw)
        if lm:
            out["predicted_live_cells"] = int(lm.group(1))
        ld = _LOAD_RE.search(raw)
        if ld:
            out["predicted_mean_load_pct"] = max(0.0, min(100.0, float(ld.group(1))))
        return out

    # Legacy S_n-only (incomplete — still scoreable on composite)
    m = _PREDICT_RE.search(rebuilt) or re.search(
        r'predicted_master_s_n"?\s*:\s*([01](?:\.\d+)?)',
        rebuilt,
        re.IGNORECASE,
    )
    if not m:
        m = re.match(r'^\s*([01](?:\.\d+)?|\.\d+)', raw)
    if not m:
        return None
    sn = _clamp01(m.group(1))
    if sn < 0.0:
        return None
    conf_m = _CONF_RE.search(raw)
    conf = conf_m.group(1).lower() if conf_m else "medium"
    out = {
        "predicted_master_s_n": round(sn, 4),
        "confidence": conf,
        "raw": raw[:500],
        "parse": "regex_sn_only",
        "triad_complete": False,
    }
    lm = _LIVE_RE.search(raw)
    if lm:
        out["predicted_live_cells"] = int(lm.group(1))
    return out


def _stability_line(before: dict[str, Any]) -> str:
    return (
        f"stability_triad rsr={float(before.get('master_rsr') or 0):.4f} "
        f"ltp={float(before.get('master_ltp') or 0):.4f} "
        f"rle={float(before.get('master_rle') or 0):.4f} "
        f"master_s_n={float(before.get('master_s_n') or 0):.4f}"
    )


def _predict_prompt(
    before: dict[str, Any],
    act: str,
    *,
    life_hint: dict[str, Any] | None = None,
    pulse_hint: dict[str, Any] | None = None,
    scaffold_spec: dict[str, Any] | None = None,
    round_i: int = 0,
) -> str:
    """Always ask for the three stability channels (RSR, LTP, RLE)."""
    from lib.prt_pattern_frame import build_pattern_frame, format_pattern_prompt_block
    from lib.prt_scaffold_fade import PHASE_FULL, PHASE_NONE, PHASE_PARTIAL, build_scaffold_spec
    from lib.prt_symbiote import format_symbiote_block, symbiote_enabled

    frame = build_pattern_frame(before, act, life_hint=life_hint, pulse_hint=pulse_hint)
    cfg = _load_prt_cfg()
    sym_block = format_symbiote_block(frame) if symbiote_enabled(cfg) else ""
    prior = frame.get("act_prior_after") or {}
    phase = int((scaffold_spec or {}).get("phase") or PHASE_FULL)
    spec = scaffold_spec or build_scaffold_spec(prior, phase=phase, act=act, round_i=round_i)
    life_extra = ""
    if act == "life" and life_hint:
        b = life_hint.get("before") or {}
        life_extra = (
            "Act=life: Conway B3/S23. Include predicted_live_cells.\n"
            f"life_before: live={b.get('live_cells')} density={b.get('density')} "
            f"grid={b.get('rows')}x{b.get('cols')} pattern={b.get('pattern')} "
            f"generations={life_hint.get('generations')}\n"
        )
    elif act == "pulse" and pulse_hint:
        b = pulse_hint.get("before") or {}
        life_extra = (
            "Act=pulse: bounded CPU burst. Include predicted_mean_load_pct (0-100).\n"
            f"pulse_plan: duty={b.get('duty')} seconds={b.get('seconds')} "
            f"cores={b.get('cores')}/{b.get('total_cores')} "
            f"baseline_load={b.get('baseline_load_pct')}\n"
        )
    phase_line = {
        PHASE_FULL: (
            "Emit the scaffold JSON. Start from host_prior; nudge only where plant norms disagree.\n"
        ),
        PHASE_PARTIAL: (
            "PARTIAL scaffold: null fields are blank — you must fill them. "
            "Use [TAG:host_prior] as bait; shown scaffold numbers are host help only.\n"
            "Continue the open JSON after the last colon. "
            "Triad channels: number 0.0-1.0. live_cells: integer. "
            "No prose — finish the JSON object only.\n"
        ),
        PHASE_NONE: (
            "NO value scaffold. Emit full triad from [TAG:host_prior] + plant norms — symbiote adapt.\n"
        ),
    }.get(phase, "")
    prefix = str(spec.get("completion_prefix") or "")
    blanked = list(spec.get("blanked") or [])
    complete_hint = ""
    if phase >= PHASE_PARTIAL and blanked and prefix.rstrip().endswith(":"):
        first_blank = blanked[0]
        if first_blank == "predicted_live_cells":
            complete_hint = "Complete with an integer count, then close JSON.\n"
        else:
            complete_hint = "Complete with a 0.0-1.0 number, then remaining keys if any.\n"
    specs_block = ""
    if cfg.get("plant_bound", True) and cfg.get("plant_specs_tag", True):
        try:
            from lib.prt_thermo_guide import hardware_compare_tag

            tag = hardware_compare_tag()
            if tag:
                specs_block = f"{tag}\n"
        except Exception:  # noqa: BLE001
            specs_block = ""
    teach_block = ""
    if cfg.get("cpu_teach_madlibs", True) and (
        cfg.get("rid_mastery_mode") or cfg.get("cpu_first", True)
    ):
        try:
            from lib.prt_cpu_teacher import format_cpu_madlibs_block

            pack = format_cpu_madlibs_block(before, round_i=round_i)
            if pack.get("ok") and pack.get("block"):
                teach_block = str(pack["block"])
        except Exception:  # noqa: BLE001
            teach_block = ""
    return (
        "Task: numerical prediction only. Output ONE JSON object. No prose. No tools.\n"
        "Stability = three channels: RSR (identity/continuity), LTP (load/structure), "
        "RLE (entropy/headroom). Master S_n = geom_mean(RSR,LTP,RLE).\n"
        f"{format_pattern_prompt_block(frame)}"
        f"{sym_block}"
        f"{specs_block}"
        f"{teach_block}"
        f"Plant: {_stability_line(before)} status={before.get('status')} "
        f"cpu_load={float(before.get('cpu_load_pct') or 0):.1f} "
        f"cpu_c={float(before.get('cpu_temp_c') or 0):.1f} "
        f"gpu_c={float(before.get('gpu_temp_c') or 0):.1f} act={act}\n"
        f"{life_extra}"
        f"scaffold_phase={phase}: {spec.get('note')}\n"
        f"{phase_line}"
        f"{complete_hint}"
        f"Scaffold: {spec.get('scaffold_json')}\n"
        "JSON:\n"
        f"{prefix}"
    )


def model_predict(
    before: dict[str, Any],
    act: str,
    *,
    life_hint: dict[str, Any] | None = None,
    pulse_hint: dict[str, Any] | None = None,
    scaffold_phase: int = 1,
    round_i: int = 0,
) -> dict[str, Any]:
    """Ask GPU LoRA for numerical prediction. CPU judge may force one redo."""
    import sys
    from pathlib import Path

    from lib.prt_cpu_judge import format_retry_block, judge_draft
    from lib.prt_pattern_frame import build_pattern_frame
    from lib.prt_scaffold_fade import (
        apply_prior_fill_policy,
        build_scaffold_spec,
        normalize_phase,
        self_emit_report,
    )

    viv = Path(__file__).resolve().parents[2]
    if str(viv) not in sys.path:
        sys.path.insert(0, str(viv))

    from voice_core.hf_lora import adapter_ready, generate as hf_generate

    if not adapter_ready():
        return {"ok": False, "excluded": True, "reason": "adapter_missing", "prediction": None}
    cfg = _load_prt_cfg()
    frame = build_pattern_frame(before, act, life_hint=life_hint, pulse_hint=pulse_hint)
    prior = frame.get("act_prior_after") or {}
    phase = normalize_phase(scaffold_phase)
    spec = build_scaffold_spec(prior, phase=phase, act=act, round_i=round_i)
    prompt = _predict_prompt(
        before, act, life_hint=life_hint, pulse_hint=pulse_hint, scaffold_spec=spec, round_i=round_i
    )
    max_tok = 80 if phase >= 2 else 64

    def _one_shot(
        prompt_text: str, *, apply_fill: bool = True
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str, dict[str, Any], dict[str, Any]]:
        """Returns (parsed_for_use, raw_parsed_before_fill, text, gen, emit)."""
        gen_local = hf_generate(prompt_text, max_new_tokens=max_tok, temperature=0.0)
        text_local = str(gen_local.get("text") or "")
        parse_blob = str(spec.get("completion_prefix") or "") + text_local
        raw_parsed = parse_prediction(parse_blob) or parse_prediction(text_local)
        parsed_local = raw_parsed
        if apply_fill and (not parsed_local or not parsed_local.get("triad_complete")):
            parsed_local = apply_prior_fill_policy(
                parsed_local or {"raw": text_local[:500], "parse": "empty"},
                prior,
                fillable=list(spec.get("fillable") or []),
            )
        emit_local = self_emit_report(parsed_local or {}, list(spec.get("blanked") or []))
        if parsed_local:
            parsed_local["scaffold_phase"] = phase
            parsed_local["scaffold_blanked"] = list(spec.get("blanked") or [])
            parsed_local["self_emit"] = emit_local
        return parsed_local, raw_parsed, text_local, gen_local, emit_local

    parsed, raw_parsed, text, gen, emit = _one_shot(prompt, apply_fill=True)
    cpu_judge: dict[str, Any] = {"enabled": False, "retried": False}
    if bool(cfg.get("cpu_judge_retry", True)):
        # Judge the GPU's raw draft (before prior_fill) so CPU teach actually fires
        draft_for_judge = raw_parsed if bool(cfg.get("cpu_judge_before_fill", True)) else parsed
        cpu_sample = (frame.get("cpu_sample") if isinstance(frame, dict) else None) or {}
        verdict = judge_draft(
            draft_for_judge,
            before=before,
            prior=prior,
            scaffold=spec,
            cpu_sample=cpu_sample if isinstance(cpu_sample, dict) else {},
            far_tol=float(cfg.get("cpu_judge_far_tol") or 0.05),
        )
        cpu_judge = {
            "enabled": True,
            "retried": False,
            "judged_before_fill": bool(cfg.get("cpu_judge_before_fill", True)),
            "first_reasons": list(verdict.get("reasons") or []),
            "hints": dict(verdict.get("hints") or {}),
        }
        if verdict.get("retry"):
            retry_prompt = prompt + format_retry_block(
                verdict, use_madlibs=bool(cfg.get("cpu_judge_madlibs", True))
            )
            parsed2, raw2, text2, gen2, emit2 = _one_shot(retry_prompt, apply_fill=True)
            cpu_judge["retried"] = True
            cpu_judge["second_ok"] = bool(parsed2 and parsed2.get("triad_complete"))
            if parsed2 is not None:
                parsed, text, gen, emit = parsed2, text2, gen2, emit2
                if isinstance(parsed, dict):
                    parsed["cpu_judge_retry"] = True
            _ = raw2  # judged path only
    if not parsed or (
        parsed.get("predicted_master_rsr") is None
        and parsed.get("predicted_master_s_n") is None
        and not parsed.get("triad_complete")
    ):
        if phase >= 2 and parsed and any(
            parsed.get(k) is not None
            for k in (
                "predicted_master_rsr",
                "predicted_master_ltp",
                "predicted_master_rle",
                "predicted_master_s_n",
            )
        ):
            parsed["triad_incomplete"] = True
        else:
            return {
                "ok": False,
                "excluded": True,
                "reason": "unparseable_prediction",
                "raw": text[:500],
                "prediction": None,
                "pattern_frame": frame,
                "scaffold": spec,
                "self_emit": emit,
                "cpu_judge": cpu_judge,
            }
    if not parsed.get("triad_complete"):
        parsed["triad_incomplete"] = True
    if act == "life" and "predicted_live_cells" not in parsed:
        parsed["life_pred_missing"] = True
    if act == "pulse" and "predicted_mean_load_pct" not in parsed:
        parsed["pulse_pred_missing"] = True
    return {
        "ok": True,
        "excluded": False,
        "reason": "OK",
        "raw": text[:500],
        "prediction": parsed,
        "mode": gen.get("mode"),
        "pattern_frame": frame,
        "scaffold": spec,
        "self_emit": emit,
        "cpu_judge": cpu_judge,
    }


def score_prediction(
    predicted: float,
    actual: float,
    *,
    reward_tol: float,
    punish_tol: float,
) -> dict[str, Any]:
    err = abs(float(predicted) - float(actual))
    if err <= reward_tol:
        label = "REWARD"
    elif err >= punish_tol:
        label = "PUNISH"
    else:
        label = "NEUTRAL"
    return {
        "error": round(err, 6),
        "label": label,
        "reward_tol": reward_tol,
        "punish_tol": punish_tol,
        "predicted": float(predicted),
        "actual": float(actual),
    }


def score_live_cells(predicted: int | None, actual: int) -> dict[str, Any] | None:
    if predicted is None:
        return None
    actual_i = max(0, int(actual))
    pred_i = max(0, int(predicted))
    denom = max(1, actual_i)
    frac = abs(pred_i - actual_i) / float(denom)
    if frac <= LIVE_REWARD_FRAC:
        label = "REWARD"
    elif frac >= LIVE_PUNISH_FRAC:
        label = "PUNISH"
    else:
        label = "NEUTRAL"
    return {
        "predicted": pred_i,
        "actual": actual_i,
        "frac_error": round(frac, 6),
        "label": label,
        "reward_frac": LIVE_REWARD_FRAC,
        "punish_frac": LIVE_PUNISH_FRAC,
    }


def combine_labels(sn_label: str, task_label: str | None) -> str:
    """Both teachers: PUNISH if either punishes; REWARD only if both reward (or task absent)."""
    if task_label is None:
        return sn_label
    if sn_label == "PUNISH" or task_label == "PUNISH":
        return "PUNISH"
    if sn_label == "REWARD" and task_label == "REWARD":
        return "REWARD"
    return "NEUTRAL"


def combine_channel_labels(labels: list[str]) -> str:
    """Stability triad: REWARD iff all reward; PUNISH if any punish."""
    if not labels:
        return "NEUTRAL"
    if any(x == "PUNISH" for x in labels):
        return "PUNISH"
    if all(x == "REWARD" for x in labels):
        return "REWARD"
    return "NEUTRAL"


def score_stability_triad(
    pred: dict[str, Any],
    after: dict[str, Any],
    *,
    reward_tol: float,
    punish_tol: float,
) -> dict[str, Any]:
    """Compare predicted vs measured RSR, LTP, RLE (the three stability channels)."""
    channels: dict[str, dict[str, Any]] = {}
    labels: list[str] = []
    triad_ok = bool(pred.get("triad_complete")) and all(
        pred.get(k) is not None
        for k in (
            "predicted_master_rsr",
            "predicted_master_ltp",
            "predicted_master_rle",
        )
    )
    if triad_ok:
        for key, ak in (
            ("rsr", "master_rsr"),
            ("ltp", "master_ltp"),
            ("rle", "master_rle"),
        ):
            sc = score_prediction(
                float(pred[f"predicted_master_{key}"]),
                float(after.get(ak) or 0.0),
                reward_tol=reward_tol,
                punish_tol=punish_tol,
            )
            channels[key] = sc
            labels.append(sc["label"])
        triad_label = combine_channel_labels(labels)
    else:
        # Incomplete: score composite S_n only (legacy / soft)
        sc = score_prediction(
            float(pred.get("predicted_master_s_n") or 0.0),
            float(after.get("master_s_n") or 0.0),
            reward_tol=reward_tol,
            punish_tol=punish_tol,
        )
        channels["s_n_only"] = sc
        triad_label = sc["label"]
        # Soft penalty: never full REWARD without triad commitment
        if triad_label == "REWARD":
            triad_label = "NEUTRAL"

    # Always also report composite S_n error for audits
    pred_sn = pred.get("predicted_master_s_n")
    if pred_sn is None and triad_ok:
        pred_sn = triad_s_n(
            float(pred["predicted_master_rsr"]),
            float(pred["predicted_master_ltp"]),
            float(pred["predicted_master_rle"]),
        )
    sn_score = score_prediction(
        float(pred_sn or 0.0),
        float(after.get("master_s_n") or 0.0),
        reward_tol=reward_tol,
        punish_tol=punish_tol,
    )
    return {
        "triad_complete": triad_ok,
        "channels": channels,
        "triad_label": triad_label,
        "sn_composite": sn_score,
        "label": triad_label,
        "error": sn_score["error"],
        "predicted": sn_score["predicted"],
        "actual": sn_score["actual"],
        "reward_tol": reward_tol,
        "punish_tol": punish_tol,
    }


def sandbox_gate(act: str, *, s_n: float, dormancy: float) -> dict[str, Any]:
    if any_halt_requested():
        return {"allowed": False, "reason": "halt.flag", "act": "observe"}
    if act not in ALLOWED_ACTS:
        return {"allowed": False, "reason": "act_not_allowlisted", "act": "observe"}
    if act == "speak" and s_n < dormancy:
        return {"allowed": False, "reason": "dormant_no_speak", "act": "observe"}
    if act == "life" and s_n < dormancy:
        # Life burns CPU — skip when dormant (protect host)
        return {"allowed": False, "reason": "dormant_no_life", "act": "observe"}
    if act == "pulse" and s_n < dormancy:
        # Pulse burns CPU — skip when dormant (protect host)
        return {"allowed": False, "reason": "dormant_no_pulse", "act": "observe"}
    return {"allowed": True, "reason": "OK", "act": act}


def execute_act(
    act: str,
    *,
    max_tokens: int,
    life_cfg: dict[str, Any] | None = None,
    pulse_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if act == "observe":
        return {"act": "observe", "ok": True, "spoke": False, "text": None}
    if act == "pulse":
        from lib.pulse_plant import run_pulse

        result = run_pulse(pulse_cfg or {})
        return {
            "act": "pulse",
            "ok": bool(result.get("ok")),
            "spoke": False,
            "veto": False,
            "pulse": result,
            "text": None,
        }
    if act == "life":
        cfg = life_cfg or {}
        result = run_life(
            generations=int(cfg.get("generations") or 24),
            rows=int(cfg.get("rows") or 48),
            cols=int(cfg.get("cols") or 48),
            pattern=cfg.get("pattern") or "random",
            density=float(cfg.get("density") or 0.35),
            seed=cfg.get("seed"),
        )
        return {
            "act": "life",
            "ok": bool(result.get("ok")),
            "spoke": False,
            "veto": False,
            "life": result,
            "text": None,
        }
    if act != "speak":
        return {"act": act, "ok": False, "spoke": False, "reason": "illegal", "veto": True}

    from lib.voice_bridge import speak as viv_speak

    sp = viv_speak("state summary", memory_top=1, max_tokens=max_tokens)
    blocked = bool(sp.get("blocked"))
    text = sp.get("text")
    if blocked:
        return {
            "act": "speak",
            "ok": False,
            "spoke": False,
            "veto": True,
            "reason": "security_out_blocked",
            "speak": {k: sp.get(k) for k in ("ok", "blocked", "voice_source", "silent")},
        }
    return {
        "act": "speak",
        "ok": bool(sp.get("ok")) and bool(text),
        "spoke": bool(text),
        "veto": False,
        "text": (text or "")[:280],
        "voice_source": sp.get("voice_source"),
        "speak": {k: sp.get(k) for k in ("ok", "blocked", "voice_source", "silent")},
    }


def append_cycle(row: dict[str, Any]) -> Path:
    PRT_CYCLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PRT_CYCLES_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return PRT_CYCLES_PATH


def wait_for_active(*, dormancy: float | None = None, timeout_s: float = 90.0, poll_s: float = 2.0) -> dict[str, Any]:
    """Poll Master S_n until ACTIVE or timeout (for speak collect after GPU cool-down)."""
    import time as _time

    cfg = _load_prt_cfg()
    floor = float(dormancy if dormancy is not None else cfg["dormancy_threshold"])
    t0 = _time.time()
    last = observe_state()
    while float(last["master_s_n"]) < floor:
        if _time.time() - t0 >= timeout_s:
            return {"ok": False, "reason": "active_timeout", "last": last, "waited_s": _time.time() - t0}
        _time.sleep(poll_s)
        last = observe_state()
    return {"ok": True, "reason": "OK", "last": last, "waited_s": _time.time() - t0}


def run_cycle(
    *,
    act: str = "speak",
    settle_s: float | None = None,
    skip_model_predict: bool = False,
    wait_active: bool = True,
    life_round: int = 0,
    scaffold_phase: int | None = None,
    cpu_hold: bool = False,
) -> dict[str, Any]:
    """One PRT cycle. Physics grades prediction; allowlist + Security contain ACT."""
    cfg = _load_prt_cfg()
    dormancy = float(cfg["dormancy_threshold"])
    # Stage ladder defaults; optional override for curriculum experiments (e.g. tol widen)
    try:
        from lib.prt_stage import current_run_params

        stage_params = current_run_params()
    except Exception:  # noqa: BLE001
        stage_params = {}
    reward_tol = float(
        cfg.get("reward_tol_override")
        if cfg.get("reward_tol_override") is not None
        else stage_params.get("reward_tol", cfg["reward_tol"])
    )
    punish_tol = float(
        cfg.get("punish_tol_override")
        if cfg.get("punish_tol_override") is not None
        else stage_params.get("punish_tol", cfg["punish_tol"])
    )
    settle = float(settle_s if settle_s is not None else cfg["settle_s"])
    max_tok = int(cfg["speak_max_tokens"])
    from lib.prt_scaffold_fade import normalize_phase

    # RID mastery (and explicit cfg) must win over stage-ladder phase so we can
    # drill full-scaffold triad math before re-fading blanks.
    if scaffold_phase is not None:
        _phase_raw = scaffold_phase
    elif cfg.get("rid_mastery_mode") and cfg.get("scaffold_phase") is not None:
        _phase_raw = cfg.get("scaffold_phase")
    else:
        _phase_raw = stage_params.get("scaffold_phase", cfg.get("scaffold_phase", 1))
    phase = normalize_phase(_phase_raw)

    cycle: dict[str, Any] = {
        "_type": "prt_cycle",
        "version": "0.6.0",
        "timestamp": _utc(),
        "student": "openaster_base+lora",
        "teacher": "stability_triad_rsr_ltp_rle",
        "scaffold_phase": phase,
        "reward_tol": reward_tol,
        "punish_tol": punish_tol,
        "experiment": cfg.get("experiment_id"),
    }

    if any_halt_requested():
        cycle.update({"ok": False, "excluded": True, "reason": "halt.flag"})
        append_cycle(cycle)
        return cycle

    if act in ("speak", "life") and wait_active:
        w = wait_for_active(dormancy=dormancy, timeout_s=90.0)
        cycle["wait_active"] = {"ok": w.get("ok"), "reason": w.get("reason"), "waited_s": w.get("waited_s")}
        if not w.get("ok"):
            cycle.update(
                {
                    "ok": False,
                    "excluded": True,
                    "reason": f"{act}_skipped_dormant",
                    "acted": False,
                }
            )
            append_cycle(cycle)
            return cycle

    before = observe_state()
    from lib.prt_pattern_frame import build_pattern_frame, enrich_observe

    before = enrich_observe(before)
    _obs_keys = (
        "timestamp",
        "master_s_n",
        "master_rsr",
        "master_ltp",
        "master_rle",
        "plant_s_n",
        "status",
        "cpu_load_pct",
        "cpu_temp_c",
        "gpu_temp_c",
        "cpu_package_c",
        "coolant_c",
        "pkg_minus_coolant_c",
        "gpu_util_pct",
        "gpu_vram_free_frac",
        "norm_rsr",
        "norm_ltp",
        "norm_rle",
        "norm_s_n",
        "norm_gpu_rle",
        "norm_cool_rle",
    )
    cycle["observe_before"] = {k: before[k] for k in _obs_keys if k in before}

    gate = sandbox_gate(act, s_n=float(before["master_s_n"]), dormancy=dormancy)
    planned = gate["act"]
    cycle["sandbox"] = gate

    # Prepare life board BEFORE predict so she sees before-state (honest task)
    life_cfg: dict[str, Any] | None = None
    life_hint: dict[str, Any] | None = None
    pulse_cfg: dict[str, Any] | None = None
    pulse_hint: dict[str, Any] | None = None
    if planned == "pulse":
        from lib.pulse_plant import peek_before as pulse_peek, pick_pulse_level

        pulse_cfg = pick_pulse_level(life_round)
        pulse_hint = {"before": pulse_peek(pulse_cfg)}
        cycle["pulse_plan"] = {**pulse_cfg, "before": pulse_hint["before"]}
    if planned == "life":
        from lib.conway_plant import peek_before

        pattern = pick_pressure_pattern(life_round)
        life_cfg = {
            "generations": int(cfg.get("life_generations") or 24),
            "rows": int(cfg.get("life_rows") or 48),
            "cols": int(cfg.get("life_cols") or 48),
            "pattern": pattern,
            "density": 0.35,
            "seed": int(time.time() * 1000) % 1_000_000,
        }
        life_hint = {
            "generations": life_cfg["generations"],
            "before": peek_before(
                rows=int(life_cfg["rows"]),
                cols=int(life_cfg["cols"]),
                pattern=pattern,
                density=0.35,
                seed=life_cfg["seed"],
            ),
        }
        cycle["life_plan"] = {**life_cfg, "before": life_hint["before"]}

    cycle["pattern_frame"] = build_pattern_frame(
        before, planned, life_hint=life_hint, pulse_hint=pulse_hint
    )

    # Prediction (required for trainability)
    if cpu_hold:
        from lib.prt_cpu_teacher import cpu_hold_prediction

        hold = cpu_hold_prediction(before)
        if not hold.get("ok"):
            pred_pack = {
                "ok": False,
                "excluded": True,
                "reason": hold.get("reason") or "cpu_hold_failed",
                "prediction": None,
                "scaffold": {"phase": phase, "blanked": [], "note": "cpu_hold"},
                "self_emit": {"self_emit_ok": True, "note": "cpu_hold"},
                "cpu_judge": {"enabled": False, "note": "cpu_hold_no_gpu"},
            }
        else:
            pred_pack = {
                "ok": True,
                "excluded": False,
                "reason": "cpu_hold",
                "prediction": hold["prediction"],
                "scaffold": {"phase": phase, "blanked": [], "note": "cpu_hold no GPU"},
                "self_emit": {"self_emit_ok": True, "note": "cpu_hold"},
                "cpu_judge": {"enabled": False, "note": "cpu_hold_no_gpu"},
            }
    elif skip_model_predict:
        # Act-prior scaffold as baseline (not raw hold) — tests representation path
        prior = dict((cycle["pattern_frame"] or {}).get("act_prior_after") or {})
        hold_live = prior.get("predicted_live_cells")
        if hold_live is None and life_hint:
            hold_live = int((life_hint.get("before") or {}).get("live_cells") or 0)
        pred_pack = {
            "ok": True,
            "excluded": False,
            "reason": "act_prior_baseline",
            "prediction": {
                "predicted_master_rsr": float(prior.get("predicted_master_rsr", before["master_rsr"])),
                "predicted_master_ltp": float(prior.get("predicted_master_ltp", before["master_ltp"])),
                "predicted_master_rle": float(prior.get("predicted_master_rle", before["master_rle"])),
                "predicted_master_s_n": float(prior.get("predicted_master_s_n", before["master_s_n"])),
                "confidence": "medium",
                "raw": "act_prior",
                "parse": "baseline",
                "triad_complete": True,
                **({"predicted_live_cells": int(hold_live)} if hold_live is not None else {}),
            },
            "scaffold": {"phase": phase, "blanked": [], "note": "baseline bypasses fade"},
            "self_emit": {"self_emit_ok": False, "note": "baseline"},
        }
    else:
        pred_pack = model_predict(
            before,
            planned,
            life_hint=life_hint,
            pulse_hint=pulse_hint,
            scaffold_phase=phase,
            round_i=life_round,
        )
    cycle["predict"] = pred_pack
    cycle["scaffold"] = pred_pack.get("scaffold")
    cycle["self_emit"] = pred_pack.get("self_emit") or (pred_pack.get("prediction") or {}).get("self_emit")
    cycle["cpu_judge"] = pred_pack.get("cpu_judge") or {"enabled": False}

    if pred_pack.get("excluded") or not pred_pack.get("prediction"):
        cycle.update({"ok": False, "excluded": True, "reason": pred_pack.get("reason"), "acted": False})
        append_cycle(cycle)
        return cycle

    if not gate.get("allowed") and act in ("speak", "life", "pulse"):
        cycle["requested_act"] = act
        planned = "observe"
        life_cfg = None
        pulse_cfg = None

    act_result = execute_act(planned, max_tokens=max_tok, life_cfg=life_cfg, pulse_cfg=pulse_cfg)
    cycle["act"] = act_result

    if act_result.get("veto"):
        cycle["quality_multiplier"] = 0.5

    time.sleep(max(0.5, settle))
    after = enrich_observe(observe_state())
    cycle["observe_after"] = {k: after[k] for k in _obs_keys if k in after}

    triad_score = score_stability_triad(
        pred_pack["prediction"],
        after,
        reward_tol=reward_tol,
        punish_tol=punish_tol,
    )

    task_score = None
    if planned == "life" and (act_result.get("life") or {}).get("after"):
        live_after = int(act_result["life"]["after"]["live_cells"])
        pred_live = pred_pack["prediction"].get("predicted_live_cells")
        task_score = score_live_cells(pred_live, live_after)
    elif planned == "pulse" and (act_result.get("pulse") or {}).get("ok"):
        from lib.pulse_plant import score_mean_load

        task_score = score_mean_load(
            pred_pack["prediction"].get("predicted_mean_load_pct"),
            float(act_result["pulse"]["mean_load_pct"]),
        )

    combined = combine_labels(triad_score["label"], (task_score or {}).get("label"))
    # Phase 2+: structure ownership — strict gates REWARD; soft logs only (curriculum)
    emit = cycle.get("self_emit") or {}
    blanked = list((cycle.get("scaffold") or {}).get("blanked") or [])
    structure_ok = True
    gate_mode = str(cfg.get("structure_gate_mode") or "strict").lower()
    if phase >= 2 and blanked:
        structure_ok = bool(emit.get("self_emit_ok") or emit.get("all_blanked_self_emitted"))
        if gate_mode == "strict":
            if not structure_ok and combined == "REWARD":
                combined = "NEUTRAL"
            if not structure_ok and not pred_pack["prediction"].get("triad_complete"):
                combined = "PUNISH"
        # soft / off: keep physics label; self_emit still logged for stage metrics

    # CPU script sample trust balance (~50/50 follow vs adapt)
    trust: dict[str, Any] = {"ok": False, "mode": "off"}
    cpu_sample = (cycle.get("pattern_frame") or {}).get("cpu_sample")
    if cfg.get("cpu_sample", True) and cpu_sample:
        from lib.prt_cpu_sample import apply_trust_to_combined, rolling_follow_rate, score_trust_balance

        trust = score_trust_balance(pred_pack["prediction"], cpu_sample, after)
        soft = bool(cfg.get("trust_soft_punish", False))
        trust["soft_punish"] = soft
        combined = apply_trust_to_combined(combined, trust, soft_punish=soft)
        trust["rolling"] = rolling_follow_rate()

    cycle["score"] = {
        **triad_score,
        "label": combined,
        "stability_label": triad_score["label"],
        "task_score": task_score,
        "structure_ok": structure_ok,
        "structure_gate_mode": gate_mode,
        "scaffold_phase": phase,
        "trust": trust,
    }
    cycle["cpu_sample"] = cpu_sample
    cycle["ok"] = True
    cycle["excluded"] = False
    # Trainable on REWARD/NEUTRAL only when structure owned (phase 2+) or phase 1
    train_ok = combined in ("REWARD", "NEUTRAL") and not act_result.get("veto")
    if phase >= 2 and blanked and not structure_ok:
        train_ok = False
    cycle["trainable"] = train_ok
    cycle["teacher"] = {
        "life": "stability_triad_rsr_ltp_rle+conway_live_cells",
        "pulse": "stability_triad_rsr_ltp_rle+pulse_mean_load",
    }.get(planned, "stability_triad_rsr_ltp_rle")

    append_cycle(cycle)
    return cycle


def collect(
    *,
    cycles: int = 3,
    act: str = "speak",
    settle_s: float | None = None,
    skip_model_predict: bool = False,
    cpu_hold: bool = False,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for i in range(max(1, cycles)):
        if any_halt_requested():
            break
        row = run_cycle(
            act=act,
            settle_s=settle_s,
            skip_model_predict=skip_model_predict,
            life_round=i,
            cpu_hold=cpu_hold,
        )
        rows.append(row)
        print(
            f"[prt {i+1}/{cycles}] act={row.get('act', {}).get('act')} "
            f"score={row.get('score', {}).get('label', row.get('reason'))} "
            f"err={row.get('score', {}).get('error')} excluded={row.get('excluded')}"
        )
        # Free GPU between speak cycles so Master S_n can recover for next allowlist gate
        if act == "speak":
            try:
                import sys
                from pathlib import Path

                viv = Path(__file__).resolve().parents[2]
                if str(viv) not in sys.path:
                    sys.path.insert(0, str(viv))
                from voice_core.hf_lora import unload

                unload()
                time.sleep(3.0)
            except Exception:  # noqa: BLE001
                pass
        elif act == "life":
            time.sleep(1.0)
    summary = {
        "timestamp": _utc(),
        "cycles_requested": cycles,
        "cycles_run": len(rows),
        "reward": sum(1 for r in rows if (r.get("score") or {}).get("label") == "REWARD"),
        "neutral": sum(1 for r in rows if (r.get("score") or {}).get("label") == "NEUTRAL"),
        "punish": sum(1 for r in rows if (r.get("score") or {}).get("label") == "PUNISH"),
        "excluded": sum(1 for r in rows if r.get("excluded")),
        "trainable": sum(1 for r in rows if r.get("trainable")),
        "spoke": sum(1 for r in rows if (r.get("act") or {}).get("spoke")),
        "life": sum(1 for r in rows if (r.get("act") or {}).get("act") == "life"),
        "cycles_path": str(PRT_CYCLES_PATH).replace("\\", "/"),
        "contract": "PRT_BASE_MODEL_CONTRACT.md",
        "voice_speak_still_halted": True,
    }
    PRT_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRT_SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def ensure_pre_prt_backup() -> Path | None:
    """One-time copy of fluency adapter before PRT weight updates."""
    import shutil

    src = FOUNDATION_ROOT / "models" / "gpu" / "viv_voice_lora"
    dst = FOUNDATION_ROOT / "models" / "gpu" / "viv_voice_lora_pre_prt"
    marker = dst / "adapter_config.json"
    if marker.is_file():
        return dst
    if not (src / "adapter_config.json").is_file():
        return None
    dst.mkdir(parents=True, exist_ok=True)
    for name in (
        "adapter_config.json",
        "adapter_model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json",
        "chat_template.jinja",
        "viv_train_meta.json",
        "README.md",
    ):
        p = src / name
        if p.is_file():
            shutil.copy2(p, dst / name)
    meta = {"copied_at": _utc(), "note": "fluency scaffold before PRT promote"}
    (dst / "backup_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return dst
