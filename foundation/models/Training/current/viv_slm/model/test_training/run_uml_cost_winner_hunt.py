#!/usr/bin/env python3
"""Hunt real cost-winners for persistent composite promotion.

Breakthrough (binding):
  C_persistent < C_dynamic_foundational_federation
  AND C_persistent < C_mono_or_LIT
  plus Codex + authority (authority not auto-granted here).

Cost model (honest, replayable):
  - C_mono_LIT(dest)  = min symbolic cost among LIT + single-domain routes
  - C_mixed(F, dest)  = min symbolic cost among routes tagged federation F
  - C_persistent(F)   = C_mixed(F)          # fused specialist: no assembly tax
  - C_dynamic(F)      = C_mixed(F) + tax(F)  # assemble U + |F| foundations on demand
  - tax(F)            = assembly_tax_per_extra_domain * (len(F) - 1)
                        (U substrate always present; tax is multi-expert glue)

If tax=0, persistent cannot *strictly* beat dynamic on the same equation
(symbolic identity). The hard prerequisite is still C_mixed < C_mono_LIT.

This hunt does not invent equations outside the registry pool.
"""
from __future__ import annotations

import argparse
import json
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

GATE = SANDBOX / "uml_federation_promotion_gate.json"
LATTICE = SANDBOX / "uml_domain_expert_lattice.json"
RECIPE = SANDBOX / "uml_domain_expert_train_recipe.json"
OUT_JSON = SANDBOX / "runs" / "uml_cost_winner_hunt_latest.json"
OUT_MD = SANDBOX / "runs" / "uml_cost_winner_hunt_latest.md"

PAIRS = ("AS", "AM", "AD", "SM", "SD", "MD")
TRIPLES = ("ASM", "ASD", "AMD", "SMD")
ASMD = ("ASMD",)
ALL_LABELS = PAIRS + TRIPLES + ASMD


def _fed_label(domains: frozenset[str] | set[str]) -> str:
    return "".join(d for d in ("A", "S", "M", "D") if d in domains)


def _pool_for(entry: dict[str, Any]) -> list[tuple[str, int, str]]:
    exprs = [str(entry["canonical"])] + [str(e) for e in (entry.get("equivalents") or [])]
    rows: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    for expr in exprs:
        if expr in seen:
            continue
        seen.add(expr)
        try:
            cost = int(_symbolic_cost(expr))
        except Exception:
            continue
        doms = _domains_in_expr(expr)
        fed = _fed_label(doms) if doms else "LIT"
        rows.append((expr, cost, fed))
    return rows


def _tax(label: str, per_extra: int) -> int:
    # Extra arithmetic domains beyond the first; U is substrate (not taxed as peer).
    return max(0, int(per_extra) * max(0, len(label) - 1))


