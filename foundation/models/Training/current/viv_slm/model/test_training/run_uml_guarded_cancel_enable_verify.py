#!/usr/bin/env python3
"""Verify guarded U cancel is enabled before federation dispatch."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FOUNDATION = HERE.parents[5]
RUNS = HERE / "runs"
sys.path.insert(0, str(FOUNDATION))
sys.path.insert(0, str(HERE))

from lib import uml_engine  # noqa: E402
from lib.uml_equation_registry import _domains_in_expr  # noqa: E402
from lib.uml_guarded_canonicalize import (  # noqa: E402
    federation_domains_for,
    is_enabled,
    set_enabled,
    try_guarded_cancel,
)


def main() -> int:
    RUNS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    failures: list[str] = []

    if not is_enabled():
        failures.append("policy_disabled")

    cases = [
        ("(41*2)/2", frozenset()),
        ("(2*41)/2", frozenset()),
        ("(2*2)/2", frozenset()),
        ("(1*4)/2", frozenset({"M", "D"})),  # irreducible residual
        ("6/2", frozenset({"D"})),
        ("2+3", frozenset({"A"})),
    ]
    for expr, expect in cases:
        got = federation_domains_for(expr)
        if got != expect:
            failures.append(f"domains:{expr}:got={sorted(got)}:want={sorted(expect)}")
        reg = _domains_in_expr(expr)
        if reg != expect:
            failures.append(f"registry:{expr}:got={sorted(reg)}:want={sorted(expect)}")

    # Fail-closed: identity mismatch must not apply.
    value, node, _n, _t = uml_engine.evaluate("(41*2)/2")
    bad = try_guarded_cancel(
        "(41*2)/2",
        node=node,
        authoritative_value=999.0,  # wrong seal
        require_md=True,
    )
    if bad.applied:
        failures.append("fail_closed_identity_mismatch_applied")

    # Disable override works for A/B baselines.
    set_enabled(False)
    if federation_domains_for("(41*2)/2") != frozenset({"M", "D"}):
        failures.append("disable_override_failed")
    set_enabled(True)
    if federation_domains_for("(41*2)/2") != frozenset():
        failures.append("reenable_failed")

    # Live demand: shadow sandbox with cancel ON should starve U_MD to residual.
    from run_uml_am_shadow_sandbox import main as shadow_main

    t0 = time.perf_counter()
    shadow_code = int(shadow_main())
    shadow_elapsed = round(time.perf_counter() - t0, 3)
    shadow_path = RUNS / "uml_u_am_shadow_sandbox_latest.json"
    shadow = json.loads(shadow_path.read_text(encoding="utf-8")) if shadow_path.is_file() else {}
    mixed = (shadow.get("totals") or {}).get("mixed_federation_counts") or {}
    u_md = int(mixed.get("U_MD", 0))
    # Residual irreducible only expected (~9 on this workload). Hard fail if
    # cancelable drag still dominates (>100), or if residual vanished incorrectly
    # when we still expect some irreducible MD.
    if shadow_code != 0:
        failures.append(f"shadow_exit:{shadow_code}")
    if u_md > 100:
        failures.append(f"u_md_still_hot:{u_md}")
    if u_md < 1:
        failures.append(f"u_md_residual_missing:{u_md}")

    objective = (
        "PASS_GUARDED_CANCEL_ENABLED"
        if not failures
        else "FAIL_GUARDED_CANCEL_ENABLE"
    )
    receipt = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": "uml_guarded_cancel_enable_v1",
        "objective": objective,
        "enabled": is_enabled(),
        "env_override": "UML_GUARDED_CANCEL",
        "default": "on",
        "fail_closed": True,
        "shadow_exit_code": shadow_code,
        "shadow_elapsed_s": shadow_elapsed,
        "u_md_after_enable": u_md,
        "mixed_federation_counts": mixed,
        "failures": failures,
        "hooks": [
            "lib.uml_guarded_canonicalize.federation_domains_for",
            "lib.uml_equation_registry._domains_in_expr",
            "uml_u_am_shadow.UAMShadowObserver",
        ],
        "next_step": (
            "only_residual_irreducible_md_eligible_for_u_md_service_cost"
            if not failures
            else "investigate_enable_failures"
        ),
    }
    text = json.dumps(receipt, indent=2, sort_keys=True)
    (RUNS / f"uml_guarded_cancel_enable_{stamp}.json").write_text(text, encoding="utf-8")
    (RUNS / "uml_guarded_cancel_enable_latest.json").write_text(text, encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
