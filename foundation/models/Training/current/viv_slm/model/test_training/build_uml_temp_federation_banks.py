#!/usr/bin/env python3
"""Build temporary federation dialogue banks: U+<config> over mixed-op routes.

Covers:
  pairs  — AS, AM, AD, SM, SD, MD
  triples — ASM, ASD, AMD, SMD
  all_four — ASMD (optional; built when --include-asmd)

Each bank requires Nested-PEMDAS structure (U) plus the labeled arithmetic ops.
Temporary only — not persistent composites.
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

from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402
from lib.uml_route_governor import decide_route  # noqa: E402

OUT_ROOT = SANDBOX / "data" / "uml_temp_federations_v1"
RECEIPT = SANDBOX / "runs" / "uml_temp_federation_banks_latest.json"
LATTICE = SANDBOX / "uml_domain_expert_lattice.json"

LETTER_OPS = {"A": "+", "S": "-", "M": "*", "D": "/"}

PAIR_OPS = {
    "AS": set("+-"),
    "AM": set("+*"),
    "AD": set("+/"),
    "SM": set("-*"),
    "SD": set("-/"),
    "MD": set("*/"),
}

TRIPLE_OPS = {
    "ASM": set("+-*"),
    "ASD": set("+-/" ),
    "AMD": set("+*/"),
    "SMD": set("-*/"),
}

ASMD_OPS = {"ASMD": set("+-*/")}

ALL_OPS = {**PAIR_OPS, **TRIPLE_OPS, **ASMD_OPS}


def _ops_in(expr: str) -> set[str]:
    text = str(expr).replace("**", "*")
    return {op for op in "+-*/" if op in text}


def _config_ops(label: str) -> set[str]:
    if label not in ALL_OPS:
        raise KeyError(f"unknown_federation:{label}")
    return ALL_OPS[label]


def _mixed_ok(expr: str, label: str, *, min_ops: int) -> bool:
    need = _config_ops(label)
    found = _ops_in(expr)
    return bool(found) and found <= need and len(found) >= min_ops


def _mono_ok(expr: str, label: str) -> bool:
    need = _config_ops(label)
    found = _ops_in(expr)
    return bool(found) and found <= need


def _min_ops_for(label: str) -> int:
    n = len(label)  # A/S/M/D letters
    if n >= 3:
        return 2  # triples: at least two distinct ops; synthetics push toward 3
    return 2


def _templates(label: str) -> list[str]:
    table = {
        "AS": ["(3+2)-1", "(5-1)+2", "7-(2+1)"],
        "AM": ["(2+3)*4", "2*(3+1)", "(1+2)*3"],
        "AD": ["(6+2)/2", "(8/2)+1", "9/(1+2)"],
        "SM": ["(5-1)*2", "3*(4-1)", "(6-2)*3"],
        "SD": ["(8-2)/3", "(9/3)-1", "6/(4-1)"],
        "MD": ["(6*2)/3", "(8/2)*2", "3*(4/2)"],
        "ASM": ["((3+2)-1)*2", "(5-1)*2+3", "2*(4+1)-3"],
        "ASD": ["((8+4)-2)/2", "(9-3)/3+1", "(6+3)/(4-1)"],
        "AMD": ["((2+4)*3)/2", "(8/2)*3+1", "((1+3)*4)/2"],
        "SMD": ["((8-2)*3)/3", "(9/3)*(4-1)", "((6*2)-4)/2"],
        "ASMD": ["((3+5)-2)*2/2", "((8/2)+1)*3-1", "((4*3)-2)/2+1"],
    }
    return list(table.get(label, []))


def _synthetics(label: str) -> list[str]:
    out: list[str] = []
    for a in range(1, 8):
        for b in range(1, 5):
            for c in range(1, 5):
                if label == "AS":
                    out.extend([f"({a}+{b})-{c}", f"({a+b}-{b})+{c}"])
                elif label == "AM":
                    out.extend([f"({a}+{b})*{c}", f"{a}*({b}+{c})"])
                elif label == "AD" and c:
                    out.extend([f"({a}+{b})/{c}", f"({a*c}/{c})+{b}"])
                elif label == "SM":
                    out.extend([f"({a+b}-{b})*{c}", f"{a}*({b+c}-{c})"])
                elif label == "SD" and c:
                    left = a * c if a * c > b else a + c * b
                    out.extend([f"({left}-{b})/{c}", f"({a*c}/{c})-{min(b, a)}"])
                elif label == "MD" and c:
                    out.extend([f"({a}*{b})/{c}", f"({a*c}/{c})*{b}"])
                elif label == "ASM":
                    out.extend(
                        [
                            f"(({a}+{b})-{c})*{max(1, b)}",
                            f"({a}-{min(a, b)}+{c})*{b}",
                            f"{a}*({b}+{c})-{min(a, c)}",
                        ]
                    )
                elif label == "ASD" and c:
                    out.extend(
                        [
                            f"(({a}+{b})-{min(a, b)})/{c}",
                            f"({a*c}/{c}+{b})-{min(b, c)}",
                            f"({a}+{b*c})/{c}-{min(a, b)}",
                        ]
                    )
                elif label == "AMD" and c:
                    out.extend(
                        [
                            f"(({a}+{b})*{c})/{c}",
                            f"({a*c}/{c})*{b}+{c}",
                            f"(({a}+{c})*{b})/{max(1, b)}",
                        ]
                    )
                elif label == "SMD" and c:
                    out.extend(
                        [
                            f"(({a+b}-{b})*{c})/{c}",
                            f"({a*c}/{c})*{b}-{min(a, b)}",
                            f"(({a}*{b})-{min(a, b)})/{c}",
                        ]
                    )
                elif label == "ASMD" and c:
                    out.extend(
                        [
                            f"(({a}+{b})-{min(a, b)})*{c}/{c}",
                            f"(({a*c}/{c})+{b})*{max(1, b)}-{min(a, c)}",
                            f"(({a}+{c})*{b}-{min(a, b)})/{c}",
                        ]
                    )
    # Dedup preserve order
    seen: set[str] = set()
    uniq = [e for e in out if not (e in seen or seen.add(e))]
    return uniq


def build_federation(reg: UMLEquationRegistry, label: str) -> dict[str, Any]:
    rows: list[str] = []
    fed = f"U+{label}"
    min_ops = _min_ops_for(label)
    rows.append(f"User: {fed} structure seal required\nViv: nested_pemdas_seal_ok<END>\n")
    rows.append(f"User: {fed} reject malformed\nViv: invalid_route<END>\n")

    mixed = 0
    mono = 0
    for ch, entry in reg.entries.items():
        if not str(ch).isprintable() or ch in "\n\r\t":
            continue
        pool = [str(entry["canonical"])] + [str(e) for e in (entry.get("equivalents") or [])]
        mixed_exprs = [e for e in pool if _mixed_ok(e, label, min_ops=min_ops)]
        mono_exprs = [
            e for e in pool if _mono_ok(e, label) and not _mixed_ok(e, label, min_ops=min_ops)
        ]
        if mixed_exprs:
            mixed_exprs.sort(key=lambda e: (len(e), e))
            best = mixed_exprs[0]
            rows.append(f"User: {fed} mixed UML for {ch}\nViv: {best}<END>\n")
            rows.append(f"User: Prefer efficient UML for {ch}\nViv: {best}<END>\n")
            rows.append(f"UML:{best}\nViv: {best}\n")
            mixed += 1
        elif mono_exprs:
            mono_exprs.sort(key=lambda e: (len(e), e))
            best = mono_exprs[0]
            rows.append(f"User: {fed} domain UML for {ch}\nViv: {best}<END>\n")
            rows.append(f"UML:{best}\nViv: {best}\n")
            mono += 1
        if mixed + mono >= 120:
            break

    for expr in _templates(label):
        rows.append(f"User: {fed} nested {expr}\nViv: {expr}<END>\n")
        rows.append(f"UML:{expr}\nViv: {expr}\n")

    for expr in _synthetics(label):
        if not _mono_ok(expr, label):
            continue
        rows.append(f"User: {fed} drill {expr}\nViv: {expr}<END>\n")
        rows.append(f"UML:{expr}\nViv: {expr}\n")

    for ch in ("H", "A", "V"):
        if ch not in reg.entries:
            continue
        cheap = decide_route(reg, target_char=ch).selected
        rows.append(f"User: {fed} cheapest sealed for {ch}\nViv: {cheap}<END>\n")

    seen: set[str] = set()
    uniq = [r for r in rows if not (r in seen or seen.add(r))]
    out = OUT_ROOT / f"U_{label}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "train_dialogues.txt").write_text("".join(uniq), encoding="utf-8", newline="\n")
    meta = {
        "federation": fed,
        "label": label,
        "tier": (
            "all_four"
            if label == "ASMD"
            else ("triple" if label in TRIPLE_OPS else "pair")
        ),
        "ops": sorted(_config_ops(label)),
        "dialogue_rows": len(uniq),
        "mixed_chars": mixed,
        "mono_chars": mono,
        "temporary": True,
        "persistent": False,
        "path": str(out).replace("\\", "/"),
    }
    with (out / "MANIFEST.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(meta, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tier",
        choices=("pairs", "triples", "all", "asmd"),
        default="all",
        help="Which federation banks to rebuild (default: all pairs+triples).",
    )
    parser.add_argument(
        "--labels",
        type=str,
        default="",
        help="Comma list override (e.g. ASM,ASD). Ignores --tier when set.",
    )
    args = parser.parse_args()

    lattice = json.loads(LATTICE.read_text(encoding="utf-8"))
    labels_cfg = lattice["composition_unordered"]["labels"]
    if args.labels.strip():
        labels = [x.strip() for x in args.labels.split(",") if x.strip()]
    elif args.tier == "pairs":
        labels = list(labels_cfg["pairs"])
    elif args.tier == "triples":
        labels = list(labels_cfg["triples"])
    elif args.tier == "asmd":
        labels = list(labels_cfg["all_four"])
    else:
        labels = list(labels_cfg["pairs"]) + list(labels_cfg["triples"])

    for lab in labels:
        if lab not in ALL_OPS:
            raise ValueError(f"unknown_label:{lab}")

    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    metas = [build_federation(reg, lab) for lab in labels]
    receipt = {
        "schema_version": "uml_temp_federation_banks_v2",
        "status": "PASS",
        "temporary": True,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "tier": args.tier if not args.labels.strip() else "custom",
        "federations": metas,
        "total_dialogues": sum(int(m["dialogue_rows"]) for m in metas),
        "binding": "Each bank is U+<arith>; U substrate mandatory.",
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
        handle.write("\n")
    with (OUT_ROOT / "BUILD.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"UML_TEMP_FEDERATION_BANKS_PASS labels={len(metas)} "
        f"dialogues={receipt['total_dialogues']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