def hunt(*, assembly_tax_per_extra_domain: int) -> dict[str, Any]:
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    winners: list[dict[str, Any]] = []
    near_misses: list[dict[str, Any]] = []
    prereq_beats_mono = 0
    dest_n = 0
    by_fed: dict[str, dict[str, int]] = {
        lab: {
            "appear": 0,
            "beats_mono_lit": 0,
            "beats_dynamic": 0,
            "full_win": 0,
        }
        for lab in ALL_LABELS
    }

    for ch, entry in reg.entries.items():
        if not str(ch).isprintable() or ch in "\n\r\t":
            continue
        rows = _pool_for(entry)
        if not rows:
            continue
        dest_n += 1
        by_tag: dict[str, list[tuple[str, int]]] = {}
        for expr, cost, fed in rows:
            by_tag.setdefault(fed, []).append((expr, cost))

        mono_lit_costs = []
        for tag, items in by_tag.items():
            if tag == "LIT" or len(tag) == 1:
                mono_lit_costs.extend(c for _, c in items)
        if not mono_lit_costs:
            continue
        c_mono = min(mono_lit_costs)

        for lab in ALL_LABELS:
            items = by_tag.get(lab)
            if not items:
                continue
            by_fed[lab]["appear"] += 1
            best_expr, c_mixed = min(items, key=lambda t: (t[1], len(t[0]), t[0]))
            c_persistent = c_mixed
            c_dynamic = c_mixed + _tax(lab, assembly_tax_per_extra_domain)

            beats_mono = c_persistent < c_mono
            beats_dyn = c_persistent < c_dynamic
            if beats_mono:
                by_fed[lab]["beats_mono_lit"] += 1
                prereq_beats_mono += 1
            if beats_dyn:
                by_fed[lab]["beats_dynamic"] += 1

            row = {
                "dest": ch,
                "federation": f"U_{lab}",
                "label": lab,
                "best_expr": best_expr,
                "C_persistent": c_persistent,
                "C_dynamic": c_dynamic,
                "C_mono_LIT": c_mono,
                "assembly_tax": _tax(lab, assembly_tax_per_extra_domain),
                "beats_mono_LIT": beats_mono,
                "beats_dynamic": beats_dyn,
                "full_win": beats_mono and beats_dyn,
            }
            if row["full_win"]:
                by_fed[lab]["full_win"] += 1
                winners.append(row)
            elif beats_mono and not beats_dyn:
                near_misses.append({**row, "miss": "dynamic_tie_or_worse_tax0"})
            elif beats_dyn and not beats_mono:
                near_misses.append({**row, "miss": "mono_LIT_cheaper_or_equal"})

    # Cap near-miss samples for receipt size
    near_misses_sorted = sorted(
        near_misses,
        key=lambda r: (r["C_persistent"] - r["C_mono_LIT"], r["label"], r["dest"]),
    )[:40]

    n_full = len(winners)
    if n_full > 0:
        objective = "FOUND_COST_WINNER"
        note = (
            f"{n_full} destination×federation pairs clear both inequalities "
            f"at assembly_tax_per_extra_domain={assembly_tax_per_extra_domain}."
        )
    elif prereq_beats_mono == 0:
        objective = "BLOCKED_PREREQUISITE"
        note = (
            "No mixed route in the registry pool has C_mixed < C_mono_LIT. "
            "Persistent cannot win the breakthrough comparison until registry "
            "economics produce a mixed route cheaper than mono/LIT. "
            "Assembly tax alone cannot invent that."
        )
    else:
        objective = "BLOCKED_DYNAMIC"
        note = (
            f"{prereq_beats_mono} mixed routes beat mono/LIT, but none also beat "
            f"dynamic under tax={assembly_tax_per_extra_domain} "
            "(tax=0 makes persistent vs dynamic a non-strict identity)."
        )

    return {
        "objective": objective,
        "note": note,
        "n_destinations": dest_n,
        "n_full_wins": n_full,
        "n_prereq_beats_mono_lit_events": prereq_beats_mono,
        "assembly_tax_per_extra_domain": assembly_tax_per_extra_domain,
        "winners": winners[:50],
        "near_misses_sample": near_misses_sorted,
        "by_federation": by_fed,
        "cost_model": {
            "C_persistent": "C_mixed(F)",
            "C_dynamic": "C_mixed(F) + tax*(len(F)-1)",
            "C_mono_LIT": "min(LIT, single-domain)",
            "pool": "registry canonical + equivalents only (no invented eqs)",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tax",
        type=int,
        default=1,
        help="Assembly tax per extra arithmetic domain (default 1). Use 0 to show identity tie.",
    )
    parser.add_argument(
        "--tax-sweep",
        type=str,
        default="0,1,2,4",
        help="Comma list of tax values to summarize alongside primary --tax.",
    )
    args = parser.parse_args()

    primary = hunt(assembly_tax_per_extra_domain=int(args.tax))
    sweep = []
    for raw in str(args.tax_sweep).split(","):
        raw = raw.strip()
        if not raw:
            continue
        t = int(raw)
        h = hunt(assembly_tax_per_extra_domain=t)
        sweep.append(
            {
                "tax": t,
                "objective": h["objective"],
                "n_full_wins": h["n_full_wins"],
                "n_prereq_beats_mono_lit_events": h["n_prereq_beats_mono_lit_events"],
            }
        )

    finished = datetime.now(timezone.utc).isoformat()
    receipt = {
        "schema_version": "uml_cost_winner_hunt_v1",
        "status": "PASS",
        "objective": primary["objective"],
        "hypothesis": (
            "A real cost-winner exists in the registry pool under the breakthrough "
            "comparison (persistent < dynamic AND persistent < mono/LIT)."
        ),
        "hypothesis_supported": primary["objective"] == "FOUND_COST_WINNER",
        "finished_at": finished,
        "breakthrough_criterion": json.loads(GATE.read_text(encoding="utf-8")).get(
            "breakthrough_criterion"
        ),
        "primary": primary,
        "tax_sweep": sweep,
        "governance": (
            "0 winners is a valid success of restraint if the pool cannot clear "
            "mono/LIT. Do not invent equations to force a promotion."
        ),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    lines = [
        "# UML Cost-Winner Hunt",
        "",
        f"- Objective: **{primary['objective']}**",
        f"- Hypothesis supported: {receipt['hypothesis_supported']}",
        f"- {primary['note']}",
        f"- Destinations scanned: {primary['n_destinations']}",
        f"- Full wins (tax={args.tax}): {primary['n_full_wins']}",
        f"- Prereq events (mixed < mono/LIT): {primary['n_prereq_beats_mono_lit_events']}",
        "",
        "## Tax sweep",
    ]
    for row in sweep:
        lines.append(
            f"- tax={row['tax']}: {row['objective']} "
            f"full_wins={row['n_full_wins']} prereq={row['n_prereq_beats_mono_lit_events']}"
        )
    if primary["winners"]:
        lines.extend(["", "## Winners"])
        for w in primary["winners"][:20]:
            lines.append(
                f"- {w['dest']!r} {w['federation']}: "
                f"P={w['C_persistent']} D={w['C_dynamic']} M={w['C_mono_LIT']} "
                f"expr={w['best_expr']}"
            )
    else:
        lines.extend(
            [
                "",
                "## Read",
                "- Capability (15/15 temp) remains true.",
                "- Restraint (0 promotions) remains correct until mono/LIT is beaten honestly.",
                "- Next lever is registry/route economics, not another specialist accuracy pass.",
            ]
        )
    lines.extend(["", f"Receipt: `{OUT_JSON.as_posix()}`", ""])
    OUT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    # Sync gate + lattice winner count
    if GATE.is_file():
        gate = json.loads(GATE.read_text(encoding="utf-8"))
        gate["current_evidence"] = {
            "real_cost_winners": primary["n_full_wins"],
            "last_hunt": primary["objective"],
            "receipt": str(OUT_JSON).replace("\\", "/"),
            "updated_at": finished,
        }
        if "breakthrough_criterion" in gate:
            gate["breakthrough_criterion"]["real_cost_winners"] = primary["n_full_wins"]
        GATE.write_text(
            json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if LATTICE.is_file():
        lattice = json.loads(LATTICE.read_text(encoding="utf-8"))
        bc = lattice.get("persistence_policy", {}).get("breakthrough_criterion")
        if isinstance(bc, dict):
            bc["real_cost_winners"] = primary["n_full_wins"]
            bc["last_hunt"] = primary["objective"]
            bc["hunt_receipt"] = str(OUT_JSON).replace("\\", "/")
        lattice["cost_winner_hunt_latest"] = {
            "objective": primary["objective"],
            "n_full_wins": primary["n_full_wins"],
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
        recipe["last_objective"] = primary["objective"]
        recipe["cost_winner_hunt"] = {
            "objective": primary["objective"],
            "n_full_wins": primary["n_full_wins"],
            "receipt": str(OUT_JSON).replace("\\", "/"),
        }
        if primary["objective"] != "FOUND_COST_WINNER":
            recipe["next_action"] = (
                "Cost-winner hunt blocked at registry economics (mixed does not beat "
                "mono/LIT in pool). Do not promote. Optional: expand equivalents only "
                "when Nested-PEMDAS truthfully yields cheaper mixed forms — never invent."
            )
        RECIPE.write_text(
            json.dumps(recipe, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    print(
        f"UML_COST_WINNER_HUNT_{primary['objective']} "
        f"full_wins={primary['n_full_wins']} "
        f"prereq_mono={primary['n_prereq_beats_mono_lit_events']} "
        f"tax={args.tax}",
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
