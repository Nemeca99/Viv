#!/usr/bin/env python3
"""Ledger control protocol v2: settled baseline + generate-locked integration.

Separates:
  E_generate = ∫_{t_request}^{t_done} P(t) dt
  E_tail     = ∫_{t_done}^{t_done+τ} P(t) dt

E_net = E_generate - P_idle_stable * Δt_generate

Cold-first and warm-repeat are distinct cells. Learning stays withheld.
"""
from __future__ import annotations

import json
import math
import statistics
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_capture import SessionCapture
from lib.rid_electrical_outcomes import board_power_w, integrate_energy_j

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
CAMPAIGN_DIR = OUT_DIR / "ledger_campaign"
SESSIONS = OUT_DIR / "sessions"

# --- Control gates (v2) ---
CV_E_MAX = 0.20
CV_P_MAX = 0.15
CV_IDLE_MAX = 0.10
CV_E_GENERATE_MAX = 0.20
INTEGRATION_WALL_RATIO_LO = 0.85
INTEGRATION_WALL_RATIO_HI = 1.25
SNR_NET_MIN = 3.0
E_RESOLUTION_FLOOR_J = 5.0
MIN_SAMPLES_PEAK_CONFIDENT = 8
IDLE_SLOPE_EPS_W_PER_S = 2.0
SETTLE_WINDOW_S = 8.0
SETTLE_TIMEOUT_S = 120.0
TAIL_TAU_S = 3.0
GPU_TEMP_MIN_C = 30.0
GPU_TEMP_MAX_C = 75.0
CADENCE_S = 0.5  # settle / tail cadence
GENERATE_CADENCE_S = 0.1  # dense sampling during generate lock
NUM_PREDICT_SHORT = 64
DEFAULT_MODEL = "viv-voice-qwen"
PROMPT = (
    "Explain liquid-cooled CPU and GPU power draw for a local agent in clear prose. "
    "Include thermal and electrical considerations."
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _gpu_temp() -> float | None:
    try:
        from lib.gpu_plant import read_gpu

        return float(read_gpu(0).temp_c)
    except Exception:  # noqa: BLE001
        return None


def _finite_slope(times: list[float], vals: list[float]) -> float | None:
    n = min(len(times), len(vals))
    if n < 3:
        return None
    t0 = times[0]
    xs = [times[i] - t0 for i in range(n)]
    ys = vals[:n]
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den < 1e-12:
        return 0.0
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / den


@dataclass(frozen=True)
class ControlCell:
    cell_id: str
    residency: str  # cold_first | warm_repeat
    num_predict: int = NUM_PREDICT_SHORT
    model: str = DEFAULT_MODEL
    token_bucket: str = "tokens_short"
    prompt: str | None = None  # override default PROMPT when set

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def settle_baseline(
    record: Callable[[str], dict[str, Any]],
    *,
    cadence_s: float = CADENCE_S,
    settle_s: float = SETTLE_WINDOW_S,
    timeout_s: float = SETTLE_TIMEOUT_S,
) -> dict[str, Any]:
    """Wait until idle power/temp gates pass for a continuous settle_s window."""
    t0 = time.perf_counter()
    buf: list[dict[str, Any]] = []
    while time.perf_counter() - t0 < timeout_s:
        sample = record("baseline_settle")
        buf.append(sample)
        # keep last settle_s worth
        mono = float(sample.get("mono_s") or 0.0)
        buf = [s for s in buf if mono - float(s.get("mono_s") or 0.0) <= settle_s + 0.5]
        powers = []
        times = []
        for s in buf:
            pw = board_power_w(s)
            m = s.get("mono_s")
            if pw is None or m is None:
                continue
            powers.append(float(pw))
            times.append(float(m))
        gpu_t = _gpu_temp()
        ok_temp = gpu_t is None or (GPU_TEMP_MIN_C <= gpu_t <= GPU_TEMP_MAX_C)
        if len(powers) >= max(4, int(settle_s / max(cadence_s, 0.1))):
            span = times[-1] - times[0]
            if span >= settle_s * 0.9:
                mu = statistics.fmean(powers)
                cv = (statistics.pstdev(powers) / abs(mu)) if abs(mu) > 1e-6 else None
                slope = _finite_slope(times, powers)
                slope_ok = slope is not None and abs(slope) <= IDLE_SLOPE_EPS_W_PER_S
                cv_ok = cv is not None and cv <= CV_IDLE_MAX
                if slope_ok and cv_ok and ok_temp:
                    return {
                        "ok": True,
                        "P_idle_stable_w": mu,
                        "CV_P_idle": cv,
                        "slope_P_idle_w_per_s": slope,
                        "gpu_temp_c": gpu_t,
                        "settle_s": span,
                        "n_samples": len(powers),
                        "elapsed_s": time.perf_counter() - t0,
                        "gates": {
                            "CV_IDLE_MAX": CV_IDLE_MAX,
                            "IDLE_SLOPE_EPS_W_PER_S": IDLE_SLOPE_EPS_W_PER_S,
                            "GPU_TEMP_MIN_C": GPU_TEMP_MIN_C,
                            "GPU_TEMP_MAX_C": GPU_TEMP_MAX_C,
                        },
                    }
        time.sleep(cadence_s)
    # Failed settle — still report last stats
    powers = [float(board_power_w(s)) for s in buf if board_power_w(s) is not None]
    mu = statistics.fmean(powers) if powers else None
    cv = (
        statistics.pstdev(powers) / abs(mu)
        if mu is not None and len(powers) > 1 and abs(mu) > 1e-6
        else None
    )
    return {
        "ok": False,
        "P_idle_stable_w": mu,
        "CV_P_idle": cv,
        "gpu_temp_c": _gpu_temp(),
        "n_samples": len(powers),
        "elapsed_s": time.perf_counter() - t0,
        "error": "settle_timeout",
    }


def ollama_generate_timed(
    *,
    model: str,
    num_predict: int,
    prompt: str = PROMPT,
    timeout_s: float = 300.0,
) -> dict[str, Any]:
    """Streamed generate with request/first/final timing + Ollama duration fields."""
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {"num_predict": int(num_predict)},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t_request = time.perf_counter()
    t_request_wall = time.time()
    t_first = None
    t_final = None
    raw_final: dict[str, Any] = {}
    err = None
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if t_first is None:
                    t_first = time.perf_counter()
                t_final = time.perf_counter()
                if chunk.get("done"):
                    raw_final = chunk
                    break
                raw_final = chunk
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        err = str(exc)
    t_done = time.perf_counter()
    out_tok = raw_final.get("eval_count")
    in_tok = raw_final.get("prompt_eval_count")
    total = None
    if isinstance(out_tok, int) or isinstance(in_tok, int):
        total = int(out_tok or 0) + int(in_tok or 0)

    def _ns_to_s(v: Any) -> float | None:
        if v is None:
            return None
        try:
            return float(v) / 1e9
        except (TypeError, ValueError):
            return None

    return {
        "ok": err is None and bool(raw_final),
        "error": err,
        "model": model,
        "num_predict": num_predict,
        "prompt_eval_count": in_tok,
        "eval_count": out_tok,
        "token_count_total": total,
        "t_request_mono": t_request,
        "t_first_token_mono": t_first,
        "t_final_token_mono": t_final,
        "t_done_mono": t_done,
        "t_request_unix": t_request_wall,
        "wall_s": t_done - t_request,
        "ttft_s": (t_first - t_request) if t_first is not None else None,
        "total_duration_s": _ns_to_s(raw_final.get("total_duration")),
        "load_duration_s": _ns_to_s(raw_final.get("load_duration")),
        "prompt_eval_duration_s": _ns_to_s(raw_final.get("prompt_eval_duration")),
        "eval_duration_s": _ns_to_s(raw_final.get("eval_duration")),
        "done_reason": raw_final.get("done_reason"),
    }


def _energy_from_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    times, powers = [], []
    for s in samples:
        pw = board_power_w(s)
        m = s.get("mono_s")
        if pw is None or m is None:
            continue
        times.append(float(m))
        powers.append(float(pw))
    integ = integrate_energy_j(times, powers)
    peak = max(powers) if powers else None
    mean = statistics.fmean(powers) if powers else None
    return {
        "E_j": integ.get("E_j"),
        "duration_s": integ.get("duration_s"),
        "P_mean_w": mean,
        "P_peak_w": peak,
        "n": len(powers),
        "integration": integ,
    }


def ensure_model_residency(cell: ControlCell) -> dict[str, Any]:
    """Cold-first: best-effort unload. Warm-repeat: discard warmup generate."""
    if cell.residency == "cold_first":
        # Best-effort: ask Ollama to unload by generating with keep_alive=0 after a noop
        try:
            body = json.dumps(
                {
                    "model": cell.model,
                    "keep_alive": 0,
                    "prompt": ".",
                    "stream": False,
                    "options": {"num_predict": 1},
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp.read()
            time.sleep(2.0)
            return {"mode": "cold_first", "unload_attempted": True}
        except Exception as exc:  # noqa: BLE001
            return {"mode": "cold_first", "unload_attempted": True, "error": str(exc)}
    # warm_repeat: one discarded generate to load/reside model
    warm = ollama_generate_timed(
        model=cell.model,
        num_predict=max(16, cell.num_predict // 4),
        prompt=str(cell.prompt) if cell.prompt else PROMPT,
        timeout_s=180.0,
    )
    time.sleep(1.0)
    return {"mode": "warm_repeat", "warmup": warm}


def _lock_samples_to_window(
    samples: list[dict[str, Any]],
    *,
    t0_mono: float,
    t_lo_abs: float,
    t_hi_abs: float,
) -> list[dict[str, Any]]:
    """Keep samples whose absolute perf time falls in [t_lo, t_hi]."""
    out: list[dict[str, Any]] = []
    for s in samples:
        m = s.get("mono_s")
        if m is None:
            continue
        abs_t = float(t0_mono) + float(m)
        if t_lo_abs <= abs_t <= t_hi_abs:
            out.append(s)
    return out


def run_controlled_v2(
    cell: ControlCell,
    *,
    repeat_i: int,
    cadence_s: float = CADENCE_S,
    generate_cadence_s: float = GENERATE_CADENCE_S,
    tail_tau_s: float = TAIL_TAU_S,
    prep_residency: bool = True,
    pre_inference_hook: Callable[[dict[str, Any]], Any] | None = None,
    plant_config_id: str | None = None,
) -> dict[str, Any]:
    """One controlled action under v2 protocol.

    Optional ``pre_inference_hook`` runs after settle and immediately before
    generate sampling/inference. Hook failures never block inference; callers
    must treat ``snapshot_hook_failed`` as training-ineligible.
    """
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    session_id = f"ctrl2_{cell.cell_id}_r{repeat_i}_{_utc_stamp()}"
    session_dir = SESSIONS / session_id
    if prep_residency:
        residency = ensure_model_residency(cell)
    else:
        residency = {"mode": cell.residency, "warmup_skipped": True}

    meta = {
        "session_id": session_id,
        "workload": "ledger_ctrl_v2",
        "experiment": "rid_electrical_ledger_controls_v2",
        "protocol": "stable_baseline+generate_locked+cold_warm_split",
        "cell": cell.to_dict(),
        "repeat_i": repeat_i,
        "residency_prep": dict(residency),
        "forensic_legacy_campaign": False,
        "learning_admission": False,
        "started_at": _utc(),
    }
    # Don't dump huge warmup into meta twice
    if "warmup" in residency:
        w = residency["warmup"]
        meta["residency_prep"]["warmup"] = {
            "ok": w.get("ok"),
            "token_count_total": w.get("token_count_total"),
            "wall_s": w.get("wall_s"),
            "load_duration_s": w.get("load_duration_s"),
        }

    cap = SessionCapture(session_dir, meta)
    cap.open()

    def record(phase: str, *, cadence: float | None = None) -> dict[str, Any]:
        return cap.record(
            workload="ledger_ctrl_v2",
            phase=phase,
            cadence_s=float(cadence if cadence is not None else cadence_s),
            session_id=session_id,
        )

    settle = settle_baseline(record, cadence_s=cadence_s)
    P_idle = settle.get("P_idle_stable_w")

    action_id = f"{session_id}::generate"
    snapshot_hook_failed = False
    pre_inference_hook_result: Any = None
    pre_hook_wall = _utc()
    pre_hook_mono = time.perf_counter()
    if pre_inference_hook is not None:
        hook_ctx = {
            "settle": settle,
            "gpu_temp_c": settle.get("gpu_temp_c"),
            "P_idle_stable_w": settle.get("P_idle_stable_w"),
            "session_id": session_id,
            "action_id": action_id,
            "cell": cell.to_dict(),
            "repeat_i": repeat_i,
            "plant_config_id": plant_config_id,
            "wall_time": pre_hook_wall,
            "mono_s": pre_hook_mono,
        }
        try:
            pre_inference_hook_result = pre_inference_hook(hook_ctx)
            if pre_inference_hook_result is False:
                snapshot_hook_failed = True
        except Exception as exc:  # noqa: BLE001
            snapshot_hook_failed = True
            pre_inference_hook_result = {"ok": False, "error": str(exc)}

    # Bookend + dense generate sampling locked to request→done.
    generate_raw: list[dict[str, Any]] = []
    stop = threading.Event()

    def _sampler() -> None:
        while not stop.is_set():
            generate_raw.append(record("generate", cadence=generate_cadence_s))
            time.sleep(generate_cadence_s)

    generate_raw.append(record("generate_pre", cadence=generate_cadence_s))
    th_s = threading.Thread(target=_sampler, daemon=True)
    th_s.start()
    inference_request_at = _utc()
    inference_request_mono = time.perf_counter()
    infer = ollama_generate_timed(
        model=cell.model,
        num_predict=cell.num_predict,
        prompt=str(cell.prompt) if cell.prompt else PROMPT,
        timeout_s=300.0,
    )
    infer = dict(infer)
    infer["inference_request_at"] = inference_request_at
    infer["inference_request_mono"] = inference_request_mono
    stop.set()
    th_s.join(timeout=2.0)
    generate_raw.append(record("generate_post", cadence=generate_cadence_s))

    t_req = float(infer.get("t_request_mono") or 0.0)
    t_done = float(infer.get("t_done_mono") or t_req)
    locked = _lock_samples_to_window(
        generate_raw,
        t0_mono=cap.t0_mono,
        t_lo_abs=t_req,
        t_hi_abs=t_done,
    )
    # If lock is too sparse (cadence edge), fall back to all generate_* samples
    # but still report ratio so the gate fails when windowing is wrong.
    gen_for_energy = locked if len(locked) >= 2 else generate_raw
    gen_energy = _energy_from_samples(gen_for_energy)

    # Tail window (diagnostic only — never folded into E_net)
    tail_samples: list[dict[str, Any]] = []
    t_tail_end = time.perf_counter() + float(tail_tau_s)
    while time.perf_counter() < t_tail_end:
        tail_samples.append(record("tail"))
        time.sleep(cadence_s)
    tail_energy = _energy_from_samples(tail_samples)

    dt_gen = gen_energy.get("duration_s")
    # Matched generate wall: request→done (same interval as E_generate lock)
    dt_generate = max(0.0, t_done - t_req)
    dt_ollama = infer.get("total_duration_s") or infer.get("wall_s") or dt_generate
    E_generate = gen_energy.get("E_j")
    E_tail = tail_energy.get("E_j")
    E_net_raw = None
    if E_generate is not None and P_idle is not None and dt_generate > 0:
        E_net_raw = float(E_generate) - float(P_idle) * float(dt_generate)

    # Single-shot baseline/subtraction uncertainty from idle CV.
    cv_idle = settle.get("CV_P_idle")
    sigma_sub_est = None
    if P_idle is not None and cv_idle is not None and dt_generate > 0:
        sigma_sub_est = abs(float(P_idle) * float(cv_idle) * float(dt_generate))
    snr_net = None
    if E_net_raw is not None and sigma_sub_est is not None and float(sigma_sub_est) > 0:
        snr_net = abs(float(E_net_raw)) / float(sigma_sub_est)
    below_res_single = (
        E_net_raw is not None
        and (
            abs(float(E_net_raw)) < E_RESOLUTION_FLOOR_J
            or (
                snr_net is not None
                and float(snr_net) < SNR_NET_MIN
            )
        )
    )
    # Authoritative net is withheld when below meter/subtraction resolution.
    E_net_auth = None if below_res_single else E_net_raw

    n_locked = len(locked) if locked else len(gen_for_energy)
    peak_confident = (
        n_locked >= MIN_SAMPLES_PEAK_CONFIDENT and dt_generate >= 2.0
    )
    P_mean_from_E = None
    if E_generate is not None and dt_generate > 0:
        P_mean_from_E = float(E_generate) / float(dt_generate)

    ratio = None
    if dt_gen and dt_ollama and float(dt_ollama) > 0:
        ratio = float(dt_gen) / float(dt_ollama)

    control_gates = {
        "settle_ok": bool(settle.get("ok")),
        "CV_P_idle": settle.get("CV_P_idle"),
        "CV_P_idle_ok": (
            settle.get("CV_P_idle") is not None
            and float(settle["CV_P_idle"]) <= CV_IDLE_MAX
        ),
        "integration_wall_ratio": ratio,
        "integration_wall_ratio_ok": (
            ratio is not None
            and INTEGRATION_WALL_RATIO_LO <= ratio <= INTEGRATION_WALL_RATIO_HI
        ),
        "sigma_baseline_subtraction_est_j": sigma_sub_est,
        "net_below_resolution_single": below_res_single,
        "gates": {
            "CV_IDLE_MAX": CV_IDLE_MAX,
            "INTEGRATION_WALL_RATIO_LO": INTEGRATION_WALL_RATIO_LO,
            "INTEGRATION_WALL_RATIO_HI": INTEGRATION_WALL_RATIO_HI,
            "CV_E_MAX": CV_E_MAX,
            "CV_P_MAX": CV_P_MAX,
            "SNR_NET_MIN": SNR_NET_MIN,
            "E_RESOLUTION_FLOOR_J": E_RESOLUTION_FLOOR_J,
            "MIN_SAMPLES_PEAK_CONFIDENT": MIN_SAMPLES_PEAK_CONFIDENT,
        },
    }

    temps = {
        "gpu_temp_c_end": _gpu_temp(),
        "gpu_temp_c_settle": settle.get("gpu_temp_c"),
    }

    row = {
        "ok": bool(settle.get("ok")) and bool(infer.get("ok")) and E_generate is not None,
        "action_id": action_id,
        "action_type": "controlled_generate_v2",
        "session_id": session_id,
        "cell": cell.to_dict(),
        "repeat_i": repeat_i,
        "SNR_net": snr_net,
        "sigma_baseline_subtraction_j": sigma_sub_est,
        "snapshot_hook_failed": bool(snapshot_hook_failed),
        "pre_inference_hook_result": pre_inference_hook_result,
        "pre_inference_hook_at": pre_hook_wall,
        "pre_inference_hook_mono": pre_hook_mono,
        "inference_request_at": inference_request_at,
        "inference_request_mono": inference_request_mono,
        "token_count": infer.get("token_count_total"),
        "model": cell.model,
        "residency": cell.residency,
        # Tiered accounting
        "E_action_immediate_j": E_generate,
        "E_generate_j": E_generate,
        "E_post_action_j": E_tail,
        "E_tail_j": E_tail,
        "E_session_consequence_j": (
            (float(E_generate) + float(E_tail))
            if E_generate is not None and E_tail is not None
            else None
        ),
        "E_net_raw_j": E_net_raw,
        "E_net_j": E_net_auth,
        "net_attribution": (
            "below_resolution" if below_res_single else "provisional_raw"
        ),
        "P_idle_stable_w": P_idle,
        "P_mean_generate_w": gen_energy.get("P_mean_w"),
        "P_mean_from_E_w": P_mean_from_E,
        "P_peak_generate_w": gen_energy.get("P_peak_w"),
        "P_peak_confidence": "high" if peak_confident else "low",
        "delta_t_generate_s": dt_generate,
        "delta_t_integration_s": dt_gen,
        "delta_t_ollama_s": dt_ollama,
        "n_generate_locked_samples": n_locked,
        "used_locked_window": len(locked) >= 2,
        "E_net_per_generate_s": (
            (float(E_net_auth) / float(dt_generate))
            if E_net_auth is not None and dt_generate > 0
            else None
        ),
        "settle": settle,
        "infer": infer,
        "generate_energy": gen_energy,
        "tail_energy": tail_energy,
        "control_gates": control_gates,
        "temperatures": temps,
        "provenance": {
            "protocol": "rid_electrical_ledger_controls_v2",
            "tokens": "ollama_/api/generate_stream",
            "power": "HWiNFO+NVML",
        },
        "authority": "control_validation_only",
        "enters_A_t": False,
        "enters_master_s_n": False,
        "predictor_operational": False,
        "learning_admission": False,
    }

    # close capture; load unused samples only if needed later
    cap.close(
        protocol="controls_v2",
        cell=cell.to_dict(),
        control_gates=control_gates,
    )
    # Attach human summary
    row["human_summary"] = (
        f"{cell.cell_id} r{repeat_i}: tokens={row.get('token_count')} "
        f"E_gen={E_generate} E_net_raw={E_net_raw} net={row.get('net_attribution')} "
        f"ratio={ratio} settle_ok={settle.get('ok')}"
    )

    # Read-only accounting: estimate → measure → residual (never gates action)
    try:
        from lib.rid_electrical_action_accounting import account_gpu_inference
        from lib.rid_electrical_energy_ledger import append_action_row
        from lib.rid_electrical_predictor import PLANT_CONFIG_ID as _PLANT_CFG

        infer_local = row.get("infer") or {}
        acct = account_gpu_inference(
            action_id=str(row.get("action_id")),
            model=str(cell.model),
            eval_duration_s=infer_local.get("eval_duration_s"),
            measured_E_net_j=E_net_raw,
            actual_eval_tokens=infer_local.get("eval_count"),
            session_id=session_id,
            plant_config_id=_PLANT_CFG,
            gpu_temp_start_c=temps.get("gpu_temp_c_settle"),
            gpu_temp_end_c=temps.get("gpu_temp_c_end"),
            residency_state=str(cell.residency),
            action_type="controlled_generate_v2",
            refresh_drift=True,
            append_drift_log=True,
            prompt_eval_duration_s=infer_local.get("prompt_eval_duration_s"),
            measured_E_tail_j=E_tail,
            tail_horizon_s=float(tail_tau_s),
            unload_before=False,
            shadow_v2=True,
        )
        row["accounting_report"] = acct
        row["accounting_human"] = acct.get("human_report")
        append_action_row(
            {
                **acct,
                "session_id": session_id,
                "executor": "gpu",
            }
        )
        print(acct.get("human_report") or "", flush=True)
    except Exception as exc:  # noqa: BLE001
        row["accounting_report"] = {
            "ok": False,
            "error": str(exc),
            "gates_action": False,
            "operational_authority": False,
        }

    out_path = session_dir / "controlled_action_v2.json"
    out_path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    row["artifact"] = str(out_path).replace("\\", "/")
    return row


def evaluate_control_repeats(
    rows: list[dict[str, Any]],
    *,
    cv_p_primary: str = "auto",
) -> dict[str, Any]:
    """Repeatability + SNR-gated net CV for a fixed cell.

    cv_p_primary:
      - "auto": peak when window long enough, else mean_from_E
      - "mean_from_E": always gate on P_mean (token matrix mode)
      - "peak": always gate on P_peak

    Outcomes:
      - insufficient_evidence
      - gross_signature_repeatable  (windowing OK; gross CV OK; net below resolution)
      - net_signature_repeatable    (SNR + CV_E + CV_P all pass)
      - unstable_signature          (SNR eligible but CV fails, or control gates fail)
    """
    usable = [
        r
        for r in rows
        if r.get("E_generate_j") is not None
        and (r.get("control_gates") or {}).get("settle_ok")
    ]

    def _net_raw(r: dict[str, Any]) -> float | None:
        if r.get("E_net_raw_j") is not None:
            return float(r["E_net_raw_j"])
        if r.get("E_net_j") is not None:
            return float(r["E_net_j"])
        return None

    e_raw = [v for v in (_net_raw(r) for r in usable) if v is not None]
    e_gen_vals = [float(r["E_generate_j"]) for r in usable]
    p_peak_vals = [
        float(r["P_peak_generate_w"])
        for r in usable
        if r.get("P_peak_generate_w") is not None
    ]
    p_mean_vals = [
        float(r["P_mean_from_E_w"])
        for r in usable
        if r.get("P_mean_from_E_w") is not None
    ]
    if not p_mean_vals:
        p_mean_vals = [
            float(r["P_mean_generate_w"])
            for r in usable
            if r.get("P_mean_generate_w") is not None
        ]
    ratios = [
        float((r.get("control_gates") or {}).get("integration_wall_ratio"))
        for r in usable
        if (r.get("control_gates") or {}).get("integration_wall_ratio") is not None
    ]
    sigma_ests = [
        float((r.get("control_gates") or {}).get("sigma_baseline_subtraction_est_j"))
        for r in usable
        if (r.get("control_gates") or {}).get("sigma_baseline_subtraction_est_j")
        is not None
    ]
    n_samples = [
        int(r["n_generate_locked_samples"])
        for r in usable
        if r.get("n_generate_locked_samples") is not None
    ]

    def _cv(xs: list[float]) -> float | None:
        if len(xs) < 2:
            return None
        mu = statistics.fmean(xs)
        if abs(mu) < 1e-9:
            return None
        return statistics.pstdev(xs) / abs(mu)

    n = len(usable)
    mu_e = statistics.fmean(e_raw) if e_raw else None
    sigma_emp = statistics.pstdev(e_raw) if len(e_raw) >= 2 else None
    sigma_est_mean = statistics.fmean(sigma_ests) if sigma_ests else None
    # Conservative baseline/subtraction noise: max(empirical scatter, idle estimate)
    sigma_sub = None
    cands = [x for x in (sigma_emp, sigma_est_mean) if x is not None and x > 0]
    if cands:
        sigma_sub = max(cands)

    snr_net = None
    if mu_e is not None and sigma_sub is not None and sigma_sub > 0:
        snr_net = abs(float(mu_e)) / float(sigma_sub)

    snr_ok = (
        snr_net is not None
        and snr_net >= SNR_NET_MIN
        and mu_e is not None
        and abs(float(mu_e)) > E_RESOLUTION_FLOOR_J
    )

    # CV_E on net only when SNR-eligible; otherwise leave null (do not mislead).
    cv_e = _cv(e_raw) if snr_ok else None
    cv_e_gen = _cv(e_gen_vals)
    cv_p_peak = _cv(p_peak_vals)
    cv_p_mean = _cv(p_mean_vals)
    mean_n_samp = statistics.fmean(n_samples) if n_samples else None
    dts = [
        float(r["delta_t_generate_s"])
        for r in usable
        if r.get("delta_t_generate_s") is not None
    ]
    mean_dt = statistics.fmean(dts) if dts else None
    peak_ok_for_cv = (
        mean_n_samp is not None
        and mean_n_samp >= MIN_SAMPLES_PEAK_CONFIDENT
        and mean_dt is not None
        and mean_dt >= 2.0
    )
    mode = str(cv_p_primary or "auto")
    if mode == "mean_from_E":
        cv_p = cv_p_mean
        cv_p_metric = "mean_from_E"
    elif mode == "peak":
        cv_p = cv_p_peak
        cv_p_metric = "peak"
    else:
        cv_p = cv_p_peak if peak_ok_for_cv else cv_p_mean
        cv_p_metric = "peak" if peak_ok_for_cv else "mean_from_E"

    ratio_ok_n = sum(
        1
        for r in usable
        if (r.get("control_gates") or {}).get("integration_wall_ratio_ok")
    )
    idle_ok_n = sum(
        1 for r in usable if (r.get("control_gates") or {}).get("CV_P_idle_ok")
    )
    control_ok = n >= 3 and ratio_ok_n == n and idle_ok_n == n
    gross_ok = (
        cv_e_gen is not None
        and cv_e_gen <= CV_E_GENERATE_MAX
        and statistics.fmean(e_gen_vals) > 0
    )

    if n < 3:
        outcome = "insufficient_evidence"
        net_attr = "insufficient_evidence"
    elif not control_ok:
        outcome = "unstable_signature"
        net_attr = "control_gates_failed"
    elif not snr_ok:
        if gross_ok:
            outcome = "gross_signature_repeatable"
            net_attr = "below_resolution"
        else:
            outcome = "unstable_signature"
            net_attr = "below_resolution"
    elif (
        cv_e is not None
        and cv_p is not None
        and cv_e <= CV_E_MAX
        and cv_p <= CV_P_MAX
        and mu_e is not None
        and mu_e > 0
    ):
        outcome = "net_signature_repeatable"
        net_attr = "authoritative"
    else:
        outcome = "unstable_signature"
        net_attr = "snr_ok_but_cv_failed"

    return {
        "n_rows": len(rows),
        "n_usable": n,
        "mu_E_net_raw_j": mu_e,
        "sigma_E_net_raw_j": sigma_emp,
        "sigma_baseline_subtraction_j": sigma_sub,
        "SNR_net": snr_net,
        "SNR_net_ok": snr_ok,
        "CV_E": cv_e,
        "mu_E_generate_j": statistics.fmean(e_gen_vals) if e_gen_vals else None,
        "CV_E_generate": cv_e_gen,
        "mu_P_peak_w": statistics.fmean(p_peak_vals) if p_peak_vals else None,
        "CV_P_peak": cv_p_peak,
        "mu_P_mean_from_E_w": statistics.fmean(p_mean_vals) if p_mean_vals else None,
        "CV_P_mean": cv_p_mean,
        "CV_P": cv_p,
        "CV_P_metric": cv_p_metric,
        "mean_n_generate_samples": mean_n_samp,
        "mean_delta_t_generate_s": mean_dt,
        "mean_integration_wall_ratio": statistics.fmean(ratios) if ratios else None,
        "ratio_ok_n": ratio_ok_n,
        "idle_cv_ok_n": idle_ok_n,
        "outcome": outcome,
        "net_attribution": net_attr,
        "gross_authority": "authoritative" if gross_ok and control_ok else "not_established",
        "repeatable": outcome == "net_signature_repeatable",
        "gates": {
            "CV_E_MAX": CV_E_MAX,
            "CV_P_MAX": CV_P_MAX,
            "CV_E_GENERATE_MAX": CV_E_GENERATE_MAX,
            "CV_IDLE_MAX": CV_IDLE_MAX,
            "INTEGRATION_WALL_RATIO": [
                INTEGRATION_WALL_RATIO_LO,
                INTEGRATION_WALL_RATIO_HI,
            ],
            "SNR_NET_MIN": SNR_NET_MIN,
            "E_RESOLUTION_FLOOR_J": E_RESOLUTION_FLOOR_J,
            "MIN_SAMPLES_PEAK_CONFIDENT": MIN_SAMPLES_PEAK_CONFIDENT,
            "MIN_REPEATS": 3,
            "cv_p_primary": mode,
        },
        "learning_admission": False,
        "note": (
            "SNR gate precedes CV_E on net. below_resolution ≠ unstable. "
            "Short actions: E_generate gross is authoritative; E_net withheld. "
            "Token matrix resumes only above the net resolution boundary."
        ),
    }
