#!/usr/bin/env python3
"""Full cost-decomposition evidence campaign runner.

Runs families in locked order with rotated sessions (≥5 repeats), unload before
unload/reload cells, wired prompt overrides, and per-family artifacts.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_cost_decomposition_campaign.py --run-all
  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_cost_decomposition_campaign.py --run-family load_residency --sessions 5
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_cost_decomposition import (  # noqa: E402
    DECOMPOSITION_CELLS,
    FAMILY_ORDER,
    DecompositionCell,
    campaign_manifest,
    cells_for_family,
    prompt_for_variant,
)
from lib.rid_electrical_ledger_controls import ControlCell, run_controlled_v2  # noqa: E402
from lib.rid_electrical_policy import policy_stamp  # noqa: E402

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append_progress(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def session_orders_for_family(
    cells: list[DecompositionCell],
    *,
    n_sessions: int = 5,
) -> list[list[DecompositionCell]]:
    """Rotated cell orders: each cell once per session; n_sessions repeats."""
    if not cells:
        return []
    n = len(cells)
    orders: list[list[DecompositionCell]] = []
    for s in range(n_sessions):
        # Cyclic rotate + one swap for coverage diversity when n>=3
        rotated = cells[s % n :] + cells[: s % n]
        if n >= 3 and s % 2 == 1:
            rotated = list(rotated)
            rotated[0], rotated[1] = rotated[1], rotated[0]
        orders.append(list(rotated))
    return orders


def control_cell_from_decomp(c: DecompositionCell) -> ControlCell:
    return ControlCell(
        cell_id=c.cell_id,
        residency=c.residency,
        num_predict=int(c.num_predict),
        token_bucket=f"decomp_{c.family}",
        prompt=prompt_for_variant(c.prompt_variant),
    )


def _md_family(report: dict[str, Any]) -> str:
    lines = [
        f"# Decomposition family: `{report.get('family')}`",
        "",
        f"- at: `{report.get('at')}`",
        f"- sessions: `{report.get('n_sessions')}`",
        f"- n_actions: `{len(report.get('rows') or [])}`",
        f"- v2_fit_authorized: `{report.get('v2_fit_authorized')}`",
        "",
        "## Actions",
        "",
        "| session | order | cell | E_net_raw_j | E_generate_j | E_tail_j | eval_s |",
        "|---:|---:|---|---:|---:|---:|---:|",
    ]
    for r in report.get("rows") or []:
        infer = r.get("infer") or {}
        lines.append(
            f"| {r.get('session_i')} | {r.get('order_i')} | `{r.get('cell_id')}` | "
            f"{r.get('E_net_raw_j')} | {r.get('E_generate_j')} | {r.get('E_tail_j')} | "
            f"{infer.get('eval_duration_s')} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_family(
    family: str,
    *,
    n_sessions: int = 5,
    gap_s: float = 10.0,
) -> dict[str, Any]:
    cells = cells_for_family(family)
    if not cells:
        return {"ok": False, "error": "unknown_family", "family": family}

    orders = session_orders_for_family(cells, n_sessions=n_sessions)
    OUT.mkdir(parents=True, exist_ok=True)
    progress_path = OUT / f"decomp_{family}_progress.jsonl"
    progress_path.write_text("", encoding="utf-8")

    print(
        f"[decomp] family={family} sessions={n_sessions} cells={[c.cell_id for c in cells]}",
        flush=True,
    )

    rows: list[dict[str, Any]] = []
    for session_i, order in enumerate(orders, start=1):
        print(
            f"[decomp] === {family} session {session_i}/{n_sessions} "
            f"order={[c.cell_id for c in order]} ===",
            flush=True,
        )
        model_warm = False
        for order_i, dc in enumerate(order, start=1):
            need_unload = bool(dc.unload_before) or dc.residency == "cold_first"
            if need_unload:
                prep = True
            else:
                prep = not model_warm

            ctrl = control_cell_from_decomp(dc)
            print(
                f"[decomp] S{session_i} order{order_i}: {dc.cell_id} "
                f"prep={prep} unload={need_unload} prompt={dc.prompt_variant} "
                f"tail={dc.tail_tau_s}s",
                flush=True,
            )
            row = run_controlled_v2(
                ctrl,
                repeat_i=session_i,
                prep_residency=prep,
                tail_tau_s=float(dc.tail_tau_s),
            )
            row["session_i"] = session_i
            row["order_i"] = order_i
            row["decomp_family"] = family
            row["prompt_variant"] = dc.prompt_variant
            row["prompt_text_len"] = len(prompt_for_variant(dc.prompt_variant))
            row["unload_before"] = bool(dc.unload_before)
            row["target_eval_s"] = dc.target_eval_s
            row["tail_tau_s"] = float(dc.tail_tau_s)
            row["cell_id"] = dc.cell_id
            row["v2_fit_authorized"] = False
            rows.append(row)
            model_warm = True  # generate leaves model resident

            _append_progress(
                progress_path,
                {
                    "at": _utc(),
                    "family": family,
                    "session_i": session_i,
                    "order_i": order_i,
                    "cell_id": dc.cell_id,
                    "E_net_raw_j": row.get("E_net_raw_j"),
                    "E_generate_j": row.get("E_generate_j"),
                    "E_tail_j": row.get("E_tail_j"),
                    "eval_duration_s": (row.get("infer") or {}).get("eval_duration_s"),
                    "session_id": row.get("session_id"),
                },
            )
            print(
                f"[decomp] done E_gen={row.get('E_generate_j')} "
                f"E_net={row.get('E_net_raw_j')} E_tail={row.get('E_tail_j')} "
                f"dt={(row.get('infer') or {}).get('eval_duration_s')}",
                flush=True,
            )
            time.sleep(max(0.0, float(gap_s)))

    report = {
        "ok": True,
        "at": _utc(),
        "family": family,
        "n_sessions": n_sessions,
        "cell_ids": [c.cell_id for c in cells],
        "session_orders": [[c.cell_id for c in o] for o in orders],
        "rows": rows,
        "v2_fit_authorized": False,
        "refit_v1_forbidden": True,
        "policy": policy_stamp(),
    }
    jpath = OUT / f"decomp_{family}_latest.json"
    mpath = OUT / f"decomp_{family}_latest.md"
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
    mpath.write_text(_md_family(report), encoding="utf-8")
    report["artifact_json"] = str(jpath).replace("\\", "/")
    report["artifact_md"] = str(mpath).replace("\\", "/")
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-all", action="store_true", help="Run all families in locked order")
    p.add_argument("--run-family", type=str, default="", help="Run a single family")
    p.add_argument("--sessions", type=int, default=5)
    p.add_argument("--gap-s", type=float, default=10.0)
    p.add_argument("--manifest-only", action="store_true")
    args = p.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = campaign_manifest()
    manifest["at"] = _utc()
    manifest["policy"] = policy_stamp()
    mpath = OUT / "cost_decomposition_campaign_manifest.json"
    mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if args.manifest_only or (not args.run_all and not args.run_family):
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "manifest_only",
                    "families": manifest["families"],
                    "family_order": manifest["family_order"],
                    "n_cells": len(manifest["cells"]),
                    "artifact": str(mpath).replace("\\", "/"),
                    "v2_fit_authorized": False,
                },
                indent=2,
            )
        )
        return 0

    families = list(FAMILY_ORDER) if args.run_all else [args.run_family.strip()]
    summaries = []
    for fam in families:
        if fam not in {c.family for c in DECOMPOSITION_CELLS}:
            print(json.dumps({"error": "unknown_family", "family": fam}))
            return 1
        rep = run_family(fam, n_sessions=max(1, int(args.sessions)), gap_s=float(args.gap_s))
        if not rep.get("ok"):
            print(json.dumps(rep, indent=2))
            return 1
        summaries.append(
            {
                "family": fam,
                "n_rows": len(rep.get("rows") or []),
                "artifact_json": rep.get("artifact_json"),
                "artifact_md": rep.get("artifact_md"),
            }
        )

    wrap = {
        "ok": True,
        "at": _utc(),
        "mode": "run_all" if args.run_all else "run_family",
        "sessions": int(args.sessions),
        "families": summaries,
        "v2_fit_authorized": False,
        "refit_v1_forbidden": True,
        "manifest": str(mpath).replace("\\", "/"),
        "policy": policy_stamp(),
    }
    wpath = OUT / "decomp_campaign_run_latest.json"
    wpath.write_text(json.dumps(wrap, indent=2), encoding="utf-8")
    print(json.dumps(wrap, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
