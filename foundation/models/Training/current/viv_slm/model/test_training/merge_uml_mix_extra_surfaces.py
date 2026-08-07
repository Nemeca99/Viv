#!/usr/bin/env python3
"""Merge hard-OOD / real-heldout surfaces into the permanent mix-bank extras catalog.

Writes ``data/uml_mix_extra_surfaces/surfaces.json`` consumed by
``build_uml_equation_mix_dataset.py`` on rebuild. Does NOT rebuild the tensor bank
and does NOT auto-promote federation composites.

Sources (if present):
- real heldout set_a / set_b
- OOD probe surfaces.json
- optional fresh hard procedural surfaces (``--hard-n``)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
for p in (FOUNDATION, MODEL, SANDBOX):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import build_uml_equation_mix_dataset as mix_build  # noqa: E402
import run_uml_ood_probe as ood  # noqa: E402
from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402
from sandbox_codex_identity import resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

OUT_DIR = SANDBOX / "data" / "uml_mix_extra_surfaces"
BANK_SURFACES = SANDBOX / "data" / "uml_equation_mix_v1" / "surfaces.json"
HELDOUT_A = SANDBOX / "data" / "uml_real_heldout_v1" / "set_a.json"
HELDOUT_B = SANDBOX / "data" / "uml_real_heldout_v1" / "set_b.json"
OOD_SURFACES = SANDBOX / "data" / "uml_ood_probe_v1" / "surfaces.json"
RECEIPT = SANDBOX / "runs" / "uml_mix_extra_surfaces_latest.json"


def _load_list(path: Path) -> list[str]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [str(x) for x in payload if str(x).strip()]
    surfaces = payload.get("surfaces") if isinstance(payload, dict) else None
    if isinstance(surfaces, list):
        return [str(x) for x in surfaces if str(x).strip()]
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hard-n", type=int, default=256, help="Fresh hard procedural surfaces to add")
    ap.add_argument("--hard-seed", type=int, default=424242)
    ap.add_argument(
        "--include-bank-dupes",
        action="store_true",
        help="Keep surfaces already in uml_equation_mix_v1 (default: skip bank dupes)",
    )
    ap.add_argument(
        "--no-heldout",
        action="store_true",
        help="Skip real-heldout set_a/set_b",
    )
    ap.add_argument(
        "--no-ood-probe",
        action="store_true",
        help="Skip existing OOD probe surfaces.json",
    )
    args = ap.parse_args(argv)

    tok = CharacterTokenizer.from_manifest(resolve_codex_dataset("v61")[1])
    vocab = set(tok.vocab)
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    bank = set(_load_list(BANK_SURFACES))
    existing = _load_list(OUT_DIR / "surfaces.json")

    seen: set[str] = set()
    merged: list[str] = []
    sources: dict[str, int] = {}

    def add_many(raws: list[str], source: str) -> int:
        n = 0
        for raw in raws:
            surface = mix_build._clean_surface(raw, vocab)
            if len(surface) < 3 or surface in seen:
                continue
            if not args.include_bank_dupes and surface in bank:
                continue
            # Seal must round-trip before permanent bank admission.
            try:
                eqs = reg.encode_text(surface)
                if not eqs or reg.decode_equations(eqs) != surface:
                    continue
            except Exception:
                continue
            seen.add(surface)
            merged.append(surface)
            n += 1
        sources[source] = n
        return n

    add_many(existing, "prior_catalog")
    if not args.no_heldout:
        add_many(_load_list(HELDOUT_A), "real_heldout_set_a")
        add_many(_load_list(HELDOUT_B), "real_heldout_set_b")
    if not args.no_ood_probe:
        add_many(_load_list(OOD_SURFACES), "ood_probe_surfaces")
    if int(args.hard_n) > 0:
        hard = ood._synth_surfaces(
            tok,
            set(seen) | bank,
            n=int(args.hard_n),
            seed=int(args.hard_seed),
            hard=True,
        )
        add_many(hard, "hard_procedural")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    catalog = {
        "schema_version": "uml_mix_extra_surfaces_v1",
        "count": len(merged),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "bank_surfaces_at_merge": len(bank),
        "note": (
            "Consumed by build_uml_equation_mix_dataset._phrases before Codex mining. "
            "Rebuild bank explicitly; this script only updates the extras catalog."
        ),
        "surfaces": merged,
    }
    (OUT_DIR / "surfaces.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    receipt = {
        "schema_version": "uml_mix_extra_surfaces_merge_v1",
        "status": "PASS",
        "finished_at": catalog["built_at"],
        "count": len(merged),
        "sources": sources,
        "catalog": str(OUT_DIR / "surfaces.json").replace("\\", "/"),
        "rebuild_hint": "L:\\Continue\\.venv\\Scripts\\python.exe build_uml_equation_mix_dataset.py",
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"UML_MIX_EXTRA_SURFACES_PASS count={len(merged)} sources={sources} "
        f"catalog={OUT_DIR / 'surfaces.json'}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
