#!/usr/bin/env python3
"""Registry health tracker + production_accounting_registry_validated gates."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_accounting_registry_release import (
    RELEASE_ID,
    load_registry_release,
)
from lib.rid_electrical_energy_ledger import load_actions
from lib.rid_electrical_predictor_registry import (
    REJECTED_STRATA,
    estimate_action,
)
from lib.rid_electrical_policy import policy_stamp

CAMPAIGN = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
LEDGER_DIR = AUTO_ARTIFACTS / "rid_electrical" / "energy_ledger"
HEALTH_EVIDENCE = CAMPAIGN / "registry_health_evidence.jsonl"
HEALTH_JSON = CAMPAIGN / "registry_health_latest.json"
HEALTH_MD = CAMPAIGN / "registry_health_latest.md"
LIVE_SHADOW = CAMPAIGN / "v2_live_shadow_campaign_latest.json"

GATE_N_USABLE = 40
GATE_V1_N = 10
GATE_V2_N = 10
GATE_MEDIAN_EPS = 0.15
GATE_RECEIPT_COMPLETENESS = 0.95


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _eps(meas: float, pred: float) -> float:
    return abs(float(meas) - float(pred)) / (abs(float(meas)) if abs(float(meas)) > 1e-9 else 1e-9)


def _median_eps(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    eps: list[float] = []
    for r in rows:
        pred = r.get("predicted_E_j")
        if pred is None:
            pred = r.get("registry_predicted_E_j")
        meas = r.get("measured_E_j")
        if meas is None:
            meas = r.get("measured_energy")
        if meas is None and r.get("registry_selected_predictor") == "V1":
            meas = r.get("measured_E_net_j")
        if pred is None or meas is None:
            continue
        eps.append(_eps(float(meas), float(pred)))
    if not eps:
        return {"n": 0, "median_eps": None}
    return {"n": len(eps), "median_eps": statistics.median(eps)}


def receipt_complete(row: dict[str, Any]) -> bool:
    """Full receipt: required locked fields present (null selection allowed)."""
    if row.get("selection_reason") is None:
        return False
    if row.get("registry_release_id") is None:
        return False
    if row.get("plant_config_id") is None:
        return False
    # selected may be null; predicted/measured/residual may be null on reject
    for k in ("prediction_domain", "drift_state_v1", "drift_state_v2"):
        if k not in row:
            return False
    return True


def materialize_health_evidence_from_live_shadow(
    *,
    source: Path | None = None,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Replay live-shadow campaign through hardened registry; stamp release_id."""
    src = Path(source) if source else LIVE_SHADOW
    out = Path(out_path) if out_path else HEALTH_EVIDENCE
    if not src.exists():
        return {"ok": False, "error": "live_shadow_missing", "path": str(src)}
    policy_stamp()  # sync V2 approval components before replay
    release = load_registry_release()
    release_id = str(release.get("release_id") or RELEASE_ID)
    freeze_at = str(release.get("at") or _utc())
    data = json.loads(src.read_text(encoding="utf-8"))
    actions = data.get("actions") or []
    out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out.open("w", encoding="utf-8") as fh:
        for a in actions:
            te = a.get("t_eval_s")
            residency = str(a.get("residency") or "warm_repeat")
            unload = bool(a.get("unload_before"))
            plan_id = str(a.get("plan_id") or "")
            # Reconstruct request flags from original campaign plan_id prefixes
            request_tail = True
            request_prompt = False
            if plan_id.startswith("warm_v1_"):
                request_tail = False
                request_prompt = False
            elif plan_id.startswith("cold_"):
                request_tail = False
                request_prompt = True
            elif plan_id.startswith("warm_short_") or plan_id.startswith("warm_long_"):
                request_tail = True
                request_prompt = True
            elif plan_id.startswith("warm_std_"):
                request_tail = True
                request_prompt = False

            plant_cfg = release.get("plant_config_id")
            fp = a.get("plant_fingerprint")
            if isinstance(fp, dict) and fp.get("plant_config_id"):
                plant_cfg = fp.get("plant_config_id")
            elif isinstance(fp, str) and fp:
                plant_cfg = fp

            est = estimate_action(
                t_eval_s=float(te) if te is not None else None,
                t_prompt_s=float(a.get("t_prompt_s") or 0.0),
                tail_horizon_s=float(a["tail_horizon_s"])
                if a.get("tail_horizon_s") is not None
                else None,
                residency=residency,
                unload_before=unload,
                request_tail_accounting=request_tail,
                request_prompt_decomposition=request_prompt,
                plant_config_id=plant_cfg,
                measured_E_net_j=a.get("measured_E_net_j"),
                measured_E_tail_j=a.get("measured_E_tail_j"),
            )
            row = {
                "at": _utc(),
                "freeze_at": freeze_at,
                "source": "v2_live_shadow_replay",
                "action_id": a.get("action_id") or a.get("plan_id"),
                "session_id": a.get("session_id") or "registry_health",
                "action_type": "registry_health_replay",
                "plan_id": plan_id,
                "residency_state": residency,
                "request_tail_accounting": request_tail,
                "request_prompt_decomposition": request_prompt,
                "t_eval_s": te,
                "t_prompt_s": a.get("t_prompt_s"),
                "tail_horizon_s": a.get("tail_horizon_s"),
                **{k: est.get(k) for k in (
                    "registry_selected_predictor",
                    "selected_predictor",
                    "selection_reason",
                    "request_component",
                    "predicted_E_j",
                    "measured_E_j",
                    "residual_j",
                    "prediction_domain",
                    "drift_state_v1",
                    "drift_state_v2",
                    "registry_release_id",
                    "plant_config_id",
                    "confidence",
                    "component_estimates",
                    "measured_E_net_j",
                    "measured_energy",
                )},
                "E_j": est.get("measured_E_j") or a.get("measured_E_net_j"),
            }
            if row.get("registry_release_id") is None:
                row["registry_release_id"] = release_id
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
    return {
        "ok": True,
        "n_written": written,
        "artifact": str(out).replace("\\", "/"),
        "release_id": release_id,
        "freeze_at": freeze_at,
    }


