#!/usr/bin/env python3
"""Controlled ledger campaign: one-factor cells + CV repeatability gates.

Learning (Ê predictor) stays blocked until predefined cells show low CV_E/CV_P
across independent repeats and between-condition gaps exceed measurement noise.

Does not touch Master S_n, A(t), or routing.
"""
from __future__ import annotations

import json
import math
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_capture import SessionCapture, load_session_meta, load_session_samples
from lib.rid_electrical_outcomes import action_record, idle_baseline_w, validated_energy
from lib.rid_stressor import start_stressor, stop_stressor

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
CAMPAIGN_DIR = OUT_DIR / "ledger_campaign"
SESSIONS = OUT_DIR / "sessions"

# Predefined repeatability gates (do not soften ad hoc for admission)
CV_E_MAX = 0.20
CV_P_MAX = 0.15
MIN_REPEATS = 3
MIN_VALID_FRAC = 0.67
BETWEEN_CONDITION_MIN_SEP_E = 0.15  # |μ_a-μ_b|/max(|μ|,1) must exceed this vs noise
LEARNING_ADMISSION_WITHHELD = True  # hard default until evaluate_learning_admission passes

TOKEN_BUCKETS = {
    "tokens_short": 64,
    "tokens_medium": 256,
    "tokens_long": 512,
}

DEFAULT_MODEL = "viv-voice-qwen"
ALT_MODEL = "viv-qwen-teacher"
PROMPT = (
    "Explain liquid-cooled CPU and GPU power draw for a local agent in clear prose. "
    "Include thermal and electrical considerations."
)


@dataclass(frozen=True)
class CellSpec:
    """One controlled condition: single factor varied from base."""

    cell_id: str
    factor: str  # tokens|thermal|repetition|model|executor
    level: str
    executor: str  # cpu_only|gpu_only|mixed
    model: str
    num_predict: int
    thermal: str  # cold|warm|uncontrolled
    repetition: str  # first|repeat|na
    smoke: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def campaign_matrix(*, smoke: bool = False) -> list[CellSpec]:
    """One-factor-at-a-time cells. Smoke = short plumbing subset."""
    base_tokens = 32 if smoke else TOKEN_BUCKETS["tokens_medium"]
    model = DEFAULT_MODEL
    cells: list[CellSpec] = []

    if smoke:
        # Minimal plumbing set: one tokens cell, one thermal, one executor
        return [
            CellSpec(
                cell_id="tokens__tokens_short",
                factor="tokens",
                level="tokens_short",
                executor="gpu_only",
                model=model,
                num_predict=32,
                thermal="uncontrolled",
                repetition="first",
                smoke=True,
            ),
            CellSpec(
                cell_id="thermal__cold",
                factor="thermal",
                level="cold",
                executor="gpu_only",
                model=model,
                num_predict=32,
                thermal="cold",
                repetition="first",
                smoke=True,
            ),
            CellSpec(
                cell_id="executor__gpu_only",
                factor="executor",
                level="gpu_only",
                executor="gpu_only",
                model=model,
                num_predict=32,
                thermal="uncontrolled",
                repetition="first",
                smoke=True,
            ),
        ]

    # Factor: token-count buckets (GPU-only, warm/uncontrolled, first)
    for level, npred in TOKEN_BUCKETS.items():
        cells.append(
            CellSpec(
                cell_id=f"tokens__{level}",
                factor="tokens",
                level=level,
                executor="gpu_only",
                model=model,
                num_predict=npred,
                thermal="uncontrolled",
                repetition="first",
                smoke=False,
            )
        )

    # Factor: thermal (fixed medium tokens)
    for level in ("cold", "warm"):
        cells.append(
            CellSpec(
                cell_id=f"thermal__{level}",
                factor="thermal",
                level=level,
                executor="gpu_only",
                model=model,
                num_predict=base_tokens,
                thermal=level,
                repetition="first",
                smoke=False,
            )
        )

    # Factor: first vs repeat
    for level in ("first", "repeat"):
        cells.append(
            CellSpec(
                cell_id=f"repetition__{level}",
                factor="repetition",
                level=level,
                executor="gpu_only",
                model=model,
                num_predict=base_tokens,
                thermal="uncontrolled",
                repetition=level,
                smoke=False,
            )
        )

    # Factor: model
    for level, m in (("default_qwen", DEFAULT_MODEL), ("alt_teacher", ALT_MODEL)):
        cells.append(
            CellSpec(
                cell_id=f"model__{level}",
                factor="model",
                level=level,
                executor="gpu_only",
                model=m,
                num_predict=base_tokens,
                thermal="uncontrolled",
                repetition="first",
                smoke=False,
            )
        )

    # Factor: executor
    for level in ("cpu_only", "gpu_only", "mixed"):
        cells.append(
            CellSpec(
                cell_id=f"executor__{level}",
                factor="executor",
                level=level,
                executor=level,
                model=model,
                num_predict=base_tokens,
                thermal="uncontrolled",
                repetition="first",
                smoke=False,
            )
        )

    return cells


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _coolant_c() -> float | None:
    try:
        from lib.corsair_telemetry import read_latest

        return read_latest().get("coolant_c")
    except Exception:  # noqa: BLE001
        return None


