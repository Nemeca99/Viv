#!/usr/bin/env python3
"""Human-readable energy accounting action receipt."""
from __future__ import annotations

from typing import Any


def format_action_receipt(report: dict[str, Any]) -> str:
    """Format component-visible energy accounting receipt."""
    comps = report.get("component_estimates") or {}
    e_load = comps.get("E_load_j")
    e_prompt = comps.get("E_prompt_j")
    e_eval = comps.get("E_eval_j")
    e_tail = comps.get("E_tail_j")
    # Fallbacks from flat fields
    if e_load is None:
        e_load = report.get("predicted_E_load_j")
    if e_prompt is None:
        e_prompt = report.get("predicted_E_prompt_j")
    if e_eval is None:
        e_eval = report.get("predicted_E_eval_j")
    if e_tail is None:
        e_tail = report.get("predicted_E_tail_j")

    pred = report.get("predicted_E_j")
    if pred is None:
        pred = report.get("predicted_E_action_j")
    if pred is None:
        pred = report.get("predicted_E_net_j")
    measured = report.get("measured_energy")
    if measured is None:
        measured = report.get("measured_E_action_j")
    if measured is None:
        net = report.get("measured_E_net_j")
        tail = report.get("measured_E_tail_j")
        if net is not None and tail is not None:
            measured = float(net) + float(tail)
        else:
            measured = net
    resid = report.get("residual_j")
    if resid is None and pred is not None and measured is not None:
        resid = float(measured) - float(pred)

    predictor = report.get("registry_selected_predictor") or report.get("predictor") or "?"
    state = report.get("predictor_state") or report.get("confidence") or "?"

    def _fmt(x: Any) -> str:
        if isinstance(x, (int, float)):
            return f"{float(x):.0f} J"
        return "null"

    lines = [
        "Energy accounting",
        f"Model load:        {_fmt(e_load)}",
        f"Prompt evaluation: {_fmt(e_prompt)}",
        f"Token evaluation:  {_fmt(e_eval)}",
        f"Post-action tail:  {_fmt(e_tail)}",
        f"Total measured:    {_fmt(measured)}",
        f"Predicted total:   {_fmt(pred)}",
        f"Residual:          {_fmt(resid)}",
        f"Predictor: {predictor}",
        f"State: {state}",
    ]
    return "\n".join(lines)
