#!/usr/bin/env python3
"""Promotion-gate pilot for temporary U+arith federations.

Tests whether temporary training success *scales* to persistent composites.

Gates (lattice persistence_policy):
  1. combination_frequency_high  — how often federation appears / is cheapest-mixed
  2. uml_cost_beats_alternatives — federation best cost vs proper-subset alternatives
  3. codex_hold_preserved        — from temporary federation receipts
  4. operator_or_authority_gate  — --promote required; default is audit-only

Hypothesis:
  Temporary PASS does not imply promotion. At scale, promotion should be sparse
  (or empty) unless frequency+cost concentrate on a few federations. Wholesale
  promotion of all 15 would be a warehouse failure mode.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
for p in (FOUNDATION, MODEL, SANDBOX):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from lib.uml_equation_registry import (  # noqa: E402
    SANDBOX96_ARTIFACT,
    UMLEquationRegistry,
    _domains_in_expr,
    _symbolic_cost,
)

LATTICE = SANDBOX / "uml_domain_expert_lattice.json"
RECIPE = SANDBOX / "uml_domain_expert_train_recipe.json"
GATE_CFG = SANDBOX / "uml_federation_promotion_gate.json"
OUT_JSON = SANDBOX / "runs" / "uml_federation_promotion_gate_latest.json"
OUT_MD = SANDBOX / "runs" / "uml_federation_promotion_gate_latest.md"
COMPOSITE_ROOT = SANDBOX / "checkpoints" / "composites"
TEMP_DIR = SANDBOX / "runs" / "uml_temp_federations"

PAIRS = ("AS", "AM", "AD", "SM", "SD", "MD")
TRIPLES = ("ASM", "ASD", "AMD", "SMD")
ASMD = ("ASMD",)
ALL_LABELS = PAIRS + TRIPLES + ASMD

RECEIPT_PATHS = (
    SANDBOX / "runs" / "uml_temp_federations_latest.json",
    SANDBOX / "runs" / "uml_temp_triple_federations_latest.json",
    SANDBOX / "runs" / "uml_temp_asmd_federation_latest.json",
)


def _fed_label(domains: frozenset[str] | set[str]) -> str:
    return "".join(d for d in ("A", "S", "M", "D") if d in domains)


def _proper_subsets(label: str) -> list[str]:
    letters = list(label)
    n = len(letters)
    out: list[str] = []
    for mask in range(1, (1 << n) - 1):
        sub = "".join(letters[i] for i in range(n) if mask & (1 << i))
        if sub:
            out.append(sub)
    return out


def _load_train_receipts() -> dict[str, dict[str, Any]]:
    by_label: dict[str, dict[str, Any]] = {}
    for path in RECEIPT_PATHS:
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("federations") or []:
            label = str(row.get("label") or row.get("pair") or "")
            if not label:
                fed = str(row.get("federation") or "")
                label = fed.replace("U_", "") if fed.startswith("U_") else fed
            if label:
                by_label[label] = row
    return by_label


def _default_gate_cfg() -> dict[str, Any]:
    return {
        "schema_version": "uml_federation_promotion_gate_v1",
        "hypothesis": (
            "Temporary federation PASS does not imply persistent promotion. "
            "Promotion must be sparse under frequency+cost; wholesale 15/15 is FAIL_SCALE."
        ),
        "thresholds": {
            "min_appear_rate": 0.08,
            "min_cheapest_mixed_rate": 0.03,
            "min_cost_win_rate": 0.55,
            "min_destinations_with_routes": 8,
            "require_codex_hold": True,
            "require_temp_uml_up": True,
            "max_auto_promote": 2,
        },
        "authority": {
            "default": "audit_only",
            "auto_promote_requires": ["--promote", "all_gates_pass", "within_max_auto_promote"],
        },
    }


def _ensure_gate_cfg() -> dict[str, Any]:
    if GATE_CFG.is_file():
        return json.loads(GATE_CFG.read_text(encoding="utf-8"))
    cfg = _default_gate_cfg()
    GATE_CFG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8", newline="\n")
    return cfg


def _scan_registry(reg: UMLEquationRegistry) -> dict[str, Any]:
    """Frequency + cost evidence across sealed destinations."""
    # Per destination: list of (expr, cost, federation)
    per_dest: dict[str, list[tuple[str, int, str]]] = {}
    for ch, entry in reg.entries.items():
        if not str(ch).isprintable() or ch in "\n\r\t":
            continue
        pool = [str(entry["canonical"])] + [str(e) for e in (entry.get("equivalents") or [])]
        rows: list[tuple[str, int, str]] = []
        seen: set[str] = set()
        for expr in pool:
            if expr in seen:
                continue
            seen.add(expr)
            try:
                cost = _symbolic_cost(expr)
            except Exception:
                continue
            doms = _domains_in_expr(expr)
            fed = _fed_label(doms) if doms else "LIT"
            rows.append((expr, int(cost), fed))
        if rows:
            per_dest[str(ch)] = rows

    n_dest = max(1, len(per_dest))
    stats: dict[str, dict[str, Any]] = {
        lab: {
            "appear_destinations": 0,
            "cheapest_mixed_wins": 0,
            "exact_cheapest_wins": 0,
            "cost_comparisons": 0,
            "cost_wins_vs_subsets": 0,
            "cost_ties_vs_subsets": 0,
            "best_costs": [],
            "subset_best_costs": [],
        }
        for lab in ALL_LABELS
    }

    for _ch, rows in per_dest.items():
        by_fed: dict[str, list[tuple[str, int]]] = {}
        for expr, cost, fed in rows:
            by_fed.setdefault(fed, []).append((expr, cost))

        min_cost = min(c for _, c, _ in rows)
        cheapest_feds = {fed for _, c, fed in rows if c == min_cost}
        mixed_cheapest = {f for f in cheapest_feds if len(f) >= 2}

        for lab in ALL_LABELS:
            if lab not in by_fed:
                continue
            stats[lab]["appear_destinations"] += 1
            best_f = min(c for _, c in by_fed[lab])
            stats[lab]["best_costs"].append(best_f)
            if lab in cheapest_feds:
                stats[lab]["exact_cheapest_wins"] += 1
            if lab in mixed_cheapest:
                stats[lab]["cheapest_mixed_wins"] += 1

            # Cost vs proper subsets present in this destination
            subset_costs = []
            for sub in _proper_subsets(lab):
                if sub in by_fed:
                    subset_costs.append(min(c for _, c in by_fed[sub]))
            # Also compare against mono letters and LIT if present
            for mono in lab:
                if mono in by_fed:
                    subset_costs.append(min(c for _, c in by_fed[mono]))
            if "LIT" in by_fed:
                subset_costs.append(min(c for _, c in by_fed["LIT"]))
            if not subset_costs:
                continue
            best_sub = min(subset_costs)
            stats[lab]["cost_comparisons"] += 1
            stats[lab]["subset_best_costs"].append(best_sub)
            if best_f < best_sub:
                stats[lab]["cost_wins_vs_subsets"] += 1
            elif best_f == best_sub:
                stats[lab]["cost_ties_vs_subsets"] += 1

    summary: dict[str, Any] = {}
    for lab, st in stats.items():
        appear = int(st["appear_destinations"])
        comps = int(st["cost_comparisons"])
        wins = int(st["cost_wins_vs_subsets"])
        ties = int(st["cost_ties_vs_subsets"])
        summary[lab] = {
            "appear_destinations": appear,
            "appear_rate": appear / n_dest,
            "cheapest_mixed_wins": int(st["cheapest_mixed_wins"]),
            "cheapest_mixed_rate": int(st["cheapest_mixed_wins"]) / n_dest,
            "exact_cheapest_wins": int(st["exact_cheapest_wins"]),
            "exact_cheapest_rate": int(st["exact_cheapest_wins"]) / n_dest,
            "cost_comparisons": comps,
            "cost_wins_vs_subsets": wins,
            "cost_ties_vs_subsets": ties,
            "cost_win_rate": (wins / comps) if comps else 0.0,
            "cost_win_or_tie_rate": ((wins + ties) / comps) if comps else 0.0,
            "mean_best_cost": (
                sum(st["best_costs"]) / len(st["best_costs"]) if st["best_costs"] else None
            ),
            "mean_subset_best_cost": (
                sum(st["subset_best_costs"]) / len(st["subset_best_costs"])
                if st["subset_best_costs"]
                else None
            ),
        }
    return {
        "n_destinations": len(per_dest),
        "by_federation": summary,
        "concentration": _concentration(summary),
    }


def _concentration(summary: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rates = sorted(
        ((lab, float(v["cheapest_mixed_rate"])) for lab, v in summary.items()),
        key=lambda x: -x[1],
    )
    total = sum(r for _, r in rates) or 1.0
    top3 = rates[:3]
    top3_share = sum(r for _, r in top3) / total
    nonzero = sum(1 for _, r in rates if r > 0)
    return {
        "nonzero_cheapest_mixed_federations": nonzero,
        "top3": [{"label": lab, "cheapest_mixed_rate": rate} for lab, rate in top3],
        "top3_share_of_mixed_wins": top3_share,
    }


def _evaluate_gates(
    *,
    scan: dict[str, Any],
    train: dict[str, dict[str, Any]],
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    th = cfg["thresholds"]
    rows: list[dict[str, Any]] = []
    by = scan["by_federation"]
    for lab in ALL_LABELS:
        st = by[lab]
        tr = train.get(lab) or {}
        codex_hold = bool(tr.get("codex_hold"))
        status_train = str(tr.get("status") or "MISSING")
        uml_up = float(tr.get("delta_uml_acc") or 0.0) > 0.01
        if "delta_uml_acc" not in tr and tr.get("start") and tr.get("after"):
            uml_up = float(tr["after"]["uml_acc"]) - float(tr["start"]["uml_acc"]) > 0.01
            codex_hold = bool(tr.get("codex_hold", False))

        g_freq = (
            float(st["appear_rate"]) >= float(th["min_appear_rate"])
            and float(st["cheapest_mixed_rate"]) >= float(th["min_cheapest_mixed_rate"])
            and int(st["appear_destinations"]) >= int(th["min_destinations_with_routes"])
        )
        g_cost = float(st["cost_win_rate"]) >= float(th["min_cost_win_rate"])
        g_codex = (not th["require_codex_hold"]) or (
            codex_hold and status_train in ("PASS", "HOLD_ONLY")
        )
        g_uml = (not th["require_temp_uml_up"]) or uml_up
        # Authority is external; record placeholder
        gates = {
            "frequency": g_freq,
            "cost": g_cost,
            "codex": g_codex,
            "temp_uml_lift": g_uml,
            "authority": False,  # set later if --promote and candidate
        }
        evidence_pass = g_freq and g_cost and g_codex and g_uml
        if evidence_pass:
            decision = "CANDIDATE"
        elif g_codex and g_uml and not (g_freq and g_cost):
            decision = "TRAIN_OK_PROMOTE_DENY"  # scales as temporary, not persistent
        elif not g_codex:
            decision = "DENY_CODEX"
        else:
            decision = "DENY"

        rows.append(
            {
                "federation": f"U_{lab}",
                "label": lab,
                "tier": (
                    "pair"
                    if lab in PAIRS
                    else ("triple" if lab in TRIPLES else "all_four")
                ),
                "decision": decision,
                "evidence_pass": evidence_pass,
                "gates": gates,
                "registry": st,
                "train": {
                    "status": status_train,
                    "codex_hold": codex_hold,
                    "delta_uml_acc": tr.get("delta_uml_acc"),
                    "ckpt": tr.get("ckpt"),
                    "ckpt_exists": (TEMP_DIR / f"temp_U_{lab}.pt").is_file(),
                },
            }
        )
    return rows


def _scale_verdict(rows: list[dict[str, Any]], scan: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """Does temporary success scale to persistent promotion?"""
    n = len(rows)
    candidates = [r for r in rows if r["decision"] == "CANDIDATE"]
    train_ok_deny = [r for r in rows if r["decision"] == "TRAIN_OK_PROMOTE_DENY"]
    max_auto = int(cfg["thresholds"]["max_auto_promote"])
    conc = scan["concentration"]

    if len(candidates) == n:
        scale = "FAIL_SCALE_WAREHOUSE"
        note = "All federations cleared frequency+cost — promotion would warehouse every combo."
    elif len(candidates) == 0 and len(train_ok_deny) >= n // 2:
        scale = "PASS_SCALE_TEMPORARY_DEFAULT"
        note = (
            "Temporary training succeeds broadly; frequency+cost deny persistent promotion. "
            "Scale favors assembling federations on demand, not storing all composites."
        )
    elif 0 < len(candidates) <= max_auto:
        scale = "PASS_SCALE_SPARSE_PROMOTION"
        note = (
            f"Sparse promotion set ({len(candidates)}/{n}) — temporary lattice scales by "
            "promoting only high-frequency/cost winners."
        )
    elif len(candidates) > max_auto:
        scale = "PASS_SCALE_SPARSE_CAPPED"
        note = (
            f"{len(candidates)} candidates exceed max_auto_promote={max_auto}; "
            "cap promotion and keep the rest temporary."
        )
    else:
        scale = "INCONCLUSIVE"
        note = "Mixed evidence; do not claim scale either way."

    return {
        "verdict": scale,
        "note": note,
        "n_candidates": len(candidates),
        "n_train_ok_promote_deny": len(train_ok_deny),
        "concentration": conc,
        "hypothesis_supported": scale.startswith("PASS_SCALE"),
    }


def main() -> int:
    cfg = _ensure_gate_cfg()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Authority gate: copy CANDIDATE (capped) ckpts into checkpoints/composites/.",
    )
    parser.add_argument(
        "--force-labels",
        type=str,
        default="",
        help="Comma labels to force-promote under --promote (still require codex hold).",
    )
    args = parser.parse_args()

    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    scan = _scan_registry(reg)
    train = _load_train_receipts()
    rows = _evaluate_gates(scan=scan, train=train, cfg=cfg)
    scale = _scale_verdict(rows, scan, cfg)

    # Rank candidates by cheapest_mixed_rate then cost_win_rate
    candidates = [r for r in rows if r["evidence_pass"]]
    candidates.sort(
        key=lambda r: (
            -float(r["registry"]["cheapest_mixed_rate"]),
            -float(r["registry"]["cost_win_rate"]),
            -float(r["registry"]["appear_rate"]),
            r["label"],
        )
    )
    max_auto = int(cfg["thresholds"]["max_auto_promote"])
    promote_set = [r["label"] for r in candidates[:max_auto]]
    force = {x.strip() for x in args.force_labels.split(",") if x.strip()}

    promoted: list[str] = []
    if args.promote:
        COMPOSITE_ROOT.mkdir(parents=True, exist_ok=True)
        for r in rows:
            lab = r["label"]
            allow = lab in promote_set or lab in force
            if not allow:
                continue
            if not r["train"].get("codex_hold"):
                r["gates"]["authority"] = False
                r["decision"] = "DENY_AUTHORITY_NO_CODEX"
                continue
            src = TEMP_DIR / f"temp_U_{lab}.pt"
            if not src.is_file():
                r["decision"] = "DENY_MISSING_CKPT"
                continue
            dest = COMPOSITE_ROOT / f"U_{lab}" / "specialist.pt"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            r["gates"]["authority"] = True
            r["decision"] = "PROMOTED"
            r["promoted_ckpt"] = str(dest).replace("\\", "/")
            promoted.append(str(dest).replace("\\", "/"))
    else:
        for r in rows:
            if r["evidence_pass"] and r["label"] in promote_set:
                r["decision"] = "CANDIDATE_AWAITING_AUTHORITY"

    # Recompute decision counts for receipt after authority pass
    n_cand = sum(1 for r in rows if "CANDIDATE" in r["decision"])
    n_promoted = sum(1 for r in rows if r["decision"] == "PROMOTED")
    n_deny_econ = sum(1 for r in rows if r["decision"] == "TRAIN_OK_PROMOTE_DENY")

    finished = datetime.now(timezone.utc).isoformat()
    objective = scale["verdict"]
    receipt = {
        "schema_version": "uml_federation_promotion_gate_v1",
        "status": "PASS",
        "objective": objective,
        "hypothesis": cfg["hypothesis"],
        "hypothesis_supported": scale["hypothesis_supported"],
        "finished_at": finished,
        "authority_invoked": bool(args.promote),
        "thresholds": cfg["thresholds"],
        "registry_scan": {
            "n_destinations": scan["n_destinations"],
            "concentration": scan["concentration"],
        },
        "scale": scale,
        "federations": rows,
        "promote_set_if_authority": promote_set,
        "promoted": promoted,
        "counts": {
            "n": len(rows),
            "candidates": n_cand,
            "promoted": n_promoted,
            "train_ok_promote_deny": n_deny_econ,
        },
        "binding": (
            "Promotion is conditional. Temporary lattice can be complete while "
            "persistent composites remain empty — that is a successful scale outcome."
        ),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    lines = [
        "# UML Federation Promotion Gate",
        "",
        f"- Scale verdict: **{objective}**",
        f"- Hypothesis supported: {scale['hypothesis_supported']}",
        f"- {scale['note']}",
        f"- Authority invoked: {bool(args.promote)}",
        f"- Candidates: {n_cand}  Promoted: {n_promoted}  Train-ok/promote-deny: {n_deny_econ}",
        "",
        "## Concentration (cheapest mixed)",
    ]
    for row in scan["concentration"]["top3"]:
        lines.append(f"- {row['label']}: cheapest_mixed_rate={row['cheapest_mixed_rate']:.4f}")
    lines.extend(["", "## Per federation"])
    for r in sorted(rows, key=lambda x: x["label"]):
        reg_s = r["registry"]
        lines.append(
            f"- U_{r['label']}: {r['decision']} "
            f"appear={reg_s['appear_rate']:.3f} "
            f"cheap_mixed={reg_s['cheapest_mixed_rate']:.3f} "
            f"cost_win={reg_s['cost_win_rate']:.3f} "
            f"codex={r['train']['codex_hold']}"
        )
    lines.extend(["", f"Receipt: `{OUT_JSON.as_posix()}`", ""])
    OUT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    # Update lattice + recipe
    lattice = json.loads(LATTICE.read_text(encoding="utf-8"))
    lattice["promotion_gate_latest"] = {
        "status": objective,
        "hypothesis_supported": scale["hypothesis_supported"],
        "candidates": [r["federation"] for r in rows if "CANDIDATE" in r["decision"]],
        "promoted": [r["federation"] for r in rows if r["decision"] == "PROMOTED"],
        "train_ok_promote_deny": n_deny_econ,
        "persistent_composites": n_promoted,
        "receipt": str(OUT_JSON).replace("\\", "/"),
        "updated_at": finished,
    }
    LATTICE.write_text(
        json.dumps(lattice, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    if RECIPE.is_file():
        recipe = json.loads(RECIPE.read_text(encoding="utf-8"))
        recipe["last_run"] = finished
        recipe["last_objective"] = objective
        recipe["promotion_gate"] = {
            "verdict": objective,
            "hypothesis_supported": scale["hypothesis_supported"],
            "promoted": promoted,
            "receipt": str(OUT_JSON).replace("\\", "/"),
        }
        if objective.startswith("PASS_SCALE"):
            recipe["next_action"] = (
                "Promotion gate supports temporary-default scale. "
                "Optional: thicken native snap-free bank, or --promote only sparse candidates."
            )
            recipe["binding_read"]["not_yet"] = (
                "Persistent composites remain gated. Native snap-free path still weak."
            )
        RECIPE.write_text(
            json.dumps(recipe, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    print(
        f"UML_PROMOTION_GATE_{objective} candidates={n_cand} "
        f"promoted={n_promoted} deny_econ={n_deny_econ} "
        f"authority={bool(args.promote)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main())