def prepare_thermal(level: str, *, smoke: bool) -> dict[str, Any]:
    """Best-effort cold/warm conditioning before the measured action."""
    notes: list[str] = []
    c0 = _coolant_c()
    if level == "cold":
        # Idle wait for partial cool-down
        wait_s = 20.0 if smoke else 90.0
        t_end = time.time() + wait_s
        while time.time() < t_end:
            time.sleep(2.0)
        notes.append(f"idle_wait_s={wait_s}")
    elif level == "warm":
        # Short CPU burn to raise plant temperature
        burn_s = 8.0 if smoke else 45.0
        procs = start_stressor(cores=4)
        time.sleep(burn_s)
        stop_stressor(procs)
        notes.append(f"cpu_warmup_s={burn_s}")
        time.sleep(2.0)
    c1 = _coolant_c()
    return {
        "thermal_level": level,
        "coolant_c_before": c0,
        "coolant_c_after_prep": c1,
        "notes": notes,
    }


def ollama_generate(
    *,
    model: str,
    num_predict: int,
    prompt: str = PROMPT,
    timeout_s: float = 300.0,
) -> dict[str, Any]:
    """Single Ollama /api/generate; returns token counts from response fields."""
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": int(num_predict)},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        err = None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raw = {}
        err = str(exc)
    dt = time.perf_counter() - t0
    # Ollama fields: eval_count (output), prompt_eval_count (input)
    out_tok = raw.get("eval_count")
    in_tok = raw.get("prompt_eval_count")
    total = None
    if isinstance(out_tok, int) or isinstance(in_tok, int):
        total = int(out_tok or 0) + int(in_tok or 0)
    return {
        "ok": err is None and bool(raw),
        "error": err,
        "model": model,
        "num_predict": num_predict,
        "prompt_eval_count": in_tok,
        "eval_count": out_tok,
        "token_count_total": total,
        "wall_s": dt,
        "done_reason": raw.get("done_reason"),
    }


