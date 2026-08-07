#!/usr/bin/env python3
"""Selftests for UML generation-time route governor."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402
from lib.uml_route_governor import (  # noqa: E402
    build_logit_bias,
    decide_route,
    govern_text_routes,
    next_char_pressure_scores,
    sample_route,
)

MODEL = FOUNDATION / "models" / "Training" / "current" / "viv_slm" / "model"
RECEIPT = (
    MODEL
    / "test_training"
    / "runs"
    / "uml_route_governor_v1_selftest_latest.json"
)


def main() -> int:
    failures: list[str] = []
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)

    # Fixed answer 2: invalid proposals rejected; cheapest valid wins.
    decision = decide_route(
        reg,
        target_value=2,
        proposals=["1+1", "3-1", "2*1", "9", "bogus((", "4/2", "2"],
        include_registry_pool=True,
    )
    if decision.target_value != 2:
        failures.append("target_value")
    if decision.rejected_count < 1:
        failures.append("expected_rejects")
    if decision.selected_cost > 1:
        # literal "2" should be available and cost 1
        failures.append(f"not_cheapest:{decision.selected}:{decision.selected_cost}")
    if decision.selected != "2":
        failures.append(f"expected_literal_2_got:{decision.selected!r}")

    # Without registry pool, invalid proposals → fallback literal of target value.
    ch5 = reg.vocab[5] if len(reg.vocab) > 5 else reg.vocab[0]
    bad = decide_route(
        reg,
        target_char=ch5,
        proposals=["99999", "nope"],
        include_registry_pool=False,
    )
    if bad.reason != "fallback_literal":
        failures.append(f"expected_fallback:{bad.reason}")
    if reg.decode_eq(bad.selected) != ch5:
        failures.append(f"fallback_char:{bad.selected!r}")
    if bad.rejected_count < 2:
        failures.append("fallback_rejects")

    # Governed text encode round-trip with active pressure
    phrase = "".join(ch for ch in "Hi" if ch in reg.entries)
    governed = govern_text_routes(reg, phrase)
    if not governed["roundtrip_ok"]:
        failures.append(f"text_roundtrip:{governed}")
    for row in governed["decisions"]:
        if int(row["selected_cost"]) != min(
            int(c["symbolic_cost"])
            for c in row["considered"]
            if c["valid"] and c["symbolic_cost"] is not None
        ):
            failures.append(f"not_min_cost:{row['selected']}")
            break

    # Pressure weights only on valid routes and sum ~1
    weights = decision.pressure_weights
    if weights:
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-6:
            failures.append(f"weights_sum:{total}")
        if decision.selected not in weights:
            failures.append("selected_missing_weight")

    # Pressure sampling: T→0 prefers cheapest; T>0 stays valid
    cheap = decide_route(reg, target_value=2)
    g = __import__("torch").Generator()
    g.manual_seed(0)
    near = sample_route(reg, target_value=2, temperature=1e-6, generator=g)
    if near.selected != cheap.selected:
        failures.append(f"sample_cold:{near.selected!r}!={cheap.selected!r}")
    warm = sample_route(reg, target_value=2, temperature=1.5, generator=g)
    try:
        if reg.decode_eq(warm.selected) != reg.value_to_char[2]:
            failures.append(f"sample_warm_invalid:{warm.selected!r}")
    except Exception as exc:
        failures.append(f"sample_warm_exc:{exc!r}")

    # Char logit bias prefers continuation of cheaper routes
    scores = next_char_pressure_scores(cheap.pressure_weights, "")
    if "2" not in scores:
        failures.append("prefix_bias_missing_2")
    stoi = {ch: i for i, ch in enumerate(reg.vocab)}
    bias = build_logit_bias(
        cheap.pressure_weights, "", stoi, vocab_size=len(reg.vocab), scale=4.0
    )
    if "2" in stoi and float(bias[stoi["2"]]) <= 0:
        failures.append("logit_bias_nonpositive_for_literal")
    # Literal start should outrank a non-continuation char (bias 0).
    if "2" in stoi and float(bias[stoi["2"]]) <= 0.0:
        failures.append("logit_bias_literal_not_boosted")
    status = "PASS" if not failures else "FAIL"
    receipt = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "failures": failures,
        "sample_decision": {
            "target_value": decision.target_value,
            "selected": decision.selected,
            "selected_cost": decision.selected_cost,
            "valid_count": decision.valid_count,
            "rejected_count": decision.rejected_count,
            "reason": decision.reason,
            "top_weights": dict(
                sorted(decision.pressure_weights.items(), key=lambda kv: -kv[1])[:5]
            ),
        },
        "governed_phrase": governed,
        "artifact": str(SANDBOX96_ARTIFACT).replace("\\", "/"),
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"UML_ROUTE_GOVERNOR_SELFTEST_{status} failures={len(failures)} "
        f"selected={decision.selected} rejects={decision.rejected_count}"
    )
    if failures:
        for item in failures[:20]:
            print("FAIL", item)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
