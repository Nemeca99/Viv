#!/usr/bin/env python3
"""Close electrical→Master prediction branch after decisive negative evidence.

Freezes the 15-session corpus (hashes), stamps lifecycle rejected_operational_use,
disables authority paths fail-closed, writes one postmortem, updates authoritative
artifacts. Does not delete scaffolds or tests.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_close_prediction_branch.py
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_policy import (  # noqa: E402
    LIFECYCLE,
    RAIL_ROLE,
    policy_stamp,
)
from lib.rid_electrical_session_eval import (  # noqa: E402
    list_decisive_sessions,
    qualify_for_prediction,
)

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
SESSIONS = OUT_DIR / "sessions"
DECISIVE_JSON = OUT_DIR / "decisive_evidence_latest.json"
DECISIVE_MD = OUT_DIR / "decisive_evidence_latest.md"
ROLE_JSON = OUT_DIR / "role_decision_latest.json"
ROLE_MD = OUT_DIR / "role_decision_latest.md"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def freeze_corpus() -> dict[str, Any]:
    sessions = [s for s in list_decisive_sessions() if qualify_for_prediction(s)]
    rows: list[dict[str, Any]] = []
    wl = Counter()
    for s in sessions:
        sid = str(s["session_id"])
        d = SESSIONS / sid
        samples = d / "samples.jsonl"
        meta = d / "session_meta.json"
        sample_hash = _sha256_file(samples) if samples.is_file() else None
        meta_hash = _sha256_file(meta) if meta.is_file() else None
        # Sensor provenance from first sample
        prov = {}
        origins = {}
        if s.get("samples"):
            p0 = s["samples"][0].get("provenance") or {}
            prov = {
                "hwinfo_path": p0.get("hwinfo_path"),
                "master_source": p0.get("master_source"),
                "w_gpu_source": p0.get("w_gpu_source"),
                "i_gpu_stamp_expected": p0.get("i_gpu_stamp_expected"),
                "master_disk_published": p0.get("master_disk_published"),
            }
            origins = p0.get("origins") or {}
        wl[str(s.get("workload"))] += 1
        rows.append(
            {
                "session_id": sid,
                "workload": s.get("workload"),
                "n_samples": s.get("n"),
                "master_var": s.get("master_var"),
                "duration_s": (s.get("meta") or {}).get("duration_s"),
                "samples_sha256": sample_hash,
                "meta_sha256": meta_hash,
                "provenance": prov,
                "origins": origins,
            }
        )
    # Corpus aggregate hash (ordered session_id + sample hashes)
    cat = "\n".join(
        f"{r['session_id']}:{r['samples_sha256']}:{r['meta_sha256']}" for r in rows
    )
    corpus_hash = _sha256_text(cat)
    # Mark non-corpus / incomplete / smoke as superseded for prediction
    superseded: list[dict[str, Any]] = []
    if SESSIONS.is_dir():
        corpus_ids = {r["session_id"] for r in rows}
        for d in sorted(SESSIONS.iterdir()):
            if not d.is_dir() or d.name in corpus_ids:
                continue
            meta_path = d / "session_meta.json"
            if not meta_path.is_file():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            reason = []
            if meta.get("smoke"):
                reason.append("smoke")
            if meta.get("incomplete") or not meta.get("ended_at"):
                reason.append("incomplete_or_unterminated")
            if not reason:
                reason.append("outside_decisive_15_session_corpus")
            meta["prediction_superseded"] = True
            meta["prediction_superseded_reason"] = ",".join(reason)
            meta["prediction_branch"] = "closed_negative_result"
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            superseded.append({"session_id": d.name, "reason": reason})

    # Mark corpus sessions frozen
    for r in rows:
        meta_path = SESSIONS / r["session_id"] / "session_meta.json"
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["corpus_frozen"] = True
        meta["corpus_id"] = "rid_electrical_decisive_v1_15"
        meta["corpus_sha256"] = corpus_hash
        meta["prediction_branch"] = "closed_negative_result"
        meta["lifecycle"] = LIFECYCLE
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    versions = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "foundation_root": str(FOUNDATION).replace("\\", "/"),
        "policy_module": "lib/rid_electrical_policy.py",
    }
    # Best-effort package stamps
    try:
        import psutil  # type: ignore

        versions["psutil"] = getattr(psutil, "__version__", "unknown")
    except Exception:  # noqa: BLE001
        versions["psutil"] = None

    manifest = {
        "ok": True,
        "at": _utc(),
        "corpus_id": "rid_electrical_decisive_v1_15",
        "corpus_sha256": corpus_hash,
        "n_sessions": len(rows),
        "workload_composition": dict(sorted(wl.items())),
        "sessions": rows,
        "superseded_non_corpus": superseded,
        "software_versions": versions,
        "lifecycle": LIFECYCLE,
        "rail_role": RAIL_ROLE,
        "note": (
            "Frozen decisive corpus for negative prediction result. "
            "Do not reopen by collecting more of the same construction."
        ),
    }
    path = OUT_DIR / "corpus_freeze_manifest.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["artifact"] = str(path).replace("\\", "/")
    return manifest


def _corr(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 3:
        return None
    mx = sum(xs[:n]) / n
    my = sum(ys[:n]) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    dx = math.sqrt(sum((xs[i] - mx) ** 2 for i in range(n)))
    dy = math.sqrt(sum((ys[i] - my) ** 2 for i in range(n)))
    if dx < 1e-12 or dy < 1e-12:
        return None
    return num / (dx * dy)


def _best_lag(xs: list[float], ys: list[float], max_lag: int = 5) -> dict[str, Any]:
    best = {"lag": 0, "corr": None}
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            a, b = xs[: len(xs) - lag or None], ys[lag:]
        else:
            a, b = xs[-lag:], ys[: len(ys) + lag or None]
        c = _corr(list(a), list(b))
        if c is None:
            continue
        if best["corr"] is None or abs(c) > abs(float(best["corr"])):
            best = {"lag": lag, "corr": c}
    return best


def postmortem(corpus: dict[str, Any], decisive: dict[str, Any]) -> dict[str, Any]:
    """Single learning postmortem — not another admission campaign."""
    sessions = [s for s in list_decisive_sessions() if qualify_for_prediction(s)]
    masters: list[float] = []
    s_el: list[float] = []
    w_cpu: list[float] = []
    w_gpu: list[float] = []
    i_gpu: list[float] = []
    derived_n = 0
    independent_claims = 0
    for s in sessions:
        for row in s.get("samples") or []:
            if row.get("master_s_n") is None or row.get("S_electrical") is None:
                continue
            masters.append(float(row["master_s_n"]))
            s_el.append(float(row["S_electrical"]))
            pr = row.get("P_rails") or {}
            ir = row.get("I_derived") or {}
            if pr.get("w_cpu") is not None:
                w_cpu.append(float(pr["w_cpu"]))
            if pr.get("w_gpu") is not None:
                w_gpu.append(float(pr["w_gpu"]))
            if ir.get("i_gpu") is not None:
                i_gpu.append(float(ir["i_gpu"]))
            if ir.get("i_gpu_origin") == "software_ohm_from_measured_hwinfo_rails":
                derived_n += 1
            if ir.get("i_gpu_independent"):
                independent_claims += 1

    # Align power series lengths with masters for corr (use overlapping prefix)
    n = len(masters)
    wc = w_cpu[:n] if len(w_cpu) >= n else w_cpu
    wg = w_gpu[:n] if len(w_gpu) >= n else w_gpu
    # Rebuild aligned lists from samples more carefully
    masters2, sel2, wc2, wg2 = [], [], [], []
    for s in sessions:
        for row in s.get("samples") or []:
            if row.get("master_s_n") is None or row.get("S_electrical") is None:
                continue
            pr = row.get("P_rails") or {}
            if pr.get("w_cpu") is None or pr.get("w_gpu") is None:
                continue
            masters2.append(float(row["master_s_n"]))
            sel2.append(float(row["S_electrical"]))
            wc2.append(float(pr["w_cpu"]))
            wg2.append(float(pr["w_gpu"]))

    lag = _best_lag(sel2, masters2, max_lag=8) if masters2 else {"lag": None, "corr": None}
    corr_sel = _corr(sel2, masters2)
    corr_wc = _corr(wc2, masters2)
    corr_wg = _corr(wg2, masters2)
    # Partial redundancy: how much S_electrical tracks power (already in plant via load)
    corr_sel_wc = _corr(sel2, wc2)
    corr_sel_wg = _corr(sel2, wg2)

    delta = (decisive.get("decision_evidence") or {}).get("delta_info")
    ablation = decisive.get("ablation") or {}

    categories = {
        "redundancy": {
            "claim": (
                "S_electrical and rail power co-vary with load already reflected in "
                "Master via cpu_automaton/gpu/coolant subsystems; adding electrical "
                "duplicates information Master already has."
            ),
            "corr_S_electrical_vs_Master": corr_sel,
            "corr_w_cpu_vs_Master": corr_wc,
            "corr_w_gpu_vs_Master": corr_wg,
            "corr_S_electrical_vs_w_cpu": corr_sel_wc,
            "corr_S_electrical_vs_w_gpu": corr_sel_wg,
        },
        "noise": {
            "claim": (
                "All ablation features (P, P+V, P+V+I, S_electrical) raised MAE vs "
                "Master-only baseline on the same holdouts — feature adds variance "
                "without out-of-sample predictive structure."
            ),
            "ablation_delta_info": {
                k: (v or {}).get("delta_info") for k, v in ablation.items()
            },
            "combined_delta_info": delta,
        },
        "lag": {
            "claim": (
                "HWiNFO CSV / rail sampling may lag or step-align differently from "
                "TriadSession Master commits; best cross-corr lag is reported."
            ),
            "best_cross_corr_S_electrical_leads_Master": lag,
            "note": "Positive lag means Master series shifted later relative to S_electrical.",
        },
        "derived_variable_dependence": {
            "claim": (
                "I_GPU is Ohm-reconstructed from measured PCIe+8-pin P/V "
                "(software_ohm_from_measured_hwinfo_rails), not an independent current "
                "meter — S_electrical is not three free axes."
            ),
            "ohm_derived_i_gpu_samples": derived_n,
            "independent_i_gpu_claims": independent_claims,
            "stamp": "software_ohm_from_measured_hwinfo_rails",
        },
    }

    # Dominant category ranking by evidence strength
    dominant = "redundancy+noise"
    if independent_claims == 0 and derived_n > 0:
        dominant = "derived_variable_dependence+redundancy+noise"

    report = {
        "ok": True,
        "at": _utc(),
        "purpose": "learn_from_negative_result_not_search_favorable_window",
        "lifecycle": LIFECYCLE,
        "corpus_id": corpus.get("corpus_id"),
        "corpus_sha256": corpus.get("corpus_sha256"),
        "primary_delta_info": delta,
        "folds": [
            {
                "fold": f.get("fold"),
                "delta_info": f.get("delta_info"),
                "clean_improvement": f.get("clean_improvement"),
            }
            for f in (decisive.get("folds") or [])
        ],
        "categories": categories,
        "dominant_explanation": dominant,
        "conclusion": (
            "Electrical features harmed Master one-step prediction on held-out "
            "sessions. Likely because rails largely restate load already inside "
            "Master, Ohm-derived I is dependent, and the blend added noise. "
            "Do not reopen the same construction; if revisiting electrical, target "
            "direct electrical outcomes (E=∫P dt, peak power, overload), not Master S_n."
        ),
        "not_done": "another_admission_or_decisive_campaign_same_meters",
    }
    path = OUT_DIR / "prediction_postmortem_latest.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = OUT_DIR / "prediction_postmortem_latest.md"
    md.write_text(
        "\n".join(
            [
                "# Electrical→Master prediction postmortem",
                "",
                f"- **Lifecycle:** `{LIFECYCLE}`",
                f"- **Primary Δ_info:** {delta}",
                f"- **Dominant explanation:** {dominant}",
                f"- **Corpus:** {corpus.get('corpus_id')} sha256=`{corpus.get('corpus_sha256')}`",
                "",
                "## Categories inspected",
                "",
                f"- **Redundancy:** corr(S_el, Master)={corr_sel}; corr(S_el, w_cpu)={corr_sel_wc}",
                f"- **Noise:** ablation Δ_info all non-positive; combined={delta}",
                f"- **Lag:** best cross-corr lag={lag}",
                f"- **Derived dependence:** Ohm i_gpu samples={derived_n}; independent claims={independent_claims}",
                "",
                "## Conclusion",
                "",
                report["conclusion"],
                "",
            ]
        ),
        encoding="utf-8",
    )
    report["artifact_json"] = str(path).replace("\\", "/")
    report["artifact_md"] = str(md).replace("\\", "/")
    return report


def update_authoritative(
    *,
    corpus: dict[str, Any],
    post: dict[str, Any],
) -> dict[str, Any]:
    decisive = {}
    if DECISIVE_JSON.is_file():
        decisive = json.loads(DECISIVE_JSON.read_text(encoding="utf-8"))
    stamp = policy_stamp()
    decisive.update(
        {
            "lifecycle": LIFECYCLE,
            "rail_role": RAIL_ROLE,
            "prediction_branch": "closed_negative_result",
            "authoritative": True,
            "frozen_at": _utc(),
            "corpus_id": corpus.get("corpus_id"),
            "corpus_sha256": corpus.get("corpus_sha256"),
            "workload_composition": corpus.get("workload_composition"),
            "software_versions": corpus.get("software_versions"),
            "policy": stamp,
            "postmortem_ref": post.get("artifact_json"),
            "dominant_explanation": post.get("dominant_explanation"),
            "admission_granted": False,
            "electrical_in_A_t": False,
            "master_writes_disabled": True,
            "routing_behavior_disabled": True,
            "predictor_operational": False,
            "note": (
                "CLOSED: rejected_operational_use. Rails remain observe_only_diagnostics. "
                "Authoritative with role_decision_latest. Do not reopen same construction."
            ),
        }
    )
    DECISIVE_JSON.write_text(json.dumps(decisive, indent=2), encoding="utf-8")
    DECISIVE_MD.write_text(
        "\n".join(
            [
                "# Decisive electrical evidence (AUTHORITATIVE — CLOSED)",
                "",
                f"- **Lifecycle:** `{LIFECYCLE}`",
                f"- **Rail role:** `{RAIL_ROLE}`",
                f"- **Outcome:** {decisive.get('outcome')}",
                f"- **Disposition:** {decisive.get('disposition')}",
                f"- **Δ_info (combined):** {(decisive.get('decision_evidence') or {}).get('delta_info')}",
                f"- **Corpus:** {corpus.get('corpus_id')} (`{corpus.get('corpus_sha256')}`)",
                f"- **Workloads:** {corpus.get('workload_composition')}",
                f"- **Admission / A(t) / predictor:** false",
                "",
                "Prediction branch closed with negative result. Diagnostics only.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    role = {
        "ok": True,
        "at": _utc(),
        "authoritative": True,
        "lifecycle": LIFECYCLE,
        "rail_role": RAIL_ROLE,
        "prediction_branch": "closed_negative_result",
        "outcome": "unstable_or_misleading_signal",
        "disposition": "reject_operational_use",
        "admission_granted": False,
        "electrical_in_A_t": False,
        "master_writes_disabled": True,
        "routing_behavior_disabled": True,
        "predictor_operational": False,
        "policy": stamp,
        "evidence": {
            "source": "decisive_evidence_latest",
            "delta_info": (decisive.get("decision_evidence") or {}).get("delta_info"),
            "corpus_sha256": corpus.get("corpus_sha256"),
            "postmortem": post.get("dominant_explanation"),
        },
        "note": (
            "Final role: reject operational use for prediction/Master/routing. "
            "Retain observe_only_diagnostics for rails. Reopen only under REOPEN_CONDITIONS."
        ),
        "next": "return_focus_to_proven_rid_channels",
        "proven_plant_focus": stamp["proven_plant_focus"],
        "next_experiment_hint": stamp["next_experiment_hint"],
    }
    ROLE_JSON.write_text(json.dumps(role, indent=2), encoding="utf-8")
    ROLE_MD.write_text(
        "\n".join(
            [
                "# Electrical lane role decision (AUTHORITATIVE — CLOSED)",
                "",
                f"- **Lifecycle:** `{LIFECYCLE}`",
                f"- **Rail role:** `{RAIL_ROLE}`",
                f"- **Outcome:** reject operational use (prediction)",
                f"- **Admission granted:** false",
                f"- **Electrical in A(t):** false",
                f"- **Predictor operational:** false",
                "",
                role["note"],
                "",
            ]
        ),
        encoding="utf-8",
    )

    closed = {
        "ok": True,
        "at": _utc(),
        "lifecycle": LIFECYCLE,
        "rail_role": RAIL_ROLE,
        "prediction_branch": "closed_negative_result",
        "policy": stamp,
        "corpus_id": corpus.get("corpus_id"),
        "corpus_sha256": corpus.get("corpus_sha256"),
        "delta_info": (decisive.get("decision_evidence") or {}).get("delta_info"),
        "authoritative_artifacts": stamp["authoritative_artifacts"],
        "immediate_move": (
            "close_prediction_branch → retain_diagnostic_observer → "
            "document_negative_evidence → return_focus_to_proven_RID_channels"
        ),
    }
    cpath = OUT_DIR / "CLOSED_PREDICTION_BRANCH.json"
    cpath.write_text(json.dumps(closed, indent=2), encoding="utf-8")

    # Permanently disable canary flag file
    (OUT_DIR / "CANARY_ENABLE.json").write_text(
        json.dumps(
            {
                "flag": "rid_electrical_master_canary_v1",
                "enabled": False,
                "permanently_disabled": True,
                "lifecycle": LIFECYCLE,
                "at": _utc(),
                "reason": "decisive_negative_delta_info",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT_DIR / "ADVISORY_ROUTE_ENABLE.json").write_text(
        json.dumps(
            {
                "flag": "rid_electrical_advisory_route_v1",
                "enabled": False,
                "permanently_disabled": True,
                "lifecycle": LIFECYCLE,
                "at": _utc(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Multiwindow gate: closed, not eligible
    multi = {
        "ok": True,
        "at": _utc(),
        "lifecycle": LIFECYCLE,
        "lane_advancement_eligible": False,
        "supports_admission_review": False,
        "admission_granted": False,
        "electrical_in_A_t": False,
        "prediction_branch": "closed_negative_result",
        "rule": (
            "Prediction branch closed after decisive negative Δ_info. "
            "Multi-window advancement is obsolete for Master electrical weight."
        ),
    }
    (OUT_DIR / "multiwindow_gate_latest.json").write_text(
        json.dumps(multi, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "multiwindow_gate_latest.md").write_text(
        "# Multi-window gate — CLOSED\n\n"
        f"Lifecycle `{LIFECYCLE}`. Lane advancement eligible: false.\n",
        encoding="utf-8",
    )

    return closed


def main() -> int:
    if not DECISIVE_JSON.is_file():
        print("missing decisive_evidence_latest.json", file=sys.stderr)
        return 1
    decisive = json.loads(DECISIVE_JSON.read_text(encoding="utf-8"))
    corpus = freeze_corpus()
    post = postmortem(corpus, decisive)
    closed = update_authoritative(corpus=corpus, post=post)
    print(json.dumps(closed, indent=2), flush=True)
    print(json.dumps({"corpus_sha256": corpus["corpus_sha256"], "n": corpus["n_sessions"]}, indent=2))
    print(json.dumps({"postmortem": post.get("dominant_explanation"), "delta": post.get("primary_delta_info")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
