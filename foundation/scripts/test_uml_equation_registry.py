#!/usr/bin/env python3
"""Selftests for UML equation registry (Machine + Math dual language)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.uml_equation_registry import (  # noqa: E402
    DEFAULT_EQUIVALENTS_LIMIT,
    GENERATOR_ID,
    SANDBOX96_ARTIFACT,
    SCHEMA_VERSION,
    UMLEquationRegistry,
    build_sandbox96_registry,
    pick_canonical,
)
from lib import uml_engine  # noqa: E402

MODEL = FOUNDATION / "models" / "Training" / "current" / "viv_slm" / "model"
RECEIPT = (
    MODEL
    / "test_training"
    / "runs"
    / "uml_registry_v1_selftest_latest.json"
)
REFINE_RECEIPT = (
    MODEL
    / "test_training"
    / "runs"
    / "uml_registry_v1_1_refine_latest.json"
)
VOCAB = (
    FOUNDATION
    / "models"
    / "Training"
    / "data"
    / "identity"
    / "v61_stratified_preservation_replay"
    / "VOCAB.json"
)


def main() -> int:
    failures: list[str] = []

    # Determinism: two builds identical sha
    a = build_sandbox96_registry(VOCAB, out_path=SANDBOX96_ARTIFACT)
    sha1 = a.registry_sha256()
    b = UMLEquationRegistry.from_vocab(a.vocab, meta=dict(a.meta))
    sha2 = b.registry_sha256()
    if sha1 != sha2:
        failures.append("registry_not_deterministic")

    loaded = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    if len(loaded.vocab) != 96:
        failures.append(f"vocab_size:{len(loaded.vocab)}")
    if loaded.schema_version != SCHEMA_VERSION:
        failures.append(f"schema_version:{loaded.schema_version}")

    # Round-trip all chars
    for ch in loaded.vocab:
        eq = loaded.encode_char(ch)
        back = loaded.decode_eq(eq)
        if back != ch:
            failures.append(f"roundtrip:{ch!r}->{eq!r}->{back!r}")
            break

    # Many eqs same value decode to same char
    sample_id = 1 if len(loaded.vocab) > 1 else 0
    ch1 = loaded.vocab[sample_id]
    canon, equivalents, scored = pick_canonical(sample_id)
    if len(scored) < 8:
        failures.append(f"equiv_depth_scored:{len(scored)}")
    if len(equivalents) < 8:
        failures.append(f"equiv_depth_listed:{len(equivalents)}")
    for expr in [canon, *equivalents[:8]]:
        try:
            got = loaded.decode_eq(expr)
        except Exception as exc:
            failures.append(f"decode_equiv:{expr}:{exc!r}")
            continue
        if got != ch1:
            failures.append(f"equiv_mismatch:{expr}->{got!r} want {ch1!r}")

    # Equivalents depth across vocab (v1.1 richness)
    equiv_counts = [len(row.get("equivalents") or []) for row in loaded.entries.values()]
    avg_equiv = sum(equiv_counts) / max(len(equiv_counts), 1)
    min_equiv = min(equiv_counts) if equiv_counts else 0
    if avg_equiv < 10.0:
        failures.append(f"avg_equivalents_too_low:{avg_equiv:.2f}")
    if min_equiv < 6:
        failures.append(f"min_equivalents_too_low:{min_equiv}")

    # Canonical is most efficient among scored
    for ch, row in loaded.entries.items():
        c_cost = int(row["canonical_cost"])
        for eq in row.get("equivalents") or []:
            try:
                cost = int(uml_engine.uml_cost(eq)["symbolic_cost"])
            except Exception:
                continue
            if cost < c_cost:
                failures.append(f"canonical_not_efficient:{ch!r}:{row['canonical']}:{eq}")
                break

    # Text round-trip
    phrase = "Viv"
    phrase = "".join(ch for ch in phrase if ch in loaded.entries)
    if phrase:
        eqs = loaded.encode_text(phrase)
        decoded = loaded.decode_equations(eqs)
        if decoded != phrase:
            failures.append(f"text_roundtrip:{phrase!r}->{decoded!r}")

    # RID leaves continuous from a canonical form
    rid_ok = None
    try:
        if str(MODEL) not in sys.path:
            sys.path.insert(0, str(MODEL))
        from rid_pid import uml_nested_pemdas_leaves  # noqa: E402

        leaf = uml_nested_pemdas_leaves(loaded.encode_char(loaded.vocab[1]))
        rid_ok = 0.0 <= float(leaf["x_in"]) <= 1.0 and 0.0 <= float(leaf["x_out"]) <= 1.0
        if not rid_ok:
            failures.append(f"rid_leaves:{leaf}")
    except Exception as exc:
        failures.append(f"rid_leaves_exc:{exc!r}")

    status = "PASS" if not failures else "FAIL"
    receipt = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "failures": failures,
        "schema_version": SCHEMA_VERSION,
        "generator_id": GENERATOR_ID,
        "equivalents_limit": DEFAULT_EQUIVALENTS_LIMIT,
        "registry_sha256": sha1,
        "vocab_sha256": loaded.vocab_sha256,
        "artifact": str(SANDBOX96_ARTIFACT).replace("\\", "/"),
        "equiv_stats": {
            "avg": round(avg_equiv, 3),
            "min": min_equiv,
            "max": max(equiv_counts) if equiv_counts else 0,
        },
        "samples": {
            "char1": ch1,
            "canonical": canon,
            "equivalents": equivalents[:8],
            "scored_count": len(scored),
            "phrase": phrase if phrase else None,
            "rid_leaves_ok": rid_ok,
        },
    }
    for path in (RECEIPT, REFINE_RECEIPT):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
    print(
        f"UML_REGISTRY_SELFTEST_{status} failures={len(failures)} "
        f"sha={sha1[:16]}... avg_equiv={avg_equiv:.1f} gen={GENERATOR_ID}"
    )
    if failures:
        for item in failures[:20]:
            print("FAIL", item)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
