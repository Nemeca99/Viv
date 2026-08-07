#!/usr/bin/env python3
"""Build thickened native UML math-token dialogues (P2 native snap-free).

v2 densifies costly→canonical repairs, multi-alt ranking, and multi-char
cheap streams. Still math-token only (no English Prefer-efficient prose).
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

from lib.uml_equation_registry import (  # noqa: E402
    SANDBOX96_ARTIFACT,
    UMLEquationRegistry,
    _symbolic_cost,
)
from lib.uml_route_governor import decide_route  # noqa: E402
from uml_codec_io import build_native_uml_prompt, is_math_token_surface  # noqa: E402

OUT = SANDBOX / "data" / "uml_native_math_tokens_v1"
RECEIPT = SANDBOX / "runs" / "uml_native_math_tokens_build_latest.json"


def _ops_mixed(expr: str) -> bool:
    return any(op in expr for op in "+-*/")


def _sorted_alts(entry: dict) -> list[str]:
    alts = [str(a) for a in (entry.get("equivalents") or [])]
    scored: list[tuple[int, str]] = []
    for a in alts:
        try:
            scored.append((_symbolic_cost(a), a))
        except Exception:
            continue
    scored.sort(key=lambda t: (t[0], len(t[1]), t[1]))
    # unique preserve cost order
    seen: set[str] = set()
    out: list[str] = []
    for _, a in scored:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def main() -> int:
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    surfaces: list[str] = []
    for ch in reg.vocab:
        if ch.isprintable() and ch not in "\n\r\t":
            surfaces.append(ch)
    for word in ("Hi", "Viv", "OK", "A", "Go", "HAVE", "iv", "123", "HA", "AV", "Vi"):
        if all(c in reg.entries for c in word):
            surfaces.append(word)
    seen: set[str] = set()
    surfaces = [s for s in surfaces if not (s in seen or seen.add(s))]

    rows: list[str] = []
    n_identity = 0
    n_repair = 0
    n_rank = 0
    n_multi = 0

    for s in surfaces:
        native = build_native_uml_prompt(s, registry=reg, prefer_efficient=True)
        uml = native["encode"]["uml_stream"]
        if not is_math_token_surface(uml):
            raise RuntimeError(f"non_math_surface:{s!r}:{uml!r}")
        # Identity: sealed cheap stream → same stream (×2 for weight).
        rows.append(f"{native['model_prompt']}{uml}\n")
        rows.append(f"{native['model_prompt']}{uml}\n")
        n_identity += 2

        # Multi-char: also emit per-slot cheapest via decide_route
        if len(s) > 1:
            cheap_parts = [decide_route(reg, target_char=c).selected for c in s]
            cheap_stream = ",".join(cheap_parts)
            # Start from a deliberately costly first-slot if available
            first_alts = _sorted_alts(reg.entries[s[0]])
            costly_first = next((a for a in reversed(first_alts) if _ops_mixed(a)), None)
            if costly_first:
                costly_parts = [costly_first] + cheap_parts[1:]
                rows.append(f"UML:{','.join(costly_parts)}\nViv: {cheap_stream}\n")
                n_multi += 1
            rows.append(f"UML:{cheap_stream}\nViv: {cheap_stream}\n")
            n_multi += 1

    # Per-character repair + ranking drills (dense).
    for ch, entry in reg.entries.items():
        if not str(ch).isprintable() or ch in "\n\r\t":
            continue
        canon = str(entry["canonical"])
        cheap = decide_route(reg, target_char=ch).selected
        alts = _sorted_alts(entry)
        mixed = [a for a in alts if _ops_mixed(a)]
        # Always reinforce cheapest alone
        rows.append(f"UML:{cheap}\nViv: {cheap}\n")
        rows.append(f"UML:{canon}\nViv: {cheap}\n")
        n_identity += 2

        # Up to 6 costly→cheap repairs (was 1)
        for costly in reversed(mixed[-6:] if mixed else []):
            if costly == cheap:
                continue
            rows.append(f"UML:{costly}\nViv: {cheap}\n")
            n_repair += 1

        # Rank drill: mid-cost and high-cost both map to cheap
        if len(mixed) >= 2:
            mid = mixed[len(mixed) // 2]
            hi = mixed[-1]
            rows.append(f"UML:{hi}\nViv: {cheap}\n")
            rows.append(f"UML:{mid}\nViv: {cheap}\n")
            n_rank += 2

    # Dedup preserve order (identity doubles intentionally kept via unique keys? —
    # use exact-line dedup but keep first two identity copies by tagging... simpler:
    # allow duplicates for weight; cap total size by not exploding further.)
    # Soft dedup: collapse exact duplicates beyond 3 copies.
    counts: dict[str, int] = {}
    uniq: list[str] = []
    for r in rows:
        c = counts.get(r, 0)
        if c >= 3:
            continue
        counts[r] = c + 1
        uniq.append(r)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "train_dialogues.txt").write_text("".join(uniq), encoding="utf-8", newline="\n")
    meta = {
        "schema_version": "uml_native_math_tokens_v2",
        "status": "PASS",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "registry_schema": reg.schema_version,
        "n_surfaces": len(surfaces),
        "n_dialogues": len(uniq),
        "n_identity": n_identity,
        "n_repair": n_repair,
        "n_rank": n_rank,
        "n_multi": n_multi,
        "english_instruction_lines": 0,
        "math_token_only": True,
        "emergence_need": "P2_snap_free_cheap",
        "thicken": True,
        "path": str(OUT).replace("\\", "/"),
    }
    with (OUT / "MANIFEST.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(meta, handle, indent=2, sort_keys=True)
        handle.write("\n")
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(meta, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"UML_NATIVE_MATH_TOKENS_V2_PASS dialogues={len(uniq)} "
        f"surfaces={len(surfaces)} repair={n_repair} multi={n_multi}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
