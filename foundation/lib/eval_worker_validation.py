"""Foreman-side validation for local coder evaluation drafts."""
from __future__ import annotations

from typing import Any, Callable


def validate_eval_row(row: dict[str, Any], judge: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    pair_id = row.get("pair_id", "<missing>")
    required = {
        "ask", "chosen", "target", "axis", "pair_id", "expected",
        "hold_only", "optimizer_eligible", "training_authorized", "run_authorized",
    }
    missing = sorted(required - row.keys())
    if missing:
        raise ValueError(f"{pair_id}:missing_fields:{','.join(missing)}")
    if row["chosen"] != row["target"]:
        raise ValueError(f"{pair_id}:chosen_target_mismatch")
    if row["hold_only"] is not True:
        raise ValueError(f"{pair_id}:hold_only_not_true")
    if row["optimizer_eligible"] is not False:
        raise ValueError(f"{pair_id}:optimizer_eligible_not_false")
    if row["training_authorized"] is not False:
        raise ValueError(f"{pair_id}:training_authorized_not_false")
    if row["run_authorized"] is not False:
        raise ValueError(f"{pair_id}:run_authorized_not_false")
    result = judge(row["target"], axis=row["axis"], ask=row["ask"], use_cpu_sensor=False)
    if result.get("status") != row["expected"]:
        raise ValueError(f"{pair_id}:expected={row['expected']}:observed={result.get('status')}")
    return result
