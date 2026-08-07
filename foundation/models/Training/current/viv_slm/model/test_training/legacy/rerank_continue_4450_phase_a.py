#!/usr/bin/env python3
"""Re-score continue-4450 arms under Phase-A (acc-primary) gates and pin if warranted."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SANDBOX = Path(__file__).resolve().parents[1]  # legacy home: parents[1] = test_training/
RUNS = SANDBOX / "runs"
CONTINUE = RUNS / "rid_breakthrough_continue_4450_latest.json"
HYBRID = RUNS / "rid_breakthrough" / "hybrid_full"
EFF = SANDBOX / "checkpoints" / "efficient" / "specialist.pt"
DEEP = SANDBOX / "checkpoints" / "deep" / "specialist.pt"
OUT = RUNS / "acc99_phase_a_rerank_4450.json"

NLL_COLLAPSE = 0.02
ACC_GAP_MAX = 0.015


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _phase_a_accept(
    *,
    parent_eff: dict[str, float],
    parent_deep: dict[str, float],
    cand_eff: dict[str, float],
    cand_deep: dict[str, float],
    probes_ok: bool,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    min_parent = min(parent_eff["acc"], parent_deep["acc"])
    min_cand = min(cand_eff["acc"], cand_deep["acc"])
    if min_cand + 1e-12 < min_parent:
        reasons.append("min_acc_not_improved")
    if cand_eff["nll"] - parent_eff["nll"] > NLL_COLLAPSE:
        reasons.append("efficient_nll_collapse")
    if cand_deep["nll"] - parent_deep["nll"] > NLL_COLLAPSE:
        reasons.append("deep_nll_collapse")
    if abs(cand_eff["acc"] - cand_deep["acc"]) > ACC_GAP_MAX:
        reasons.append("lane_acc_gap")
    if not probes_ok:
        reasons.append("probe_collapse")
    return (len(reasons) == 0 and min_cand >= min_parent), reasons


def _probes_ok(probes: dict[str, Any] | None) -> bool:
    if not probes:
        return False
    for lane in ("efficient", "deep"):
        texts = probes.get(lane) or {}
        joined = " ".join(str(v) for v in texts.values()).lower()
        if "hello" not in joined and "aios" not in joined and "viv" not in joined:
            return False
        # Extreme garble heuristic
        if joined.count("<end>") > 40:
            return False
    return True


def main() -> int:
    payload = json.loads(CONTINUE.read_text(encoding="utf-8"))
    parent = payload.get("parent_metrics") or {}
    # Prefer hybrid_full metrics if embedded; else use continue parent_metrics.
    if not parent.get("efficient"):
        raise SystemExit("rerank_missing_parent_metrics")
    arms = list(payload.get("arms") or [])
    ranked: list[dict[str, Any]] = []
    for arm in arms:
        eff = arm["efficient"]
        deep = arm["deep"]
        ok, reasons = _phase_a_accept(
            parent_eff=parent["efficient"],
            parent_deep=parent["deep"],
            cand_eff=eff,
            cand_deep=deep,
            probes_ok=_probes_ok(arm.get("probes")),
        )
        ranked.append(
            {
                "arm_id": arm["arm_id"],
                "min_acc": min(eff["acc"], deep["acc"]),
                "sum_nll": eff["nll"] + deep["nll"],
                "phase_a_accept": ok,
                "reject_reasons": reasons,
                "efficient": eff,
                "deep": deep,
                "delta_vs_parent": arm.get("delta_vs_parent"),
            }
        )
    ranked.sort(key=lambda r: (-float(r["min_acc"]), float(r["sum_nll"])))
    winner = next((r for r in ranked if r["phase_a_accept"]), None)
    pin_policy = "retain_existing"
    pinned_from = None
    if winner is not None:
        # Continue winner already pinned by NLL policy; confirm Phase-A pin source.
        arm_dir = RUNS / "rid_breakthrough_continue_4450" / str(winner["arm_id"])
        eff_src = arm_dir / "efficient_final.pt"
        deep_src = arm_dir / "deep_final.pt"
        if eff_src.is_file() and deep_src.is_file():
            import shutil

            shutil.copy2(eff_src, EFF)
            shutil.copy2(deep_src, DEEP)
            pin_policy = "phase_a_pinned"
            pinned_from = str(winner["arm_id"])
        else:
            pin_policy = "accept_but_checkpoints_missing"
    summary = {
        "status": "PASS",
        "mode": "reach99_phase_a_rerank",
        "finished_at": _now(),
        "parent_metrics": parent,
        "nll_collapse_budget": NLL_COLLAPSE,
        "acc_gap_max": ACC_GAP_MAX,
        "ranked": ranked,
        "winner": winner,
        "pin_policy": pin_policy,
        "pinned_from": pinned_from,
        "note": "Phase A primary = min(acc); NLL is collapse guard only.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"PHASE_A_RERANK_PASS winner={None if winner is None else winner['arm_id']} "
        f"pin={pin_policy} min_acc={None if winner is None else round(winner['min_acc'], 6)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
