"""Pure governance primitives for bounded Viv-SLM layer experiments.

This module deliberately does not load models, write files, acquire leases, or
change authority records.  It centralizes the deterministic decisions that
future layer trainers must share: one bounded increment, explicit closed
side-effect gates, parent binding, largest guard-safe composition selection,
and rollback/halt accounting.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import math
import re
from typing import Any, Callable, Iterable, Mapping


ONE_INCREMENT_STEPS = 250
MAX_CONSECUTIVE_GUARD_FAILURES = 2
_REQUIRED_CLOSED_FIELDS = (
    "promotion_authorized",
    "deployment_changed",
    "live_model_changed",
    "global_aifl_writes",
    "master_s_n_mutation",
    "knowledge_admission",
)
_SHA256_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
_CONTROLLER_SCHEMA_VERSION = "viv_slm_multi_metric_controller_v1"
_CONTROLLER_SCHEMA_V2 = "viv_slm_multi_metric_controller_v2"
_CONTROLLER_SCHEMA_V3 = "viv_slm_multi_metric_controller_v3"
_CONTROLLER_SCHEMA_VERSIONS = frozenset({_CONTROLLER_SCHEMA_VERSION, _CONTROLLER_SCHEMA_V2, _CONTROLLER_SCHEMA_V3})


def _is_exact_int(value: Any, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"viv_slm_governor_campaign_{field}_missing")
    return text


def _required_hash(value: Any, field: str) -> str:
    text = _required_text(value, field).upper()
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"viv_slm_governor_campaign_{field}_sha256_invalid")
    return text


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _finite_controller_float(value: Any, field: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"viv_slm_governor_controller_{field}_invalid") from error
    if not math.isfinite(normalized):
        raise ValueError(f"viv_slm_governor_controller_{field}_nonfinite")
    return normalized


def _controller_config_float(
    config: Mapping[str, Any],
    key: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = _finite_controller_float(config.get(key, default), key)
    if minimum is not None and value < minimum:
        raise ValueError(f"viv_slm_governor_controller_{key}_below_minimum")
    if maximum is not None and value > maximum:
        raise ValueError(f"viv_slm_governor_controller_{key}_above_maximum")
    return value


def adaptive_controller_update(
    state: Mapping[str, Any],
    *,
    observations: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
    max_grad_norm: float = 1.0,
    base_anchor_weight: float = 0.20,
    anchor_weight_min: float = 0.05,
    anchor_weight_max: float = 0.50,
    learning_rate_scale_min: float = 0.20,
    learning_rate_scale_max: float = 1.05,
    gradient_clip_scale_min: float = 0.75,
    gradient_clip_scale_max: float = 1.00,
    base_weight_decay: float = 0.0,
    weight_decay_scale_min: float = 0.25,
    weight_decay_scale_max: float = 1.00,
) -> dict[str, Any]:
    """Update bounded controller variables from declarative multi-metric feedback.

    The controller is deliberately conservative: loss and gradient observations
    can only add pressure that lowers the next learning-rate scale, while the
    existing teacher/validation signals continue to govern the anchor weight.
    Controller V1 observes the gradient ceiling as a fixed hard limit. Controller
    V2 additionally permits a declared, downward-only gradient-clip scale inside
    explicit bounds; it can never raise the caller's base ceiling.
    Controller V3 preserves V2 and additionally permits a declared, downward-only
    AdamW weight-decay scale driven by the combined stability pressure; it can
    never increase the caller's base weight decay.
    """

    if not isinstance(state, Mapping) or not isinstance(observations, Mapping):
        raise TypeError("viv_slm_governor_controller_state_and_observations_must_be_mappings")
    controller_config = dict(config or {})
    schema_version = str(controller_config.get("schema_version") or _CONTROLLER_SCHEMA_VERSION)
    if schema_version not in _CONTROLLER_SCHEMA_VERSIONS:
        raise ValueError("viv_slm_governor_controller_schema_version_invalid")
    alpha = _controller_config_float(controller_config, "ema_alpha", 0.10, minimum=1e-9, maximum=1.0)
    teacher_target = _controller_config_float(controller_config, "teacher_kl_delta_target", 0.002, minimum=1e-12)
    validation_target = _controller_config_float(controller_config, "validation_nll_delta_target", 0.001, minimum=1e-12)
    loss_tolerance = _controller_config_float(controller_config, "loss_relative_tolerance", 0.05, minimum=1e-9)
    grad_target_ratio = _controller_config_float(
        controller_config,
        "grad_norm_target_ratio",
        0.80,
        minimum=1e-9,
        maximum=1.0 - 1e-9,
    )
    max_grad_norm_value = _finite_controller_float(max_grad_norm, "max_grad_norm")
    if max_grad_norm_value <= 0.0:
        raise ValueError("viv_slm_governor_controller_max_grad_norm_invalid")
    base_anchor = _finite_controller_float(base_anchor_weight, "base_anchor_weight")
    anchor_min = _finite_controller_float(anchor_weight_min, "anchor_weight_min")
    anchor_max = _finite_controller_float(anchor_weight_max, "anchor_weight_max")
    lr_min = _finite_controller_float(learning_rate_scale_min, "learning_rate_scale_min")
    lr_max = _finite_controller_float(learning_rate_scale_max, "learning_rate_scale_max")
    clip_min = _finite_controller_float(gradient_clip_scale_min, "gradient_clip_scale_min")
    clip_max = _finite_controller_float(gradient_clip_scale_max, "gradient_clip_scale_max")
    base_weight_decay_value = _finite_controller_float(base_weight_decay, "base_weight_decay")
    weight_decay_min = _finite_controller_float(weight_decay_scale_min, "weight_decay_scale_min")
    weight_decay_max = _finite_controller_float(weight_decay_scale_max, "weight_decay_scale_max")
    if (
        not 0.0 <= anchor_min <= anchor_max
        or not 0.0 <= lr_min <= lr_max
        or not 0.0 < clip_min <= clip_max
        or base_weight_decay_value < 0.0
        or not 0.0 <= weight_decay_min <= weight_decay_max
    ):
        raise ValueError("viv_slm_governor_controller_bounds_invalid")

    observations_float: dict[str, float] = {}
    for raw_name, raw_value in observations.items():
        name = str(raw_name).strip()
        if not name:
            raise ValueError("viv_slm_governor_controller_observation_name_missing")
        observations_float[name] = _finite_controller_float(raw_value, f"observation_{name}")

    metric_ema = dict(state.get("metric_ema") or {})
    metric_baselines = dict(state.get("metric_baselines") or {})
    baseline_metrics = {"training_nll", "sft_loss", "total_loss"}
    for name, value in observations_float.items():
        previous = metric_ema.get(name)
        metric_ema[name] = value if previous is None else (alpha * value) + ((1.0 - alpha) * _finite_controller_float(previous, f"ema_{name}"))
        if name in baseline_metrics and name not in metric_baselines:
            metric_baselines[name] = value

    teacher_ema = _finite_controller_float(
        metric_ema.get("teacher_kl_delta", state.get("teacher_kl_delta_ema", 0.0)),
        "teacher_kl_delta_ema",
    )
    validation_ema = _finite_controller_float(
        metric_ema.get("validation_nll_delta", state.get("validation_nll_delta_ema", 0.0)),
        "validation_nll_delta_ema",
    )
    teacher_pressure = _clip(max(0.0, teacher_ema) / teacher_target, 0.0, 1.0)
    validation_pressure = _clip(max(0.0, validation_ema) / validation_target, 0.0, 1.0)
    metric_pressures: dict[str, float] = {
        "teacher_kl_delta": teacher_pressure,
        "validation_nll_delta": validation_pressure,
    }
    loss_pressures: list[float] = []
    for name in sorted(baseline_metrics):
        if name not in metric_ema or name not in metric_baselines:
            continue
        baseline = _finite_controller_float(metric_baselines[name], f"baseline_{name}")
        denominator = max(abs(baseline), 1e-9)
        pressure = _clip(max(0.0, (float(metric_ema[name]) - baseline) / denominator) / loss_tolerance, 0.0, 1.0)
        metric_pressures[name] = pressure
        loss_pressures.append(pressure)
    loss_pressure = max(loss_pressures, default=0.0)

    gradient_pressure = 0.0
    if "grad_norm_before_clip" in metric_ema:
        target_grad_norm = max_grad_norm_value * grad_target_ratio
        gradient_pressure = _clip(
            (float(metric_ema["grad_norm_before_clip"]) / target_grad_norm - 1.0) / (1.0 / grad_target_ratio - 1.0),
            0.0,
            1.0,
        )
        metric_pressures["grad_norm_before_clip"] = gradient_pressure
    stability_pressure = max(teacher_pressure, validation_pressure, loss_pressure, gradient_pressure)
    anchor_weight = _clip(
        base_anchor * (1.0 + (0.80 * teacher_pressure) + (0.50 * validation_pressure) + (0.40 * loss_pressure)),
        anchor_min,
        anchor_max,
    )
    lr_scale = _clip(
        1.0
        - (0.35 * teacher_pressure)
        - (0.50 * validation_pressure)
        - (0.35 * loss_pressure)
        - (0.45 * gradient_pressure),
        lr_min,
        lr_max,
    )
    gradient_clip_scale = None
    if schema_version in (_CONTROLLER_SCHEMA_V2, _CONTROLLER_SCHEMA_V3):
        gradient_clip_scale = _clip(
            clip_max - ((clip_max - clip_min) * gradient_pressure),
            clip_min,
            clip_max,
        )
    weight_decay_scale = None
    if schema_version == _CONTROLLER_SCHEMA_V3:
        weight_decay_scale = _clip(
            weight_decay_max - ((weight_decay_max - weight_decay_min) * stability_pressure),
            weight_decay_min,
            weight_decay_max,
        )
    updated = deepcopy(dict(state))
    updated.update(
        {
            "schema_version": schema_version,
            "alpha": alpha,
            "controller_config": deepcopy(controller_config),
            "metric_ema": metric_ema,
            "metric_baselines": metric_baselines,
            "metric_pressures": metric_pressures,
            "teacher_kl_delta_ema": teacher_ema,
            "validation_nll_delta_ema": validation_ema,
            "teacher_pressure": teacher_pressure,
            "validation_pressure": validation_pressure,
            "loss_pressure": loss_pressure,
            "gradient_pressure": gradient_pressure,
            "stability_pressure": stability_pressure,
            "anchor_weight": anchor_weight,
            "lr_scale": lr_scale,
            "tuned_variables": {
                "learning_rate_scale": lr_scale,
                "anchor_weight": anchor_weight,
            },
        }
    )
    if gradient_clip_scale is not None:
        updated["gradient_clip_scale"] = gradient_clip_scale
        updated["gradient_clip_ceiling"] = max_grad_norm_value * gradient_clip_scale
        updated["gradient_clip_scale_min"] = clip_min
        updated["gradient_clip_scale_max"] = clip_max
        updated["tuned_variables"]["gradient_clip_scale"] = gradient_clip_scale
    else:
        for key in ("gradient_clip_scale", "gradient_clip_ceiling", "gradient_clip_scale_min", "gradient_clip_scale_max"):
            updated.pop(key, None)
    if weight_decay_scale is not None:
        updated["weight_decay_scale"] = weight_decay_scale
        updated["effective_weight_decay"] = base_weight_decay_value * weight_decay_scale
        updated["weight_decay_scale_min"] = weight_decay_min
        updated["weight_decay_scale_max"] = weight_decay_max
        updated["tuned_variables"]["weight_decay_scale"] = weight_decay_scale
    else:
        for key in ("weight_decay_scale", "effective_weight_decay", "weight_decay_scale_min", "weight_decay_scale_max"):
            updated.pop(key, None)
    return updated


def seed_controller_actuation_state(
    initial_state: Mapping[str, Any],
    source_state: Mapping[str, Any],
    *,
    expected_schema_version: str,
    anchor_weight_min: float,
    anchor_weight_max: float,
    learning_rate_scale_min: float,
    learning_rate_scale_max: float,
    gradient_clip_scale_min: float,
    gradient_clip_scale_max: float,
    weight_decay_scale_min: float,
    weight_decay_scale_max: float,
) -> dict[str, Any]:
    """Carry forward bounded actuator state without carrying stale metric history.

    A later campaign may inherit the controller's last safe actuator settings,
    but metric EMAs, baselines, and pressures are specific to the prior run and
    must be re-established from the new run's observations.  Bounds are hard
    validation gates: the seed is rejected rather than silently repaired.
    """

    if not isinstance(initial_state, Mapping) or not isinstance(source_state, Mapping):
        raise TypeError("viv_slm_governor_controller_seed_states_must_be_mappings")
    expected_schema = str(expected_schema_version).strip()
    source_config = source_state.get("controller_config")
    source_schema = source_state.get("schema_version")
    if source_schema is None and isinstance(source_config, Mapping):
        source_schema = source_config.get("schema_version")
    if str(source_schema or "").strip() != expected_schema:
        raise ValueError("viv_slm_governor_controller_seed_schema_mismatch")
    bounds = {
        "anchor_weight": (anchor_weight_min, anchor_weight_max),
        "lr_scale": (learning_rate_scale_min, learning_rate_scale_max),
        "gradient_clip_scale": (gradient_clip_scale_min, gradient_clip_scale_max),
        "weight_decay_scale": (weight_decay_scale_min, weight_decay_scale_max),
    }
    seeded: dict[str, float] = {}
    for field, (lower_raw, upper_raw) in bounds.items():
        lower = _finite_controller_float(lower_raw, f"seed_{field}_min")
        upper = _finite_controller_float(upper_raw, f"seed_{field}_max")
        value = _finite_controller_float(source_state.get(field), f"seed_{field}")
        if lower > upper or not lower <= value <= upper:
            raise ValueError(f"viv_slm_governor_controller_seed_{field}_out_of_bounds")
        seeded[field] = value
    updated = deepcopy(dict(initial_state))
    updated.update(seeded)
    for field in (
        "metric_ema",
        "metric_baselines",
        "metric_pressures",
        "teacher_kl_delta_ema",
        "validation_nll_delta_ema",
        "teacher_pressure",
        "validation_pressure",
        "loss_pressure",
        "gradient_pressure",
        "stability_pressure",
    ):
        updated.pop(field, None)
    updated["controller_seed"] = {
        "mode": "carry_forward_actuation_only",
        "source_schema_version": expected_schema,
        "fields": sorted(seeded),
        "metric_history_carried": False,
    }
    return updated


def _validate_scale_ladder(scales: Iterable[Any]) -> tuple[float, ...]:
    values = tuple(float(value) for value in scales)
    if not values:
        raise ValueError("viv_slm_governor_scale_ladder_empty")
    if any(not math.isfinite(value) or not 0.0 < value <= 1.0 for value in values):
        raise ValueError("viv_slm_governor_scale_ladder_value_out_of_bounds")
    if len(set(values)) != len(values):
        raise ValueError("viv_slm_governor_scale_ladder_duplicate")
    if any(left <= right for left, right in zip(values, values[1:])):
        raise ValueError("viv_slm_governor_scale_ladder_must_descend")
    return values


def _validate_campaign_authority_scope(scope: Mapping[str, Any], *, step_budget: int) -> dict[str, Any]:
    if not _is_exact_int(scope.get("steps"), step_budget):
        raise ValueError("viv_slm_governor_campaign_authority_scope_steps_mismatch")
    if "step_increment" in scope and not _is_exact_int(scope.get("step_increment"), ONE_INCREMENT_STEPS):
        raise ValueError("viv_slm_governor_campaign_authority_scope_increment_invalid")
    for field in ("training_authorized", "run_authorized"):
        if not isinstance(scope.get(field), bool):
            raise ValueError(f"viv_slm_governor_campaign_authority_scope_{field}_invalid")
    for field in _REQUIRED_CLOSED_FIELDS:
        if scope.get(field) is not False:
            raise ValueError(f"viv_slm_governor_campaign_authority_scope_gate_open:{field}")
    return dict(scope)


@dataclass(frozen=True)
class LayerCampaignSpec:
    """Validated declarative input for one future layer experiment."""

    campaign_id: str
    parent_checkpoint: str
    parent_checkpoint_sha256: str
    delta_source_parent: str
    delta_source_parent_sha256: str
    delta_source_child: str
    delta_source_child_sha256: str
    allowed_scale_ladder: tuple[float, ...]
    metric_guards: Mapping[str, Any]
    teacher_reference_checkpoint: str
    teacher_reference_checkpoint_sha256: str
    step_budget: int
    rollback_budget: int
    probe_suite: tuple[str, ...]
    authority_scope: Mapping[str, Any]
    schema_version: str = "viv_slm_layer_campaign_v1"
    input_root: str = "models/viv_slm_identity_personality_v31_balanced_base/inputs"
    output_dir: str | None = None
    training_config: Mapping[str, Any] = field(default_factory=dict)
    knob_registry: Mapping[str, Any] | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "LayerCampaignSpec":
        if str(raw.get("schema_version") or "viv_slm_layer_campaign_v1") != "viv_slm_layer_campaign_v1":
            raise ValueError("viv_slm_governor_campaign_schema_version_invalid")
        step_budget = raw.get("step_budget")
        if not _is_exact_int(step_budget, ONE_INCREMENT_STEPS):
            raise ValueError("viv_slm_governor_campaign_step_budget_must_be_250")
        rollback_budget = raw.get("rollback_budget")
        if not isinstance(rollback_budget, int) or isinstance(rollback_budget, bool) or not 1 <= rollback_budget <= MAX_CONSECUTIVE_GUARD_FAILURES:
            raise ValueError("viv_slm_governor_campaign_rollback_budget_invalid")
        metric_guards = raw.get("metric_guards")
        if not isinstance(metric_guards, Mapping) or not metric_guards:
            raise ValueError("viv_slm_governor_campaign_metric_guards_missing")
        probe_suite_raw = raw.get("probe_suite")
        if not isinstance(probe_suite_raw, (list, tuple)) or not probe_suite_raw:
            raise ValueError("viv_slm_governor_campaign_probe_suite_missing")
        probe_suite = tuple(_required_text(value, "probe_suite_entry") for value in probe_suite_raw)
        if len(set(probe_suite)) != len(probe_suite):
            raise ValueError("viv_slm_governor_campaign_probe_suite_duplicate")
        authority_scope = raw.get("authority_scope")
        if not isinstance(authority_scope, Mapping):
            raise ValueError("viv_slm_governor_campaign_authority_scope_missing")
        knob_registry_raw = raw.get("knob_registry")
        if knob_registry_raw is not None and not isinstance(knob_registry_raw, Mapping):
            raise ValueError("viv_slm_governor_campaign_knob_registry_invalid")
        return cls(
            campaign_id=_required_text(raw.get("campaign_id"), "id"),
            parent_checkpoint=_required_text(raw.get("parent_checkpoint"), "parent_checkpoint"),
            parent_checkpoint_sha256=_required_hash(raw.get("parent_checkpoint_sha256"), "parent_checkpoint"),
            delta_source_parent=_required_text(raw.get("delta_source_parent"), "delta_source_parent"),
            delta_source_parent_sha256=_required_hash(raw.get("delta_source_parent_sha256"), "delta_source_parent"),
            delta_source_child=_required_text(raw.get("delta_source_child"), "delta_source_child"),
            delta_source_child_sha256=_required_hash(raw.get("delta_source_child_sha256"), "delta_source_child"),
            allowed_scale_ladder=_validate_scale_ladder(raw.get("allowed_scale_ladder") or ()),
            metric_guards=dict(metric_guards),
            teacher_reference_checkpoint=_required_text(raw.get("teacher_reference_checkpoint"), "teacher_reference_checkpoint"),
            teacher_reference_checkpoint_sha256=_required_hash(raw.get("teacher_reference_checkpoint_sha256"), "teacher_reference_checkpoint"),
            step_budget=step_budget,
            rollback_budget=rollback_budget,
            probe_suite=probe_suite,
            authority_scope=_validate_campaign_authority_scope(authority_scope, step_budget=step_budget),
            input_root=_required_text(
                raw.get("input_root") or "models/viv_slm_identity_personality_v31_balanced_base/inputs",
                "input_root",
            ),
            output_dir=(str(raw["output_dir"]).strip() if raw.get("output_dir") is not None else None),
            training_config=dict(raw.get("training_config") or {}),
            knob_registry=(dict(knob_registry_raw) if isinstance(knob_registry_raw, Mapping) else None),
        )

    def to_mapping(self) -> dict[str, Any]:
        mapping = {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "parent_checkpoint": self.parent_checkpoint,
            "parent_checkpoint_sha256": self.parent_checkpoint_sha256,
            "delta_source_parent": self.delta_source_parent,
            "delta_source_parent_sha256": self.delta_source_parent_sha256,
            "delta_source_child": self.delta_source_child,
            "delta_source_child_sha256": self.delta_source_child_sha256,
            "allowed_scale_ladder": list(self.allowed_scale_ladder),
            "metric_guards": deepcopy(dict(self.metric_guards)),
            "teacher_reference_checkpoint": self.teacher_reference_checkpoint,
            "teacher_reference_checkpoint_sha256": self.teacher_reference_checkpoint_sha256,
            "step_budget": self.step_budget,
            "rollback_budget": self.rollback_budget,
            "probe_suite": list(self.probe_suite),
            "authority_scope": deepcopy(dict(self.authority_scope)),
            "input_root": self.input_root,
            "output_dir": self.output_dir,
            "training_config": deepcopy(dict(self.training_config)),
        }
        if self.knob_registry is not None:
            mapping["knob_registry"] = deepcopy(dict(self.knob_registry))
        return mapping


def validate_layer_campaign_spec(raw: Mapping[str, Any]) -> LayerCampaignSpec:
    """Validate and normalize a declarative layer campaign contract."""

    if not isinstance(raw, Mapping):
        raise TypeError("viv_slm_governor_campaign_spec_must_be_mapping")
    return LayerCampaignSpec.from_mapping(raw)


def require_one_increment(steps: int, *, increment: int = ONE_INCREMENT_STEPS) -> int:
    """Require exactly one bounded increment and return its normalized value."""

    if not _is_exact_int(increment, ONE_INCREMENT_STEPS):
        raise ValueError("viv_slm_governor_increment_policy_must_be_250")
    if not _is_exact_int(steps, ONE_INCREMENT_STEPS):
        raise ValueError("viv_slm_governor_only_one_250_step_increment_allowed")
    return ONE_INCREMENT_STEPS


def validate_authority_record(
    record: Mapping[str, Any],
    *,
    campaign_id: str,
    steps: int,
) -> dict[str, Any]:
    """Validate training authority while requiring every consequential gate closed."""

    require_one_increment(steps)
    if str(record.get("campaign_id") or "") != str(campaign_id):
        raise PermissionError("viv_slm_governor_campaign_id_mismatch")
    if record.get("training_authorized") is not True or record.get("run_authorized") is not True:
        raise PermissionError("viv_slm_governor_training_or_run_authority_closed")
    scope = record.get("scope")
    if not isinstance(scope, Mapping) or not _is_exact_int(scope.get("steps"), ONE_INCREMENT_STEPS):
        raise PermissionError("viv_slm_governor_task_scope_steps_mismatch")
    for field in _REQUIRED_CLOSED_FIELDS:
        if record.get(field) is not False:
            raise PermissionError(f"viv_slm_governor_side_effect_gate_open:{field}")
    return {
        "campaign_id": str(campaign_id),
        "steps": ONE_INCREMENT_STEPS,
        "training_authorized": True,
        "run_authorized": True,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "global_aifl_writes": False,
        "master_s_n_mutation": False,
        "knowledge_admission": False,
    }


def parent_binding_matches(manifest: Mapping[str, Any], parent: Mapping[str, Any]) -> bool:
    """Return whether a run manifest is bound to the selected parent hash/path."""

    expected_hash = str(parent.get("checkpoint_sha256") or "").upper()
    declared_hash = str(manifest.get("warm_start_checkpoint_sha256") or "").upper()
    if expected_hash and declared_hash:
        return expected_hash == declared_hash
    declared_path = str(manifest.get("warm_start_checkpoint") or "").replace("\\", "/").casefold()
    expected_path = str(parent.get("checkpoint") or "").replace("\\", "/").casefold()
    return bool(declared_path and expected_path and declared_path == expected_path)


def _clone_state_value(value: Any) -> Any:
    clone = getattr(value, "clone", None)
    return clone() if callable(clone) else deepcopy(value)


def _is_floating_state_value(value: Any) -> bool:
    is_floating = getattr(value, "is_floating_point", None)
    if callable(is_floating):
        return bool(is_floating())
    return isinstance(value, float)


def _float_state_value(value: Any) -> Any:
    as_float = getattr(value, "float", None)
    return as_float() if callable(as_float) else float(value)


def compose_parameter_state(
    parent_state: Mapping[str, Any],
    delta_source_child_state: Mapping[str, Any],
    delta_source_parent_state: Mapping[str, Any],
    scale: float,
) -> dict[str, Any]:
    """Construct ``parent + scale * (child - source_parent)`` without mutation."""

    if not math.isfinite(float(scale)) or not 0.0 <= float(scale) <= 1.0:
        raise ValueError("viv_slm_governor_composition_scale_out_of_bounds")
    if set(parent_state) != set(delta_source_child_state) or set(parent_state) != set(delta_source_parent_state):
        raise ValueError("viv_slm_governor_composition_state_keys_mismatch")
    composed: dict[str, Any] = {}
    for key, parent_value in parent_state.items():
        child_value = delta_source_child_state[key]
        source_parent_value = delta_source_parent_state[key]
        if _is_floating_state_value(parent_value):
            composed[key] = _float_state_value(parent_value) + (
                float(scale) * (_float_state_value(child_value) - _float_state_value(source_parent_value))
            )
        else:
            composed[key] = _clone_state_value(parent_value)
    return composed


def evaluate_scale_ladder(
    *,
    parent_state: Mapping[str, Any],
    delta_source_child_state: Mapping[str, Any],
    delta_source_parent_state: Mapping[str, Any],
    allowed_scale_ladder: Iterable[Any],
    evaluate_candidate: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    guard_candidate: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, bool]],
    improvement_candidate: Callable[[Mapping[str, Any], Mapping[str, Any]], bool],
) -> dict[str, Any]:
    """Evaluate a scale ladder read-only and return the largest safe candidate."""

    scales = _validate_scale_ladder(allowed_scale_ladder)
    baseline_metrics = dict(evaluate_candidate(parent_state))
    candidate_states: dict[float, dict[str, Any]] = {}
    trials: list[dict[str, Any]] = []
    guard_keys: tuple[str, ...] | None = None
    for scale in scales:
        state = compose_parameter_state(
            parent_state,
            delta_source_child_state,
            delta_source_parent_state,
            scale,
        )
        metrics = dict(evaluate_candidate(state))
        guards = dict(guard_candidate(baseline_metrics, metrics))
        if not guards or any(not isinstance(value, bool) for value in guards.values()):
            raise ValueError("viv_slm_governor_candidate_guards_must_be_named_booleans")
        if guard_keys is None:
            guard_keys = tuple(str(key) for key in guards)
        elif tuple(str(key) for key in guards) != guard_keys:
            raise ValueError("viv_slm_governor_candidate_guard_schema_changed")
        improved = bool(improvement_candidate(baseline_metrics, metrics))
        trial = {
            "scale": scale,
            "metrics": metrics,
            "guard_results": guards,
            "improved": improved,
            "selected": False,
        }
        trial.update(guards)
        trials.append(trial)
        candidate_states[scale] = state
    selected_trial = select_largest_guard_safe_trial(
        trials,
        guard_keys=guard_keys or (),
        improvement_key="improved",
    )
    if selected_trial is None:
        return {
            "baseline_metrics": baseline_metrics,
            "selected_scale": 0.0,
            "selected_state": compose_parameter_state(
                parent_state,
                delta_source_child_state,
                delta_source_parent_state,
                0.0,
            ),
            "selected_trial": None,
            "trials": trials,
        }
    selected_scale = float(selected_trial["scale"])
    for trial in trials:
        trial["selected"] = float(trial["scale"]) == selected_scale
    return {
        "baseline_metrics": baseline_metrics,
        "selected_scale": selected_scale,
        "selected_state": candidate_states[selected_scale],
        "selected_trial": dict(selected_trial),
        "trials": trials,
    }


def select_largest_guard_safe_trial(
    trials: Iterable[Mapping[str, Any]],
    *,
    scale_key: str = "scale",
    guard_keys: tuple[str, ...] = ("metric_guard", "behavior_guard"),
    improvement_key: str = "improved",
) -> dict[str, Any] | None:
    """Select the largest positive scale with all guards and Pareto improvement.

    Selection is deterministic and intentionally refuses to infer improvement
    from a single scalar metric.  The caller must provide an explicit boolean
    improvement result that represents the campaign's declared Pareto rule.
    """

    eligible: list[tuple[float, int, dict[str, Any]]] = []
    for index, raw_trial in enumerate(trials):
        if not isinstance(raw_trial, Mapping):
            raise TypeError("viv_slm_governor_trial_must_be_mapping")
        try:
            scale = float(raw_trial[scale_key])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("viv_slm_governor_trial_scale_invalid") from error
        if not math.isfinite(scale) or not 0.0 <= scale <= 1.0:
            raise ValueError("viv_slm_governor_trial_scale_out_of_bounds")
        if scale <= 0.0:
            continue
        if not all(raw_trial.get(key) is True for key in guard_keys):
            continue
        if raw_trial.get(improvement_key) is not True:
            continue
        eligible.append((scale, index, dict(raw_trial)))
    if not eligible:
        return None
    _, _, selected = max(eligible, key=lambda item: (item[0], -item[1]))
    selected["selected"] = True
    return selected


def guarded_rollback_decision(
    *,
    guards: Mapping[str, bool],
    consecutive_guard_failures: int,
    max_consecutive_failures: int = MAX_CONSECUTIVE_GUARD_FAILURES,
) -> dict[str, Any]:
    """Calculate rollback and halt state from named guard results."""

    if not guards:
        raise ValueError("viv_slm_governor_guards_required")
    if int(consecutive_guard_failures) < 0:
        raise ValueError("viv_slm_governor_consecutive_failures_negative")
    if int(max_consecutive_failures) <= 0:
        raise ValueError("viv_slm_governor_failure_budget_invalid")
    normalized = {str(name): bool(value) for name, value in guards.items()}
    guard_ok = all(normalized.values())
    next_failures = 0 if guard_ok else int(consecutive_guard_failures) + 1
    failed_names = [name for name, passed in normalized.items() if not passed]
    return {
        "guard_results": normalized,
        "guard_ok": guard_ok,
        "rollback": not guard_ok,
        "halt": next_failures >= int(max_consecutive_failures),
        "consecutive_guard_failures": next_failures,
        "reason": "all_guards_passed" if guard_ok else "guard_failed:" + ",".join(failed_names),
    }


__all__ = [
    "adaptive_controller_update",
    "seed_controller_actuation_state",
    "LayerCampaignSpec",
    "MAX_CONSECUTIVE_GUARD_FAILURES",
    "ONE_INCREMENT_STEPS",
    "compose_parameter_state",
    "evaluate_scale_ladder",
    "guarded_rollback_decision",
    "parent_binding_matches",
    "require_one_increment",
    "select_largest_guard_safe_trial",
    "validate_layer_campaign_spec",
    "validate_authority_record",
]
