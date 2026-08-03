#!/usr/bin/env python3
"""Revalidation registry for eval_duration_v1 accounting predictor."""
from __future__ import annotations

from typing import Any

from lib.rid_electrical_predictor import PLANT_CONFIG_ID


REVALIDATION_TRIGGERS: tuple[dict[str, str], ...] = (
    {
        "trigger_id": "model_or_quantization_change",
        "description": "Model name, weights, or quantization changed.",
        "action": "revalidate_before_use",
    },
    {
        "trigger_id": "hardware_change_cpu_gpu",
        "description": "CPU/GPU hardware changed.",
        "action": "revalidate_before_use",
    },
    {
        "trigger_id": "driver_or_firmware_change",
        "description": "Driver/firmware update may alter power behavior.",
        "action": "revalidate_before_use",
    },
    {
        "trigger_id": "telemetry_cadence_change",
        "description": "Generate telemetry cadence changed from calibrated setting.",
        "action": "revalidate_before_use",
    },
    {
        "trigger_id": "baseline_recipe_change",
        "description": "Settle/baseline window or idle gates changed.",
        "action": "revalidate_before_use",
    },
    {
        "trigger_id": "thermal_protocol_change",
        "description": "GPU thermal starting band or control protocol changed.",
        "action": "revalidate_before_use",
    },
    {
        "trigger_id": "executor_change",
        "description": "Inference executor/runtime path changed.",
        "action": "revalidate_before_use",
    },
    {
        "trigger_id": "residency_mode_change",
        "description": "Warm residency protocol changed (cold/warm behavior).",
        "action": "revalidate_before_use",
    },
)


def check_config_drift(current_config_id: str | None) -> dict[str, Any]:
    """Compare runtime config against locked predictor config."""
    supplied = "" if current_config_id is None else str(current_config_id)
    match = supplied == PLANT_CONFIG_ID
    return {
        "match": match,
        "current_config_id": supplied,
        "locked_config_id": PLANT_CONFIG_ID,
        "action": "ok" if match else "revalidate_before_use",
    }