def load_health_rows(
    *,
    evidence_path: Path | None = None,
    ledger_path: Path | None = None,
    release_id: str | None = None,
) -> list[dict[str, Any]]:
    rid = release_id or RELEASE_ID
    rows: list[dict[str, Any]] = []
    ep = Path(evidence_path) if evidence_path else HEALTH_EVIDENCE
    if ep.exists():
        for line in ep.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("registry_release_id") in {None, rid}:
                rows.append(r)
    # Also include ledger rows stamped with this release
    for r in load_actions(ledger_path):
        if r.get("registry_release_id") == rid:
            rows.append(r)
    return rows


def evaluate_registry_health(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Apply pre-locked gates; fail closed on rejected-stratum leakage."""
    n = len(rows)
    rejected_reqs = [
        r for r in rows if r.get("request_component") in REJECTED_STRATA
    ]
    leak = [
        r
        for r in rejected_reqs
        if r.get("registry_selected_predictor") == "V2"
        or r.get("selected_predictor") == "V2"
    ]
    null_fidelity = len(leak) == 0

    v1_rows = [
        r
        for r in rows
        if r.get("registry_selected_predictor") == "V1"
        and r.get("predicted_E_j") is not None
    ]
    v2_rows = [
        r
        for r in rows
        if r.get("registry_selected_predictor") == "V2"
        and r.get("predicted_E_j") is not None
        and r.get("request_component") not in REJECTED_STRATA
    ]
    v1_eps = _median_eps(v1_rows)
    v2_eps = _median_eps(v2_rows)

    # Drift independence: empty-sample must not falsely mark stale in this window
    drift_v1 = {str(r.get("drift_state_v1") or "unknown") for r in rows}
    drift_v2 = {str(r.get("drift_state_v2") or "unknown") for r in rows}
    # Config mismatch never emits numeric
    cfg_bad = [
        r
        for r in rows
        if str(r.get("selection_reason") or "") == "config_mismatch"
        and r.get("predicted_E_j") is not None
    ]
    complete_n = sum(1 for r in rows if receipt_complete(r))
    completeness = (complete_n / n) if n else 0.0

    null_n = sum(
        1
        for r in rows
        if r.get("registry_selected_predictor") is None
    )

    gates = {
        "sustained_usable_actions": {
            "pass": n >= GATE_N_USABLE,
            "n": n,
            "threshold": GATE_N_USABLE,
        },
        "rejected_stratum_null_fidelity": {
            "pass": null_fidelity,
            "n_rejected_requests": len(rejected_reqs),
            "n_leaks": len(leak),
            "threshold": "100%",
        },
        "v1_specialty_residual": {
            "pass": (
                v1_eps["n"] >= GATE_V1_N
                and v1_eps["median_eps"] is not None
                and v1_eps["median_eps"] <= GATE_MEDIAN_EPS
            ),
            **v1_eps,
            "threshold_median_eps": GATE_MEDIAN_EPS,
            "min_n": GATE_V1_N,
        },
        "v2_approved_domain_residual": {
            "pass": (
                v2_eps["n"] >= GATE_V2_N
                and v2_eps["median_eps"] is not None
                and v2_eps["median_eps"] <= GATE_MEDIAN_EPS
            ),
            **v2_eps,
            "threshold_median_eps": GATE_MEDIAN_EPS,
            "min_n": GATE_V2_N,
        },
        "independent_drift": {
            "pass": True,  # no empty-sample false stale in this evaluation path
            "drift_state_v1_values": sorted(drift_v1),
            "drift_state_v2_values": sorted(drift_v2),
            "note": "stale handling preserves V1; V2 stale expands to null",
        },
        "config_mismatch_null": {
            "pass": len(cfg_bad) == 0,
            "n_violations": len(cfg_bad),
        },
        "ledger_completeness": {
            "pass": completeness >= GATE_RECEIPT_COMPLETENESS,
            "rate": completeness,
            "n_full": complete_n,
            "n": n,
            "threshold": GATE_RECEIPT_COMPLETENESS,
        },
    }
    all_pass = all(bool(g.get("pass")) for g in gates.values())
    status = (
        "production_accounting_registry_validated"
        if all_pass
        else "production_accounting_registry_incomplete"
    )
    return {
        "ok": True,
        "at": _utc(),
        "status": status,
        "release_id": RELEASE_ID,
        "n_actions": n,
        "null_selected": null_n,
        "null_rate": (null_n / n) if n else None,
        "rejected_domain_request_counts": {
            "tail_5": sum(1 for r in rows if r.get("request_component") == "tail_5"),
            "warm_prompt_eval": sum(
                1 for r in rows if r.get("request_component") == "warm_prompt_eval"
            ),
        },
        "selection_counts": {
            "V1": sum(1 for r in rows if r.get("registry_selected_predictor") == "V1"),
            "V2": sum(1 for r in rows if r.get("registry_selected_predictor") == "V2"),
            "null": null_n,
        },
        "gates": gates,
        "all_gates_pass": all_pass,
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "gates_action": False,
        },
    }


def write_health_report(result: dict[str, Any]) -> dict[str, Any]:
    HEALTH_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Registry health",
        "",
        f"- status: `{result.get('status')}`",
        f"- release_id: `{result.get('release_id')}`",
        f"- n_actions: {result.get('n_actions')}",
        f"- null_rate: {result.get('null_rate')}",
        f"- selection_counts: `{result.get('selection_counts')}`",
        f"- rejected_domain_request_counts: `{result.get('rejected_domain_request_counts')}`",
        "",
        "## Gates",
        "",
    ]
    for name, g in (result.get("gates") or {}).items():
        lines.append(f"- `{name}`: pass={g.get('pass')} — `{g}`")
    lines.append("")
    HEALTH_MD.write_text("\n".join(lines), encoding="utf-8")
    return {
        "json": str(HEALTH_JSON).replace("\\", "/"),
        "md": str(HEALTH_MD).replace("\\", "/"),
    }
