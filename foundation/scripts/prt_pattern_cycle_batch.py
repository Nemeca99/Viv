#!/usr/bin/env python3
"""Bounded PRT cycle batch to sharpen act-conditioned pattern priors."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.prt_cycle import ensure_pre_prt_backup, run_cycle  # noqa: E402
from lib.prt_pattern_frame import empirical_act_deltas, empirical_life_survival  # noqa: E402


def _life_convergence(row: dict) -> dict | None:
    act = row.get("act") or {}
    if not isinstance(act, dict) or act.get("act") != "life":
        return None
    score = row.get("score") or {}
    stab = score.get("stability_label")
    task = (score.get("task_score") or {}).get("label")
    if stab is None or task is None:
        return None
    return {
        "stability": stab,
        "task": task,
        "combined": score.get("label"),
        "both_reward": stab == "REWARD" and task == "REWARD",
        "both_non_punish": stab != "PUNISH" and task != "PUNISH",
        "frac_error": (score.get("task_score") or {}).get("frac_error"),
        "pattern": ((act.get("life") or {}).get("before") or {}).get("pattern"),
        "pred_live": ((row.get("predict") or {}).get("prediction") or {}).get("predicted_live_cells"),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--observe", type=int, default=10)
    p.add_argument("--speak", type=int, default=5)
    p.add_argument("--life", type=int, default=5)
    p.add_argument("--pulse", type=int, default=0)
    p.add_argument("--settle", type=float, default=2.0)
    p.add_argument("--scaffold-phase", type=int, default=None, choices=[1, 2, 3])
    p.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "artifacts" / "audit" / "prt_pattern_cycles_batch.json",
    )
    args = p.parse_args()

    ensure_pre_prt_backup()
    plan = [
        ("observe", max(0, args.observe), args.settle),
        ("speak", max(0, args.speak), max(args.settle, 2.5)),
        ("life", max(0, args.life), max(args.settle, 2.5)),
        ("pulse", max(0, args.pulse), max(args.settle, 2.5)),
    ]
    rows: list[dict] = []
    life_conv: list[dict] = []
    self_emit_hits = 0
    self_emit_n = 0
    t0 = time.time()
    print(f"START pattern-cycle batch {plan} scaffold_phase={args.scaffold_phase}", flush=True)

    for act, n, settle in plan:
        for i in range(n):
            row = run_cycle(
                act=act,
                settle_s=settle,
                skip_model_predict=False,
                life_round=i,
                scaffold_phase=args.scaffold_phase,
            )
            pred = (row.get("predict") or {}).get("prediction") or {}
            score = row.get("score") or {}
            emit = row.get("self_emit") or pred.get("self_emit") or {}
            blanked = list((row.get("scaffold") or {}).get("blanked") or [])
            if blanked:
                self_emit_n += 1
                if emit.get("self_emit_ok") or emit.get("all_blanked_self_emitted"):
                    self_emit_hits += 1
            summary = {
                "i": i + 1,
                "act": act,
                "ok": row.get("ok"),
                "excluded": row.get("excluded"),
                "label": score.get("label"),
                "stability_label": score.get("stability_label"),
                "triad_complete": pred.get("triad_complete"),
                "parse": pred.get("parse"),
                "prior_filled": bool(pred.get("prior_filled")),
                "scaffold_phase": row.get("scaffold_phase"),
                "blanked": blanked,
                "self_emit_ok": bool(emit.get("self_emit_ok") or emit.get("all_blanked_self_emitted")),
                "structure_ok": score.get("structure_ok"),
                "version": row.get("version"),
            }
            lc = _life_convergence(row)
            if lc:
                summary["life_convergence"] = {
                    "both_reward": lc["both_reward"],
                    "both_non_punish": lc["both_non_punish"],
                    "stability": lc["stability"],
                    "task": lc["task"],
                    "frac_error": lc["frac_error"],
                    "pattern": lc["pattern"],
                }
                life_conv.append(lc)
            rows.append(summary)
            print(json.dumps(summary), flush=True)
            if act == "speak":
                try:
                    viv = _ROOT.parent
                    if str(viv) not in sys.path:
                        sys.path.insert(0, str(viv))
                    from voice_core.hf_lora import unload

                    unload()
                    time.sleep(3.0)
                except Exception:  # noqa: BLE001
                    pass
            elif act == "life":
                time.sleep(1.0)

    elapsed = round(time.time() - t0, 1)
    by_act: dict[str, dict] = {}
    for act in ("observe", "speak", "life", "pulse"):
        subset = [r for r in rows if r["act"] == act]
        labels = Counter(r.get("label") for r in subset)
        by_act[act] = {
            "n": len(subset),
            "labels": dict(labels),
            "triad_complete": sum(1 for r in subset if r.get("triad_complete")),
            "prior_filled": sum(1 for r in subset if r.get("prior_filled")),
            "self_emit_ok": sum(1 for r in subset if r.get("self_emit_ok")),
            "ok": sum(1 for r in subset if r.get("ok")),
        }
    all_labels = Counter(r.get("label") for r in rows)
    deltas = empirical_act_deltas()
    n_life = max(len(life_conv), 1)
    convergence = {
        "n": len(life_conv),
        "both_reward": sum(1 for x in life_conv if x.get("both_reward")),
        "both_non_punish": sum(1 for x in life_conv if x.get("both_non_punish")),
        "both_reward_rate": round(sum(1 for x in life_conv if x.get("both_reward")) / n_life, 4),
        "both_non_punish_rate": round(
            sum(1 for x in life_conv if x.get("both_non_punish")) / n_life, 4
        ),
        "mean_live_frac_error": round(
            sum(float(x.get("frac_error") or 0) for x in life_conv) / n_life, 4
        )
        if life_conv
        else None,
        "life_survival_priors": empirical_life_survival(),
        "detail": life_conv,
    }
    out = {
        "ok": True,
        "elapsed_s": elapsed,
        "n": len(rows),
        "scaffold_phase": args.scaffold_phase,
        "labels": dict(all_labels),
        "reward_rate": round(all_labels.get("REWARD", 0) / max(len(rows), 1), 4),
        "self_emit_rate": round(self_emit_hits / max(self_emit_n, 1), 4),
        "self_emit_n": self_emit_n,
        "self_emit_hits": self_emit_hits,
        "by_act": by_act,
        "life_loop_convergence": convergence,
        "act_deltas": {
            k: {
                kk: vv
                for kk, vv in v.items()
                if kk in ("master_rsr", "master_ltp", "master_rle", "master_s_n")
            }
            for k, v in deltas.items()
        },
        "cycles": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    slim_conv = {k: convergence[k] for k in convergence if k != "detail"}
    print(
        "SUMMARY",
        json.dumps(
            {
                "elapsed_s": out["elapsed_s"],
                "n": out["n"],
                "scaffold_phase": out["scaffold_phase"],
                "labels": out["labels"],
                "reward_rate": out["reward_rate"],
                "self_emit_rate": out["self_emit_rate"],
                "self_emit_hits": out["self_emit_hits"],
                "self_emit_n": out["self_emit_n"],
                "by_act": out["by_act"],
                "life_loop_convergence": slim_conv,
            },
            indent=2,
            default=str,
        ),
        flush=True,
    )
    print("WROTE", args.out, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