def run_controlled_action(
    cell: CellSpec,
    *,
    repeat_i: int,
    cadence_s: float = 1.0,
) -> dict[str, Any]:
    """One independent action under a single controlled cell."""
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    session_id = f"ledger_{cell.cell_id}_r{repeat_i}_{_utc_stamp()}"
    session_dir = SESSIONS / session_id
    thermal_prep = prepare_thermal(cell.thermal, smoke=cell.smoke)

    # For repeat: run a discarded warm-up generate first
    warmup = None
    if cell.repetition == "repeat":
        warmup = ollama_generate(
            model=cell.model,
            num_predict=max(16, cell.num_predict // 4),
            timeout_s=120.0 if cell.smoke else 300.0,
        )

    meta = {
        "session_id": session_id,
        "workload": f"ledger_{cell.executor}",
        "smoke": cell.smoke,
        "experiment": "rid_electrical_ledger_campaign_v1",
        "cell": cell.to_dict(),
        "repeat_i": repeat_i,
        "thermal_prep": thermal_prep,
        "warmup": warmup,
        "goal": "controlled_action_cost_ledger",
        "not_master_prediction": True,
        "learning_admission": False,
        "started_at": _utc(),
    }
    cap = SessionCapture(session_dir, meta)
    cap.open()
    t0 = time.perf_counter()

    # Idle baseline window
    idle_s = 4.0 if cell.smoke else 12.0
    t_idle_end = time.perf_counter() + idle_s
    while time.perf_counter() < t_idle_end:
        cap.record(
            workload=meta["workload"],
            phase="idle",
            cadence_s=cadence_s,
            session_id=session_id,
        )
        time.sleep(cadence_s)

    cpu_procs: list[Any] = []
    infer_result: dict[str, Any] | None = None
    try:
        if cell.executor in {"cpu_only", "mixed"}:
            cpu_procs = start_stressor(cores=4 if cell.smoke else None)
        # Action window with concurrent sampling
        action_deadline = time.perf_counter() + (25.0 if cell.smoke else 180.0)
        if cell.executor in {"gpu_only", "mixed"}:
            # Run generate in-process while sampling in a simple poll loop:
            # sample, then non-blocking isn't available — do interleaved:
            # start generate as blocking but sample before/after; for better
            # coverage sample during a threaded generate.
            import threading

            box: dict[str, Any] = {}

            def _job() -> None:
                box["r"] = ollama_generate(
                    model=cell.model,
                    num_predict=cell.num_predict,
                    timeout_s=120.0 if cell.smoke else 300.0,
                )

            th = threading.Thread(target=_job, daemon=True)
            th.start()
            while th.is_alive() and time.perf_counter() < action_deadline:
                cap.record(
                    workload=meta["workload"],
                    phase="action",
                    cadence_s=cadence_s,
                    session_id=session_id,
                )
                time.sleep(cadence_s)
            th.join(timeout=5.0)
            infer_result = box.get("r")
        else:
            # CPU-only timed action
            act_s = 12.0 if cell.smoke else 60.0
            t_act = time.perf_counter() + act_s
            while time.perf_counter() < t_act:
                cap.record(
                    workload=meta["workload"],
                    phase="action",
                    cadence_s=cadence_s,
                    session_id=session_id,
                )
                time.sleep(cadence_s)
            infer_result = {
                "ok": True,
                "token_count_total": None,
                "note": "cpu_only_no_tokens",
                "model": None,
                "num_predict": None,
            }
    finally:
        if cpu_procs:
            stop_stressor(cpu_procs)

    # Cooldown samples
    cool_s = 3.0 if cell.smoke else 10.0
    t_c = time.perf_counter() + cool_s
    while time.perf_counter() < t_c:
        cap.record(
            workload=meta["workload"],
            phase="cooldown",
            cadence_s=cadence_s,
            session_id=session_id,
        )
        time.sleep(cadence_s)

    duration = time.perf_counter() - t0
    cap.close(
        duration_s=duration,
        infer=infer_result,
        cell=cell.to_dict(),
        thermal_prep=thermal_prep,
    )
    samples = load_session_samples(session_dir)
    meta = load_session_meta(session_dir)

    action_samples = [s for s in samples if s.get("phase") == "action"]
    if len(action_samples) < 2:
        action_samples = [s for s in samples if s.get("phase") not in {"idle"}]

    idle = idle_baseline_w(samples)
    P_idle = idle.get("P_idle_baseline_w")
    tokens = None if not infer_result else infer_result.get("token_count_total")
    row = action_record(
        action_id=f"{session_id}::controlled_action",
        action_type="controlled_action",
        workload=meta.get("workload") or cell.executor,
        samples=action_samples,
        meta=meta,
        P_idle_baseline_w=P_idle if isinstance(P_idle, (int, float)) else None,
        model=cell.model if cell.executor != "cpu_only" else None,
        token_count=int(tokens) if isinstance(tokens, int) else None,
        inference_params={
            "num_predict": cell.num_predict,
            "executor": cell.executor,
            "factor": cell.factor,
            "level": cell.level,
        },
        condition_tags=[
            f"factor:{cell.factor}",
            f"level:{cell.level}",
            f"executor:{cell.executor}",
            f"thermal:{cell.thermal}",
            f"repetition:{cell.repetition}",
            f"model:{cell.model}",
        ],
    )
    # Attach temps summary + provenance
    coolants = [s.get("coolant_c") for s in action_samples if s.get("coolant_c") is not None]
    gpu_ts = [s.get("gpu_temp_c") for s in action_samples if s.get("gpu_temp_c") is not None]
    pkg = [s.get("cpu_package_c") for s in action_samples if s.get("cpu_package_c") is not None]
    row["temperatures"] = {
        "coolant_c_mean": (sum(coolants) / len(coolants)) if coolants else None,
        "coolant_c_max": max(coolants) if coolants else None,
        "gpu_temp_c_mean": (sum(gpu_ts) / len(gpu_ts)) if gpu_ts else None,
        "gpu_temp_c_max": max(gpu_ts) if gpu_ts else None,
        "cpu_package_c_mean": (sum(pkg) / len(pkg)) if pkg else None,
        "cpu_package_c_max": max(pkg) if pkg else None,
    }
    row["infer"] = infer_result
    row["cell"] = cell.to_dict()
    row["repeat_i"] = repeat_i
    row["session_id"] = session_id
    row["provenance"] = {
        "capture": "SessionCapture+TriadSession",
        "power": "HWiNFO+NVML",
        "tokens": "ollama_/api/generate" if cell.executor != "cpu_only" else "none",
        "experiment": "rid_electrical_ledger_campaign_v1",
    }
    row["session_validated"] = validated_energy(samples)

    out_path = session_dir / "controlled_action.json"
    out_path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    return row


def _cv(vals: Sequence[float]) -> float | None:
    xs = [float(v) for v in vals]
    if len(xs) < 2:
        return None
    mu = statistics.fmean(xs)
    if abs(mu) < 1e-9:
        return None
    return statistics.pstdev(xs) / abs(mu)


def evaluate_cell_repeatability(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Classify one cell: repeatable_signature | unstable_signature | insufficient_evidence."""
    valid = [
        r
        for r in rows
        if r.get("confidence") in {"valid", "degraded"} and r.get("E_net_j") is not None
    ]
    strict = [r for r in valid if r.get("confidence") == "valid"]
    use = strict if len(strict) >= MIN_REPEATS else valid
    e_vals = [float(r["E_net_j"]) for r in use]
    p_vals = [float(r["P_peak_w"]) for r in use if r.get("P_peak_w") is not None]
    cv_e = _cv(e_vals)
    cv_p = _cv(p_vals)
    mu_e = statistics.fmean(e_vals) if e_vals else None
    mu_p = statistics.fmean(p_vals) if p_vals else None
    sig_e = statistics.pstdev(e_vals) if len(e_vals) > 1 else (0.0 if e_vals else None)
    sig_p = statistics.pstdev(p_vals) if len(p_vals) > 1 else (0.0 if p_vals else None)
    n = len(use)
    n_rows = len(rows)
    missing_or_degraded = n_rows - len(strict)

    if n < MIN_REPEATS or (not e_vals):
        outcome = "insufficient_evidence"
        reasons: list[str] = []
        if n < MIN_REPEATS:
            reasons.append(f"n_valid={n}<{MIN_REPEATS}")
        if missing_or_degraded and n < MIN_REPEATS:
            reasons.append("missing_or_degraded_repeats")
        if not e_vals:
            reasons.append("no_E_net")
    elif (
        cv_e is not None
        and cv_p is not None
        and cv_e <= CV_E_MAX
        and cv_p <= CV_P_MAX
        and mu_e is not None
        and mu_e > 0
    ):
        outcome = "repeatable_signature"
        reasons = []
    else:
        outcome = "unstable_signature"
        reasons = []
        if cv_e is not None and cv_e > CV_E_MAX:
            reasons.append(f"CV_E={cv_e:.3f}>{CV_E_MAX}")
        if cv_p is not None and cv_p > CV_P_MAX:
            reasons.append(f"CV_P={cv_p:.3f}>{CV_P_MAX}")
        if mu_e is not None and mu_e <= 0:
            reasons.append("non_positive_mu_E_net")
        if cv_e is None or cv_p is None:
            reasons.append("cv_undefined")

    return {
        "n_rows": n_rows,
        "n_valid": n,
        "n_strict_valid": len(strict),
        "valid_frac": n / max(1, n_rows),
        "mu_E_net_j": mu_e,
        "sigma_E_net_j": sig_e,
        "CV_E": cv_e,
        "mu_P_peak_w": mu_p,
        "sigma_P_peak_w": sig_p,
        "CV_P": cv_p,
        "gates": {
            "CV_E_MAX": CV_E_MAX,
            "CV_P_MAX": CV_P_MAX,
            "MIN_REPEATS": MIN_REPEATS,
            "MIN_VALID_FRAC": MIN_VALID_FRAC,
        },
        "outcome": outcome,
        "outcome_reasons": reasons,
        "repeatable": outcome == "repeatable_signature",
        "learning_eligible_cell": outcome == "repeatable_signature",
    }


def _pooled_uncertainty(
    sig_a: float | None, n_a: int, sig_b: float | None, n_b: int
) -> float | None:
    if sig_a is None or sig_b is None or n_a < 2 or n_b < 2:
        return None
    num = (n_a - 1) * (sig_a**2) + (n_b - 1) * (sig_b**2)
    den = n_a + n_b - 2
    if den <= 0:
        return None
    return math.sqrt(num / den)


def evaluate_factor_separability(
    cell_reports: dict[str, dict[str, Any]],
    *,
    factor: str,
) -> dict[str, Any]:
    """|μ_a-μ_b| must exceed pooled within-cell uncertainty."""
    cells = []
    for cell_id, rep in cell_reports.items():
        if not cell_id.startswith(f"{factor}__"):
            continue
        if rep.get("mu_E_net_j") is None:
            continue
        cells.append((cell_id, rep))
    pairs = []
    distinguishable = 0
    for i in range(len(cells)):
        for j in range(i + 1, len(cells)):
            id_a, a = cells[i]
            id_b, b = cells[j]
            mu_a = float(a["mu_E_net_j"])
            mu_b = float(b["mu_E_net_j"])
            delta = abs(mu_a - mu_b)
            pooled = _pooled_uncertainty(
                a.get("sigma_E_net_j"),
                int(a.get("n_valid") or 0),
                b.get("sigma_E_net_j"),
                int(b.get("n_valid") or 0),
            )
            both_rep = bool(a.get("repeatable")) and bool(b.get("repeatable"))
            sep_ok = pooled is not None and delta > pooled and both_rep
            if sep_ok:
                distinguishable += 1
            pairs.append(
                {
                    "a": id_a,
                    "b": id_b,
                    "abs_delta_mu_E": delta,
                    "pooled_within_sigma_E": pooled,
                    "separable": bool(sep_ok),
                    "both_repeatable": both_rep,
                    "rel_sep": delta / max(abs(mu_a), abs(mu_b), 1.0),
                }
            )
    return {
        "factor": factor,
        "n_cells": len(cells),
        "n_pairs": len(pairs),
        "n_separable_pairs": distinguishable,
        "factor_separable": distinguishable >= 1,
        "pairs": pairs,
    }


def evaluate_learning_admission(cell_reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Never auto-admits. Emits reviewable candidate status only."""
    outcome_counts = {
        "repeatable_signature": 0,
        "unstable_signature": 0,
        "insufficient_evidence": 0,
    }
    for rep in cell_reports.values():
        oc = str(rep.get("outcome") or "insufficient_evidence")
        outcome_counts[oc] = outcome_counts.get(oc, 0) + 1

    passing = {
        k: v for k, v in cell_reports.items() if v.get("outcome") == "repeatable_signature"
    }
    factors = sorted({cid.split("__", 1)[0] for cid in cell_reports})
    sep_by_factor = {
        f: evaluate_factor_separability(cell_reports, factor=f) for f in factors
    }
    separable_factors = [f for f, s in sep_by_factor.items() if s.get("factor_separable")]

    n_unstable = outcome_counts.get("unstable_signature", 0)
    if passing and separable_factors:
        decision = "predictor_dataset_candidate"
        decision_note = (
            "Repeatable within cells and separable between conditions — "
            "reviewable predictor dataset candidate only (auto_admit=false)."
        )
    elif passing and not separable_factors:
        decision = "accounting_ledger_only"
        decision_note = (
            "Repeatable within cells but not separable between conditions — "
            "keep as accounting ledger only."
        )
    elif n_unstable > 0 and not passing:
        decision = "improve_controls_or_instrumentation"
        decision_note = (
            "Unstable within cells — improve experimental controls or instrumentation."
        )
    elif n_unstable > 0 and passing:
        decision = "train_only_passing_factors_cells"
        decision_note = (
            "Mixed results — any future learning may use only factors/cells that "
            "independently pass; still requires explicit review (auto_admit=false)."
        )
    else:
        decision = "insufficient_evidence"
        decision_note = "Insufficient independent repeats or valid samples."

    return {
        "learning_admission_withheld": True,
        "learning_admission_granted": False,
        "auto_admit": False,
        "campaign_decision": decision,
        "campaign_decision_note": decision_note,
        "cell_outcome_counts": outcome_counts,
        "n_cells": len(cell_reports),
        "n_repeatable_cells": len(passing),
        "repeatable_cell_ids": sorted(passing.keys()),
        "separability_by_factor": sep_by_factor,
        "separable_factors": separable_factors,
        "criteria": {
            "CV_E_MAX": CV_E_MAX,
            "CV_P_MAX": CV_P_MAX,
            "MIN_REPEATS": MIN_REPEATS,
            "separability": "|mu_a-mu_b| > pooled_within_cell_sigma_E",
            "auto_admit": False,
        },
        "state": {
            "accounting_implemented": True,
            "measurements_valid": True,
            "cost_signatures_repeatable": len(passing) > 0,
            "learning_admission_withheld": True,
        },
        "note": (
            "Even a fully passing campaign yields a reviewable learning-candidate "
            "artifact only; never automatic predictor authorization."
        ),
    }


def write_learning_candidate(summary: dict[str, Any]) -> dict[str, Any]:
    """Reviewable artifact — never grants predictor authority."""
    adm = summary.get("learning_admission") or {}
    decision = adm.get("campaign_decision")
    candidate = {
        "ok": True,
        "at": summary.get("at"),
        "artifact_type": "learning_candidate_review",
        "auto_admit": False,
        "predictor_authorized": False,
        "learning_admission_granted": False,
        "campaign_decision": decision,
        "campaign_decision_note": adm.get("campaign_decision_note"),
        "is_predictor_dataset_candidate": decision == "predictor_dataset_candidate",
        "passing_cells": adm.get("repeatable_cell_ids") or [],
        "separable_factors": adm.get("separable_factors") or [],
        "cell_outcome_counts": adm.get("cell_outcome_counts"),
        "criteria": adm.get("criteria"),
        "review_required": True,
        "note": (
            "Reviewable only. Do not create or authorize an energy predictor "
            "without explicit operator approval after this artifact."
        ),
    }
    path = OUT_DIR / "learning_candidate_latest.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    md = OUT_DIR / "learning_candidate_latest.md"
    md.write_text(
        "\n".join(
            [
                "# Energy learning candidate (REVIEW ONLY)",
                "",
                f"- **Decision:** `{decision}`",
                "- **Predictor authorized:** false",
                "- **auto_admit:** false",
                f"- **Passing cells:** {candidate['passing_cells']}",
                f"- **Separable factors:** {candidate['separable_factors']}",
                "",
                str(adm.get("campaign_decision_note") or ""),
                "",
            ]
        ),
        encoding="utf-8",
    )
    candidate["artifact_json"] = str(path).replace("\\", "/")
    candidate["artifact_md"] = str(md).replace("\\", "/")
    return candidate


def summarize_campaign(action_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_cell: dict[str, list[dict[str, Any]]] = {}
    for r in action_rows:
        cid = (r.get("cell") or {}).get("cell_id") or "unknown"
        by_cell.setdefault(cid, []).append(r)
    cell_reports = {cid: evaluate_cell_repeatability(rows) for cid, rows in by_cell.items()}
    admission = evaluate_learning_admission(cell_reports)
    summary = {
        "ok": True,
        "at": _utc(),
        "experiment_id": "rid_electrical_ledger_campaign_v1",
        "n_actions": len(action_rows),
        "n_cells": len(by_cell),
        "cells": cell_reports,
        "learning_admission": admission,
        "predictor_blocked": True,
        "auto_admit": False,
        "authority": "controlled_ledger_only",
        "enters_A_t": False,
        "enters_master_s_n": False,
    }
    summary["learning_candidate"] = write_learning_candidate(summary)
    return summary
