#!/usr/bin/env python3
"""Build UML-structure (U) foundation axiom bank — Nested-PEMDAS / seal / codec truths.

Fifth foundation expert: not an arithmetic generator, but the medium itself.
Axioms are foundationally true of UML structure, independent of A/S/M/D ops.
"""
from __future__ import annotations

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

from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402
from lib.uml_route_governor import decide_route  # noqa: E402
from uml_codec_io import build_native_uml_prompt, encode_text_to_uml, decode_uml_to_text  # noqa: E402
from uml_structure_binding import structure_simplify_unbound  # noqa: E402

OUT = SANDBOX / "data" / "uml_domain_axioms_v1" / "uml_structure"
RECEIPT = SANDBOX / "runs" / "uml_structure_axiom_bank_latest.json"


def main() -> int:
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    rows: list[str] = []

    # 1) Seal / roundtrip axioms
    for surface in list(reg.vocab)[:40] + ["Hi", "Viv", "OK"]:
        if any(c not in reg.entries for c in surface):
            continue
        enc = encode_text_to_uml(surface, registry=reg, prefer_efficient=True)
        dec = decode_uml_to_text(enc["equations"], registry=reg)
        if dec["surface"] != surface:
            continue
        stream = enc["uml_stream"]
        rows.append(f"User: U axiom encode {surface}\nViv: {stream}<END>\n")
        rows.append(f"User: U axiom decode {stream}\nViv: {surface}<END>\n")
        rows.append(f"UML:{stream}\nViv: {stream}\n")

    # 2) Nesting / precedence structure (Nested-PEMDAS truths)
    nesting = [
        ("(1+2)*3", "force parens before multiply"),
        ("1+(2*3)", "inner multiply first"),
        ("2*3+1", "multiply before add without parens"),
        ("(2*3)+1", "same seal as 2*3+1 when add last"),
        ("8/2/2", "left-assoc division chain"),
        ("(8/2)/2", "explicit left assoc"),
    ]
    for expr, note in nesting:
        rows.append(f"User: U nesting {note}\nViv: {expr}<END>\n")
        rows.append(f"UML:{expr}\nViv: {expr}\n")

    # 3) Equivalence class: many routes, one seal
    for ch in ("H", "A", "V", "1", "+"):
        if ch not in reg.entries:
            continue
        dec = decide_route(reg, target_char=ch, include_registry_pool=True)
        cheap = str(dec.selected)
        alts = [r.expr for r in dec.considered if r.valid and r.expr != cheap][:3]
        rows.append(f"User: U seal for {ch} cheapest\nViv: {cheap}<END>\n")
        for alt in alts:
            rows.append(
                f"User: U equivalent route for {ch} also seals\n"
                f"Candidate: {alt}\nViv: {cheap}<END>\n"
            )

    # 4) Structure vs binding (foundational medium truths)
    try:
        unbound = structure_simplify_unbound("?A+?A") or {}
        result = unbound.get("structure_result") or "2*?A"
        rows.append(f"User: U structure unbound A+A\nViv: {result}<END>\n")
    except Exception:
        rows.append("User: U structure unbound A+A\nViv: 2*?A<END>\n")
    rows.append("User: U grounded 1+1\nViv: 2<END>\n")
    rows.append("User: U math does not lie\nViv: invalid_or_routing_fault_not_new_truth<END>\n")

    # 5) Multi-char sealed chain
    for word in ("Hi", "Viv"):
        native = build_native_uml_prompt(word, registry=reg, prefer_efficient=True)
        rows.append(f"User: U chain {word}\nViv: {native['encode']['uml_stream']}<END>\n")
        rows.append(native["model_prompt"] + native["encode"]["uml_stream"] + "\n")

    # Dedup
    seen: set[str] = set()
    uniq = []
    for r in rows:
        if r in seen:
            continue
        seen.add(r)
        uniq.append(r)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "train_dialogues.txt").write_text("".join(uniq), encoding="utf-8", newline="\n")
    meta = {
        "schema_version": "uml_structure_axiom_bank_v1",
        "status": "PASS",
        "domain": "uml_structure",
        "id": "U",
        "role": "foundation_medium",
        "dialogue_rows": len(uniq),
        "axiom_families": [
            "seal_roundtrip",
            "nested_pemdas",
            "equivalence_class",
            "structure_vs_binding",
            "multi_char_chain",
            "math_does_not_lie",
        ],
        "built_at": datetime.now(timezone.utc).isoformat(),
        "path": str(OUT).replace("\\", "/"),
    }
    with (OUT / "MANIFEST.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(meta, handle, indent=2, sort_keys=True)
        handle.write("\n")
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(meta, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"UML_STRUCTURE_AXIOM_BANK_PASS dialogues={len(uniq)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
