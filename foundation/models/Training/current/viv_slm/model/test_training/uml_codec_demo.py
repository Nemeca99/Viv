#!/usr/bin/env python3
"""Operator-visible Enigma demo: words ↔ UML equation forms ↔ words + RID score."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]  # model→viv_slm→current→Training→models→foundation
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))
if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))

from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402
from lib.uml_route_governor import decide_route, govern_text_routes  # noqa: E402
from rid_pid import RIDMonitor  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="Viv")
    parser.add_argument("--registry", default=str(SANDBOX96_ARTIFACT))
    parser.add_argument(
        "--govern",
        action="store_true",
        help="Use generation-time route governor (cheapest valid path).",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="With --govern, pressure-sample routes instead of hard cheapest.",
    )
    parser.add_argument("--route-temperature", type=float, default=0.8)
    parser.add_argument(
        "--proposals",
        default="",
        help="Comma-separated proposed routes for first char (demo pressure).",
    )
    args = parser.parse_args()

    reg = UMLEquationRegistry.load(args.registry)
    text = "".join(ch for ch in args.text if ch in reg.entries)
    if not text:
        raise SystemExit("uml_codec_demo_no_vocab_chars")

    if args.govern:
        props = None
        if args.proposals.strip():
            first_props = [p.strip() for p in args.proposals.split(",") if p.strip()]
            props = [first_props] + [[] for _ in text[1:]]
        governed = govern_text_routes(
            reg,
            text,
            proposals_per_char=props,
            sample=bool(args.sample),
            temperature=float(args.route_temperature),
        )
        eqs = list(governed["routes"])
        decoded = str(governed["surface_out"])
        route_meta = {
            "mode": (
                "governed_pressure_sample"
                if args.sample
                else "governed_cheapest_valid"
            ),
            "temperature": governed.get("temperature"),
            "valid_counts": [d["valid_count"] for d in governed["decisions"]],
            "rejected_counts": [d["rejected_count"] for d in governed["decisions"]],
            "selected_costs": [d["selected_cost"] for d in governed["decisions"]],
            "first_decision": governed["decisions"][0] if governed["decisions"] else None,
        }
    else:
        eqs = reg.encode_text(text)
        decoded = reg.decode_equations(eqs)
        route_meta = {"mode": "registry_canonical_encode"}

    mon = RIDMonitor()
    s = mon.score_from_text(input_text=text, output_text=text, error=0.01, registry=reg)

    sample_ch = text[0]
    sample_row = reg.entries[sample_ch]
    live = decide_route(
        reg,
        target_char=sample_ch,
        proposals=[p.strip() for p in args.proposals.split(",") if p.strip()] or None,
        include_registry_pool=True,
    )
    payload = {
        "surface_in": text,
        "uml_equations": eqs,
        "surface_out": decoded,
        "roundtrip_ok": decoded == text,
        "schema_version": reg.schema_version,
        "route": route_meta,
        "live_route_pressure": {
            "selected": live.selected,
            "selected_cost": live.selected_cost,
            "valid_count": live.valid_count,
            "rejected_count": live.rejected_count,
            "top_weights": dict(
                sorted(live.pressure_weights.items(), key=lambda kv: -kv[1])[:5]
            ),
        },
        "sample_char": {
            "char": sample_ch,
            "value": sample_row["value"],
            "canonical": sample_row["canonical"],
            "equivalents_preview": list(sample_row.get("equivalents") or [])[:8],
        },
        "rid": mon.receipt(),
        "S_RID": s,
        "registry_sha256": reg.registry_sha256(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"UML_CODEC_DEMO_{'PASS' if decoded == text else 'FAIL'} S_RID={s:.6f}")
    return 0 if decoded == text else 1


if __name__ == "__main__":
    raise SystemExit(main())
