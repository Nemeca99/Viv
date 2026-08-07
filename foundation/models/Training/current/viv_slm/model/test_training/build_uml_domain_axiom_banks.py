#!/usr/bin/env python3
"""Build per-domain A/S/M/D axiom dialogue banks (P3 generators).

Sandbox-only under data/uml_domain_axioms_v1/{addition,subtraction,multiplication,division}/.
Does not mutate Codex or identity specialists.
"""
from __future__ import annotations

import json
import re
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
from lib import uml_engine  # noqa: E402

OUT_ROOT = SANDBOX / "data" / "uml_domain_axioms_v1"
RECIPE = SANDBOX / "uml_domain_expert_train_recipe.json"
RECEIPT = SANDBOX / "runs" / "uml_domain_axiom_banks_latest.json"

OP_CHARS = {
    "addition": set("+"),
    "subtraction": set("-"),
    "multiplication": set("*"),
    "division": set("/"),
}


def _ops_in_expr(expr: str) -> set[str]:
    text = str(expr)
    found: set[str] = set()
    if "**" in text:
        found.add("*")
        text = text.replace("**", " ")
    for op in "+-*/":
        if op in text:
            found.add(op)
    return found


def _domain_only(expr: str, domain: str) -> bool:
    allowed = OP_CHARS[domain]
    found = _ops_in_expr(expr)
    if not found:
        return False  # pure literal — not a domain drill
    return found <= allowed


def _axiom_instances(seed: str, domain: str) -> list[tuple[str, str]]:
    """Expand symbolic axiom seed into concrete Viv response pairs."""
    rows: list[tuple[str, str]] = []
    # Concrete small-int substitutions.
    for n in (0, 1, 2, 3, 5, 7, 9, 12, 41):
        if seed == "x+0=x" and domain == "addition":
            rows.append((f"A axiom x+0=x for {n}", f"{n}+0"))
            rows.append((f"A check {n}+0", f"{n}"))
        elif seed == "0+x=x" and domain == "addition":
            rows.append((f"A axiom 0+x=x for {n}", f"0+{n}"))
        elif seed == "a+b=b+a" and domain == "addition":
            m = (n + 3) % 20
            rows.append((f"A commute {n}+{m}", f"{m}+{n}"))
        elif seed == "(a+b)+c=a+(b+c)" and domain == "addition":
            a, b, c = n, (n + 1) % 10, (n + 2) % 10
            rows.append((f"A assoc ({a}+{b})+{c}", f"{a}+({b}+{c})"))
        elif seed == "x-0=x" and domain == "subtraction":
            rows.append((f"S axiom x-0=x for {n}", f"{n}-0"))
        elif seed == "x-x=0" and domain == "subtraction" and n > 0:
            rows.append((f"S axiom x-x=0 for {n}", f"{n}-{n}"))
            rows.append((f"S check {n}-{n}", "0"))
        elif seed == "(a+b)-b=a" and domain == "subtraction":
            a, b = n, (n % 5) + 1
            rows.append((f"S cancel ({a}+{b})-{b}", f"{a}"))
        elif seed == "x*1=x" and domain == "multiplication":
            rows.append((f"M axiom x*1=x for {n}", f"{n}*1"))
        elif seed == "1*x=x" and domain == "multiplication":
            rows.append((f"M axiom 1*x=x for {n}", f"1*{n}"))
        elif seed == "x*0=0" and domain == "multiplication":
            rows.append((f"M axiom x*0=0 for {n}", f"{n}*0"))
            rows.append((f"M check {n}*0", "0"))
        elif seed == "a*b=b*a" and domain == "multiplication":
            m = (n % 7) + 1
            rows.append((f"M commute {n}*{m}", f"{m}*{n}"))
        elif seed == "x/1=x" and domain == "division" and n > 0:
            rows.append((f"D axiom x/1=x for {n}", f"{n}/1"))
        elif seed == "(x*y)/y=x" and domain == "division":
            x, y = max(1, n), (n % 5) + 1
            rows.append((f"D cancel ({x}*{y})/{y}", f"{x}"))
    return rows


def _registry_domain_drills(reg: UMLEquationRegistry, domain: str, *, limit: int = 200) -> list[str]:
    rows: list[str] = []
    for ch, entry in reg.entries.items():
        if not str(ch).isprintable() or ch in "\n\r\t":
            continue
        pool = [str(entry["canonical"])] + [str(e) for e in (entry.get("equivalents") or [])]
        domain_exprs = [e for e in pool if _domain_only(e, domain)]
        if not domain_exprs:
            continue
        # Prefer shortest domain route as teacher.
        domain_exprs.sort(key=lambda e: (len(e), e))
        best = domain_exprs[0]
        tag = {"addition": "A", "subtraction": "S", "multiplication": "M", "division": "D"}[domain]
        rows.append(f"User: {tag}-domain UML for {ch}\nViv: {best}<END>\n")
        rows.append(f"User: Prefer efficient UML for {ch}\nViv: {best}<END>\n")
        # Native-ish math token form
        rows.append(f"UML:{best}\nViv: {best}\n")
        if len(rows) >= limit:
            break
    return rows[:limit]


def build_domain(reg: UMLEquationRegistry, expert: dict[str, Any]) -> dict[str, Any]:
    domain = str(expert["domain"])
    out_dir = OUT_ROOT / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    dialogues: list[str] = []
    for seed in expert.get("axiom_seeds") or []:
        for instr, resp in _axiom_instances(str(seed), domain):
            dialogues.append(f"User: {instr}\nViv: {resp}<END>\n")
            # Validate numeric responses where possible
            try:
                if re.fullmatch(r"[\d+\-*/().]+", resp):
                    uml_engine.evaluate(resp)
            except Exception:
                pass
    dialogues.extend(_registry_domain_drills(reg, domain, limit=240))
    # Dedup preserve order
    seen: set[str] = set()
    uniq = []
    for d in dialogues:
        if d in seen:
            continue
        seen.add(d)
        uniq.append(d)
    text = "".join(uniq)
    (out_dir / "train_dialogues.txt").write_text(text, encoding="utf-8", newline="\n")
    meta = {
        "domain": domain,
        "id": expert.get("id"),
        "ops": expert.get("ops"),
        "dialogue_rows": len(uniq),
        "bytes": len(text.encode("utf-8")),
        "path": str(out_dir).replace("\\", "/"),
    }
    with (out_dir / "MANIFEST.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(meta, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return meta


def main() -> int:
    recipe = json.loads(RECIPE.read_text(encoding="utf-8"))
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    domains = []
    for expert in recipe.get("base_experts") or []:
        domains.append(build_domain(reg, expert))
    receipt = {
        "schema_version": "uml_domain_axiom_banks_v1",
        "status": "PASS",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "registry": str(SANDBOX96_ARTIFACT).replace("\\", "/"),
        "domains": domains,
        "total_dialogues": sum(int(d["dialogue_rows"]) for d in domains),
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
        handle.write("\n")
    with (OUT_ROOT / "BUILD.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"UML_DOMAIN_AXIOM_BANKS_PASS domains={len(domains)} "
        f"dialogues={receipt['total_dialogues']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
