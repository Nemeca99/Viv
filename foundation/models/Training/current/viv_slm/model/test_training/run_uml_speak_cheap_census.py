#!/usr/bin/env python3
"""Measurement-only matched speak-cheap census for the live UML survivor.

This script never trains or writes a checkpoint. It isolates three route
surfaces over one fixed prompt manifest:

1. raw_no_snap: deep generator with no route bias and no post-generation snap.
2. plant_rid_policy: current soft thermal/RID generation-time bias, no snap.
3. prefer_efficient_snap: existing deterministic post-generation policy applied
   to the raw proposal (upper bound).
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import random
import statistics
import sys
from typing import Any, Callable, Iterable, Mapping, Sequence

import torch
from torch import Tensor

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
for _path in (FOUNDATION, MODEL, SANDBOX):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from lib.uml_equation_registry import (  # noqa: E402
    SANDBOX96_ARTIFACT,
    UMLEquationRegistry,
    _domains_in_expr,
)
from lib.uml_route_governor import route_efficiency_error  # noqa: E402
from plant_runtime import (  # noqa: E402
    configure_plant_runtime,
    detect_hardware,
    select_device,
)
from sandbox_codex_identity import resolve_codex_dataset  # noqa: E402
from speak_lanes import speak_viv  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from uml_speak_pressure import (  # noqa: E402
    UML_DEFAULT_STOPS,
    build_uml_speak_pressure,
    clip_uml_equation_text,
    infer_uml_target_from_prompt,
    resolve_equation_for_policy,
)
import run_uml_speak_ab_f as speak_eval  # noqa: E402

SURVIVOR = SANDBOX / "runs" / "uml_mix_layers" / "layer_survivor.pt"
OUT_ROOT = SANDBOX / "runs" / "uml_speak_cheap_census"
MASTER_RID_ARTIFACT = FOUNDATION / "artifacts" / "auto" / "master_rid.json"
OLD_N7_RECEIPT = SANDBOX / "runs" / "uml_speak_cheap_ab_a_latest.json"
ITEM76_ARM_A = (
    SANDBOX
    / "runs"
    / "uml_ood_blend_recover"
    / "blend_recover_20260807T075908Z.json"
)
ITEM76_ARM_B = (
    SANDBOX
    / "runs"
    / "uml_ood_blend_recover"
    / "blend_recover_20260807T080256Z.json"
)

SCHEMA_VERSION = "uml_speak_cheap_census_v1"
DEFAULT_SEED = 20260807
OLD_CHEAP_REFERENCE = 1.0 / 7.0

# These are existing prompt forms, generalized over sealed registry characters.
# Each provenance file is recorded and hashed in the emitted prompt manifest.
PROMPT_TEMPLATES: tuple[dict[str, str], ...] = (
    {
        "template_id": "dedicated_direct",
        "template": "What is the UML for '{target}'?\nViv: ",
        "source": "run_uml_speak_ab_f.py:PROMPTS",
    },
    {
        "template_id": "mix_prefer_efficient",
        "template": "User: Prefer efficient UML for {target}\nViv: ",
        "source": "build_uml_equation_mix_dataset.py:_dialogues",
    },
    {
        "template_id": "heldout_rank_unknown",
        "template": "User: Rank UML routes for {target}\nBest: unknown\nViv: ",
        "source": "run_uml_ood_probe.py:_ood_dialogues / heldout dialogues",
    },
    {
        "template_id": "heldout_equivalent",
        "template": "User: UML equivalent for {target}\nViv: ",
        "source": "run_uml_ood_probe.py:_ood_dialogues / heldout dialogues",
    },
)

PROVENANCE_FILES: tuple[Path, ...] = (
    SANDBOX / "run_uml_speak_ab_f.py",
    SANDBOX / "build_uml_equation_mix_dataset.py",
    SANDBOX / "run_uml_ood_probe.py",
    SANDBOX
    / "data"
    / "uml_real_heldout_v1"
    / "tensor_B_fresh"
    / "dialogues.txt",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _path_text(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_identity(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": _path_text(path),
        "sha256": _sha256_file(path),
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "mtime_utc": datetime.fromtimestamp(
            stat.st_mtime, timezone.utc
        ).isoformat(),
    }


def _canonical_json_sha(payload: Any) -> str:
    body = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(body.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _eligible_targets(registry: UMLEquationRegistry) -> list[str]:
    # Quote targets are excluded because the dedicated quoted form would make
    # prompt-target inference ambiguous. Whitespace is excluded because these
    # are one-equation speak rows rather than multi-surface codec rows.
    return [
        char
        for char in registry.vocab
        if char.isprintable()
        and not char.isspace()
        and char not in {"'", '"'}
    ]


def _balanced_counts(total: int, groups: int) -> list[int]:
    base, remainder = divmod(int(total), int(groups))
    return [base + (1 if index < remainder else 0) for index in range(groups)]


def build_prompt_rows(
    registry: UMLEquationRegistry,
    tokenizer: CharacterTokenizer,
    *,
    n: int,
    seed: int,
) -> list[dict[str, Any]]:
    """Build deterministic, unique rows balanced over four existing templates."""
    targets = _eligible_targets(registry)
    counts = _balanced_counts(n, len(PROMPT_TEMPLATES))
    if max(counts, default=0) > len(targets):
        raise ValueError(
            f"census_n_too_large_for_unique_balanced_templates:"
            f"n={n}:eligible={len(targets)}"
        )

    rows: list[dict[str, Any]] = []
    for template_index, (template, count) in enumerate(
        zip(PROMPT_TEMPLATES, counts)
    ):
        chosen = list(targets)
        random.Random(int(seed) + 1009 * (template_index + 1)).shuffle(chosen)
        for target in chosen[:count]:
            prompt = template["template"].format(target=target)
            inferred = infer_uml_target_from_prompt(
                prompt, vocab=registry.vocab
            )
            if inferred.get("target_char") != target:
                raise RuntimeError(
                    "census_prompt_target_inference_mismatch:"
                    f"template={template['template_id']}:"
                    f"target={target!r}:inferred={inferred!r}"
                )
            token_ids = tokenizer.encode(prompt)
            if len(token_ids) > 96:
                raise RuntimeError(
                    "census_prompt_too_long:"
                    f"template={template['template_id']}:tokens={len(token_ids)}"
                )
            row_index = len(rows)
            entry = registry.entries[target]
            rows.append(
                {
                    "example_id": f"SC77-{row_index:03d}",
                    "order": row_index,
                    "template_id": template["template_id"],
                    "template_source": template["source"],
                    "target_char": target,
                    "target_token_id": int(entry["token_id"]),
                    "prompt": prompt,
                    "prompt_tokens": len(token_ids),
                    "generation_seed": int(seed) + row_index,
                }
            )

    if len(rows) != int(n):
        raise RuntimeError(f"census_manifest_count:{len(rows)}!={n}")
    prompts = [str(row["prompt"]) for row in rows]
    if len(set(prompts)) != len(prompts):
        raise RuntimeError("census_manifest_duplicate_prompts")
    return rows


def _manifest_payload(
    rows: list[dict[str, Any]],
    registry: UMLEquationRegistry,
    *,
    seed: int,
    created_at: str,
) -> dict[str, Any]:
    provenance: list[dict[str, Any]] = []
    for path in PROVENANCE_FILES:
        if path.is_file():
            provenance.append(_file_identity(path))
        else:
            provenance.append(
                {
                    "path": _path_text(path),
                    "status": "MISSING",
                }
            )
    prompt_surface_sha = _canonical_json_sha(
        [
            {
                "example_id": row["example_id"],
                "order": row["order"],
                "target_char": row["target_char"],
                "prompt": row["prompt"],
                "generation_seed": row["generation_seed"],
            }
            for row in rows
        ]
    )
    payload: dict[str, Any] = {
        "schema_version": "uml_speak_cheap_prompt_manifest_v1",
        "created_at": created_at,
        "status": "FIXED",
        "seed": int(seed),
        "n": len(rows),
        "prompt_surface_sha256": prompt_surface_sha,
        "registry": {
            "path": _path_text(Path(SANDBOX96_ARTIFACT)),
            "registry_sha256": registry.registry_sha256(),
            "vocab_sha256": registry.vocab_sha256,
            "vocab_size": len(registry.vocab),
        },
        "design": {
            "selection": (
                "Balanced deterministic sampling without replacement from "
                "printable, non-whitespace, non-quote sealed registry characters."
            ),
            "template_counts": dict(
                Counter(str(row["template_id"]) for row in rows)
            ),
            "template_provenance": list(PROMPT_TEMPLATES),
            "claim": (
                "Representative fixed speak/mix/heldout prompt forms; no claim "
                "that examples are training-unseen."
            ),
        },
        "provenance_files": provenance,
        "rows": rows,
    }
    payload["manifest_sha256"] = _canonical_json_sha(payload)
    return payload


def _new_run_dir(root: Path, now: datetime) -> Path:
    base = root / now.strftime("census_%Y%m%dT%H%M%SZ")
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = Path(f"{base}_{suffix:02d}")
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _torch_generator(device: torch.device, seed: int) -> torch.Generator:
    generator = torch.Generator(device=device)
    generator.manual_seed(int(seed))
    return generator


def _generate_equation(
    model: torch.nn.Module,
    tokenizer: CharacterTokenizer,
    *,
    prompt: str,
    generator: torch.Generator,
    max_new_tokens: int,
    temperature: float,
    logits_bias_fn: Callable[[Tensor, Tensor], Tensor] | None,
) -> tuple[str, dict[str, Any]]:
    ids = torch.tensor([tokenizer.encode(prompt)], dtype=torch.long)
    result = speak_viv(
        model,
        ids,
        lane="deep",
        max_new_tokens=int(max_new_tokens),
        temperature=float(temperature),
        generator=generator,
        stop_sequences=UML_DEFAULT_STOPS,
        decode_fn=tokenizer.decode,
        logits_bias_fn=logits_bias_fn,
        stamp_master_rid=False,
        configure_runtime=False,
    )
    equation = clip_uml_equation_text(str(result.get("text") or ""), prompt)
    receipt = dict(result.get("receipt") or {})
    compact = {
        "path": receipt.get("path"),
        "device": receipt.get("device"),
        "temperature": receipt.get("temperature"),
        "max_new_tokens": receipt.get("max_new_tokens"),
        "new_tokens": receipt.get("new_tokens"),
        "logits_bias_fn": receipt.get("logits_bias_fn"),
        "stop_sequences": receipt.get("stop_sequences"),
        "dual_temp_receipt": receipt.get("dual_temp_receipt"),
    }
    return equation, compact


def _route_federation(equation: str, *, valid: bool) -> str:
    if not valid:
        return "INVALID"
    domains = _domains_in_expr(equation)
    return "".join(
        domain for domain in ("A", "S", "M", "D") if domain in domains
    ) or "LIT"


def _score_equation(
    registry: UMLEquationRegistry,
    row: Mapping[str, Any],
    *,
    mode: str,
    equation: str,
    generation: Mapping[str, Any] | None,
    policy: Mapping[str, Any] | None,
    unsupported_reason: str | None = None,
) -> dict[str, Any]:
    target = str(row["target_char"])
    proposed = str(equation or "").strip()
    info = route_efficiency_error(
        registry,
        proposed=proposed if proposed else "???",
        target_char=target,
    )
    decoded: str | None = None
    decode_error: str | None = None
    if proposed:
        try:
            decoded = registry.decode_eq(proposed)
        except Exception as exc:  # noqa: BLE001 - evidence row records cause
            decode_error = f"{type(exc).__name__}:{exc}"
    destination_match = decoded == target
    valid = bool(info.get("valid"))
    cheap = info.get("kind") == "valid_efficient"
    return {
        "example_id": row["example_id"],
        "order": row["order"],
        "template_id": row["template_id"],
        "target_char": target,
        "target_token_id": row["target_token_id"],
        "generation_seed": row["generation_seed"],
        "mode": mode,
        "equation": proposed,
        "decoded_char": decoded,
        "destination_match": destination_match,
        "seal_violation": not destination_match,
        "valid": valid,
        "cheap_route": cheap,
        "route_kind": info.get("kind"),
        "route_federation": _route_federation(proposed, valid=valid),
        "route_cost": info.get("proposed_cost"),
        "cheapest_route": info.get("cheapest"),
        "cheapest_cost": info.get("cheapest_cost"),
        "route_error": float(info.get("error") or 0.0),
        "reject_reason": info.get("reject_reason"),
        "decode_error": decode_error,
        "unsupported": unsupported_reason is not None,
        "unsupported_reason": unsupported_reason,
        "generation": dict(generation or {}),
        "policy": dict(policy or {}),
    }


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return float(statistics.fmean(values))


def _percentile(sorted_values: Sequence[float], percentile: float) -> float:
    if not sorted_values:
        raise ValueError("percentile_empty")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = (len(sorted_values) - 1) * float(percentile)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return float(
        sorted_values[lower]
        + (sorted_values[upper] - sorted_values[lower]) * fraction
    )


def _bootstrap_mean_ci(
    values: Sequence[float],
    *,
    reps: int,
    seed: int,
) -> list[float] | None:
    if not values:
        return None
    if len(values) == 1 or int(reps) <= 0:
        point = float(values[0]) if len(values) == 1 else float(
            statistics.fmean(values)
        )
        return [point, point]
    rng = random.Random(int(seed))
    n = len(values)
    samples: list[float] = []
    for _ in range(int(reps)):
        samples.append(
            sum(float(values[rng.randrange(n)]) for _ in range(n)) / n
        )
    samples.sort()
    return [
        _percentile(samples, 0.025),
        _percentile(samples, 0.975),
    ]


def _counter_payload(values: Iterable[str]) -> dict[str, dict[str, float | int]]:
    counter = Counter(values)
    total = sum(counter.values())
    return {
        key: {
            "count": int(count),
            "rate": float(count / total) if total else 0.0,
        }
        for key, count in sorted(
            counter.items(), key=lambda item: (-item[1], item[0])
        )
    }


def _aggregate_mode(
    mode: str,
    rows: list[dict[str, Any]],
    *,
    bootstrap_reps: int,
    seed: int,
) -> dict[str, Any]:
    n = len(rows)
    destination = [1.0 if row["destination_match"] else 0.0 for row in rows]
    cheap = [1.0 if row["cheap_route"] else 0.0 for row in rows]
    errors = [float(row["route_error"]) for row in rows]
    costs = [
        float(row["route_cost"])
        for row in rows
        if row.get("route_cost") is not None
    ]
    unsupported = [row for row in rows if row["unsupported"]]
    invalid = [row for row in rows if not row["valid"]]
    violations = [str(row["example_id"]) for row in rows if row["seal_violation"]]
    unsupported_reasons = _counter_payload(
        str(row.get("unsupported_reason") or "unspecified")
        for row in unsupported
    )
    invalid_reasons = _counter_payload(
        str(row.get("reject_reason") or row.get("decode_error") or "unspecified")
        for row in invalid
    )
    return {
        "mode": mode,
        "status": "SUPPORTED" if not unsupported else "PARTIAL",
        "n": n,
        "supported_n": n - len(unsupported),
        "unsupported_count": len(unsupported),
        "unsupported_reasons": unsupported_reasons,
        "valid_count": n - len(invalid),
        "valid_rate": float((n - len(invalid)) / n) if n else 0.0,
        "invalid_count": len(invalid),
        "invalid_reasons": invalid_reasons,
        "destination_match_count": int(sum(destination)),
        "destination_match_rate": _mean(destination),
        "destination_match_bootstrap_95_ci": _bootstrap_mean_ci(
            destination,
            reps=bootstrap_reps,
            seed=seed + 11,
        ),
        "cheap_route_count": int(sum(cheap)),
        "cheap_route_rate": _mean(cheap),
        "cheap_route_bootstrap_95_ci": _bootstrap_mean_ci(
            cheap,
            reps=bootstrap_reps,
            seed=seed + 12,
        ),
        "mean_route_cost": _mean(costs),
        "route_cost_valid_n": len(costs),
        "mean_route_cost_bootstrap_95_ci": _bootstrap_mean_ci(
            costs,
            reps=bootstrap_reps,
            seed=seed + 13,
        ),
        "mean_route_error": _mean(errors),
        "mean_route_error_bootstrap_95_ci": _bootstrap_mean_ci(
            errors,
            reps=bootstrap_reps,
            seed=seed + 14,
        ),
        "route_distribution": {
            "federation": _counter_payload(
                str(row["route_federation"]) for row in rows
            ),
            "kind": _counter_payload(str(row["route_kind"]) for row in rows),
            "exact_equation": _counter_payload(
                str(row["equation"]) if row["equation"] else "<EMPTY>"
                for row in rows
            ),
        },
        "seal_destination_violation_count": len(violations),
        "seal_destination_violation_example_ids": violations,
    }


def _matched_delta(
    raw_rows: list[dict[str, Any]],
    mode_rows: list[dict[str, Any]],
    *,
    bootstrap_reps: int,
    seed: int,
) -> dict[str, Any]:
    if [row["example_id"] for row in raw_rows] != [
        row["example_id"] for row in mode_rows
    ]:
        raise RuntimeError("census_matched_order_mismatch")

    destination = [
        float(bool(mode["destination_match"]))
        - float(bool(raw["destination_match"]))
        for raw, mode in zip(raw_rows, mode_rows)
    ]
    cheap = [
        float(bool(mode["cheap_route"])) - float(bool(raw["cheap_route"]))
        for raw, mode in zip(raw_rows, mode_rows)
    ]
    errors = [
        float(mode["route_error"]) - float(raw["route_error"])
        for raw, mode in zip(raw_rows, mode_rows)
    ]
    costs = [
        float(mode["route_cost"]) - float(raw["route_cost"])
        for raw, mode in zip(raw_rows, mode_rows)
        if raw.get("route_cost") is not None
        and mode.get("route_cost") is not None
    ]

    def metric(
        values: Sequence[float],
        *,
        metric_seed: int,
    ) -> dict[str, Any]:
        return {
            "delta": _mean(values),
            "matched_n": len(values),
            "bootstrap_95_ci": _bootstrap_mean_ci(
                values,
                reps=bootstrap_reps,
                seed=metric_seed,
            ),
        }

    return {
        "definition": "mode_minus_raw_on_identical_example_order",
        "destination_match_rate": metric(destination, metric_seed=seed + 21),
        "cheap_route_rate": metric(cheap, metric_seed=seed + 22),
        "mean_route_cost": metric(costs, metric_seed=seed + 23),
        "mean_route_error": metric(errors, metric_seed=seed + 24),
        "output_changed_count": sum(
            str(raw["equation"]) != str(mode["equation"])
            for raw, mode in zip(raw_rows, mode_rows)
        ),
    }


def _read_json_if_present(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _artifact_timestamp_age_seconds(
    payload: Mapping[str, Any] | None,
    *,
    now: datetime,
) -> float | None:
    value = (payload or {}).get("timestamp")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return float((now - parsed.astimezone(timezone.utc)).total_seconds())


def _comparability_receipt() -> dict[str, Any]:
    old = _read_json_if_present(OLD_N7_RECEIPT)
    arm_a = _read_json_if_present(ITEM76_ARM_A)
    arm_b = _read_json_if_present(ITEM76_ARM_B)
    return {
        "old_n7": {
            "receipt": _path_text(OLD_N7_RECEIPT),
            "n": 7,
            "cheap_rate": (
                ((old or {}).get("gate") or {}).get("survivor_cheap_rate")
            ),
            "surface": (
                "run_uml_speak_ab_f.PROMPTS; hard_mask=True, scale=6 thermal "
                "generation pressure; sandwich auto-snap applies only to the "
                "Prefer-efficient prompt."
            ),
        },
        "item76_arm_a": {
            "receipt": _path_text(ITEM76_ARM_A),
            "n": 10,
            "cheap_rate": (
                ((arm_a or {}).get("fresh_ood_C") or {}).get("speak_cheap")
            ),
            "surface": (
                "run_uml_ood_probe.OOD_SPEAK_TEMPLATES; hard_mask=True, "
                "scale=6 thermal generation pressure; two Prefer-efficient "
                "templates are eligible for sandwich auto-snap."
            ),
        },
        "item76_arm_b": {
            "receipt": _path_text(ITEM76_ARM_B),
            "n": 10,
            "cheap_rate": (
                ((arm_b or {}).get("fresh_ood_C") or {}).get("speak_cheap")
            ),
            "surface": "Same hybrid n=10 OOD speak surface as Arm A.",
        },
        "conclusion": (
            "The historical 0.143 and item-76 0.3/0.4 are not directly "
            "comparable to each other or to an isolated census mode: prompt "
            "sets, n, survivor snapshots, and snap-eligible row counts differ, "
            "and both historical evaluators mix hard generation pressure with "
            "conditional post-snap behavior."
        ),
    }


def _ci_excludes_zero_positive(ci: Sequence[float] | None) -> bool:
    return bool(ci is not None and len(ci) == 2 and float(ci[0]) > 0.0)


def _ci_excludes_zero_negative(ci: Sequence[float] | None) -> bool:
    return bool(ci is not None and len(ci) == 2 and float(ci[1]) < 0.0)


def _classify(
    aggregates: Mapping[str, Mapping[str, Any]],
    deltas: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    raw = aggregates["raw_no_snap"]
    plant = aggregates["plant_rid_policy"]
    snap = aggregates["prefer_efficient_snap"]
    seal_breaks = {
        mode: int(metrics["seal_destination_violation_count"])
        for mode, metrics in aggregates.items()
        if int(metrics["seal_destination_violation_count"]) > 0
    }
    if seal_breaks:
        return {
            "classification": "SEAL_GUARD_STOP",
            "reason": (
                "At least one evaluated mode produced a destination/seal "
                f"violation: {seal_breaks}."
            ),
            "next_experiment": None,
        }
    if plant.get("status") != "SUPPORTED":
        return {
            "classification": "INCONCLUSIVE",
            "reason": "Plant/RID mode was not fully executable on all rows.",
            "next_experiment": None,
        }

    raw_rate = float(raw["cheap_route_rate"])
    plant_rate = float(plant["cheap_route_rate"])
    snap_rate = float(snap["cheap_route_rate"])
    raw_ci = raw.get("cheap_route_bootstrap_95_ci")
    plant_delta = deltas["plant_rid_policy"]["cheap_route_rate"]
    plant_cost_delta = deltas["plant_rid_policy"]["mean_route_cost"]

    raw_material = (
        raw_rate - OLD_CHEAP_REFERENCE >= 0.05
        and raw_ci is not None
        and float(raw_ci[0]) > OLD_CHEAP_REFERENCE
    )
    plant_material = (
        float(plant_delta.get("delta") or 0.0) >= 0.05
        and _ci_excludes_zero_positive(plant_delta.get("bootstrap_95_ci"))
    ) or (
        float(plant_cost_delta.get("delta") or 0.0) <= -0.10
        and _ci_excludes_zero_negative(
            plant_cost_delta.get("bootstrap_95_ci")
        )
    )

    if raw_material:
        return {
            "classification": "RAW_CLIMBING",
            "reason": (
                "Raw no-snap cheapness clears the old 1/7 point reference by "
                "at least 0.05 and its prompt-resampling CI stays above 1/7; "
                "historical-surface comparability remains limited."
            ),
            "next_experiment": None,
        }
    if raw_rate < 0.5 and plant_material:
        return {
            "classification": "PLANT_LEVER",
            "reason": (
                "Raw cheapness is low and the distinct soft plant/RID mode "
                "materially improves cheapness or cost with a CI excluding zero."
            ),
            "next_experiment": None,
        }
    if raw_rate < 0.5 and plant_rate < 0.5 and snap_rate >= 0.95:
        return {
            "classification": "SOFT_BIAS_NEXT",
            "reason": (
                "Raw and current soft plant/RID routing remain low while the "
                "existing deterministic snap upper bound is near one."
            ),
            "next_experiment": (
                "Run a measurement-gated generation-time soft cost-bias A/B "
                "over this fixed manifest; do not add mix training."
            ),
        }
    return {
        "classification": "INCONCLUSIVE",
        "reason": (
            "Observed differences do not meet a seal-safe materiality rule with "
            "prompt-resampling uncertainty."
        ),
        "next_experiment": None,
    }


def _selftest() -> int:
    _, vocab_path, _ = resolve_codex_dataset("v61")
    tokenizer = CharacterTokenizer.from_manifest(vocab_path)
    registry = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    failures: list[str] = []

    rows_a = build_prompt_rows(
        registry, tokenizer, n=256, seed=DEFAULT_SEED
    )
    rows_b = build_prompt_rows(
        registry, tokenizer, n=256, seed=DEFAULT_SEED
    )
    if rows_a != rows_b:
        failures.append("manifest_not_deterministic")
    if len(rows_a) != 256 or len({row["prompt"] for row in rows_a}) != 256:
        failures.append("manifest_n_or_uniqueness")
    counts = Counter(row["template_id"] for row in rows_a)
    if sorted(counts.values()) != [64, 64, 64, 64]:
        failures.append(f"manifest_balance:{dict(counts)}")

    canonical = registry.encode_char("H")
    cheap = route_efficiency_error(
        registry, proposed=canonical, target_char="H"
    )
    alternatives = list(registry.entries["H"].get("equivalents") or [])
    costly_expr = next(
        (
            expr
            for expr in alternatives
            if route_efficiency_error(
                registry, proposed=str(expr), target_char="H"
            )["kind"]
            == "valid_costly"
        ),
        None,
    )
    if cheap["kind"] != "valid_efficient" or cheap["error"] != 0.0:
        failures.append(f"canonical_score:{cheap}")
    if costly_expr is None:
        failures.append("missing_costly_selftest_route")
    if _bootstrap_mean_ci([1.0] * 8, reps=100, seed=7) != [1.0, 1.0]:
        failures.append("bootstrap_constant")

    status = "PASS" if not failures else "FAIL"
    print(
        f"UML_SPEAK_CHEAP_CENSUS_SELFTEST_{status} "
        f"rows={len(rows_a)} failures={len(failures)}",
        flush=True,
    )
    for failure in failures:
        print(f"FAIL {failure}", flush=True)
    return 0 if not failures else 1


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ckpt", type=Path, default=SURVIVOR)
    parser.add_argument("--n", type=int, default=256)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--max-new-tokens", type=int, default=24)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--plant-scale", type=float, default=6.0)
    parser.add_argument("--bootstrap-reps", type=int, default=5000)
    parser.add_argument("--out-root", type=Path, default=OUT_ROOT)
    parser.add_argument("--selftest", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.selftest:
        return _selftest()
    if int(args.n) != 256:
        raise ValueError(
            "thesis_item_77_requires_n_256; use --selftest for a no-model check"
        )
    if not args.ckpt.is_file():
        raise FileNotFoundError(args.ckpt)
    if int(args.max_new_tokens) <= 0:
        raise ValueError("max_new_tokens_must_be_positive")
    if float(args.temperature) < 0.0:
        raise ValueError("temperature_must_be_nonnegative")
    if int(args.bootstrap_reps) < 0:
        raise ValueError("bootstrap_reps_must_be_nonnegative")

    started = _utc_now()
    checkpoint_before = _file_identity(args.ckpt)
    plant_artifact_payload = _read_json_if_present(MASTER_RID_ARTIFACT)
    plant_artifact_before = (
        _file_identity(MASTER_RID_ARTIFACT)
        if MASTER_RID_ARTIFACT.is_file()
        else None
    )
    run_dir = _new_run_dir(args.out_root, started)

    _, vocab_path, _ = resolve_codex_dataset("v61")
    tokenizer = CharacterTokenizer.from_manifest(vocab_path)
    registry = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    prompt_rows = build_prompt_rows(
        registry,
        tokenizer,
        n=int(args.n),
        seed=int(args.seed),
    )
    manifest = _manifest_payload(
        prompt_rows,
        registry,
        seed=int(args.seed),
        created_at=started.isoformat(),
    )
    manifest_path = run_dir / "prompt_manifest.json"
    _write_json(manifest_path, manifest)

    device = select_device(str(args.device))
    # speak_viv's deep lane has a dedicated selector. Pin it within this process
    # so --device controls both model loading and generation.
    os.environ["VIV_SPEAK_DEEP_DEVICE"] = str(device)
    runtime = configure_plant_runtime(device=str(device))
    torch.manual_seed(int(args.seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(args.seed))
    torch.set_grad_enabled(False)

    model = speak_eval._load(args.ckpt, tokenizer, device)
    model.eval()

    mode_rows: dict[str, list[dict[str, Any]]] = {
        "raw_no_snap": [],
        "plant_rid_policy": [],
        "prefer_efficient_snap": [],
    }

    with torch.inference_mode():
        for index, prompt_row in enumerate(prompt_rows):
            prompt = str(prompt_row["prompt"])
            target = str(prompt_row["target_char"])
            generation_seed = int(prompt_row["generation_seed"])

            raw_equation = ""
            raw_generation: dict[str, Any] = {}
            raw_error: str | None = None
            try:
                raw_equation, raw_generation = _generate_equation(
                    model,
                    tokenizer,
                    prompt=prompt,
                    generator=_torch_generator(device, generation_seed),
                    max_new_tokens=int(args.max_new_tokens),
                    temperature=float(args.temperature),
                    logits_bias_fn=None,
                )
            except Exception as exc:  # noqa: BLE001 - evidence row records cause
                raw_error = f"{type(exc).__name__}:{exc}"
            raw_scored = _score_equation(
                registry,
                prompt_row,
                mode="raw_no_snap",
                equation=raw_equation,
                generation=raw_generation,
                policy={
                    "enabled": False,
                    "post_snap": False,
                    "description": "No logits bias; direct deep generator output.",
                },
                unsupported_reason=raw_error,
            )
            mode_rows["raw_no_snap"].append(raw_scored)

            plant_equation = ""
            plant_generation: dict[str, Any] = {}
            plant_receipt: dict[str, Any] = {}
            plant_error: str | None = None
            try:
                prompt_len = len(tokenizer.encode(prompt))
                bias_fn, plant_receipt = build_uml_speak_pressure(
                    stoi=tokenizer.stoi,
                    itos=tokenizer.itos,
                    prompt_len=prompt_len,
                    target_char=target,
                    auto_target=False,
                    scale=float(args.plant_scale),
                    hard_mask=False,
                    include_registry_pool=True,
                )
                plant_equation, plant_generation = _generate_equation(
                    model,
                    tokenizer,
                    prompt=prompt,
                    generator=_torch_generator(device, generation_seed),
                    max_new_tokens=int(args.max_new_tokens),
                    temperature=float(args.temperature),
                    logits_bias_fn=bias_fn,
                )
            except Exception as exc:  # noqa: BLE001 - evidence row records cause
                plant_error = f"{type(exc).__name__}:{exc}"
            plant_policy = dict(plant_receipt)
            plant_policy.update(
                {
                    "mode_contract": (
                        "Soft generation-time thermal/RID pressure only; "
                        "hard_mask=False; no post-generation snap."
                    ),
                    "post_snap": False,
                }
            )
            plant_scored = _score_equation(
                registry,
                prompt_row,
                mode="plant_rid_policy",
                equation=plant_equation,
                generation=plant_generation,
                policy=plant_policy,
                unsupported_reason=plant_error,
            )
            mode_rows["plant_rid_policy"].append(plant_scored)

            snap_equation = ""
            snap_receipt: dict[str, Any] = {}
            snap_error: str | None = None
            if raw_error is not None:
                snap_error = f"raw_dependency:{raw_error}"
            else:
                try:
                    snap_receipt = resolve_equation_for_policy(
                        equation_text=raw_equation,
                        prompt_text=prompt,
                        registry=registry,
                        policy="prefer_efficient",
                    )
                    snap_equation = str(
                        snap_receipt.get("equation_text") or ""
                    )
                    inferred = (
                        snap_receipt.get("inferred") or {}
                    ).get("target_char")
                    if inferred != target:
                        raise RuntimeError(
                            f"snap_target_mismatch:{inferred!r}!={target!r}"
                        )
                except Exception as exc:  # noqa: BLE001 - evidence row
                    snap_error = f"{type(exc).__name__}:{exc}"
            snap_policy = dict(snap_receipt)
            snap_policy.update(
                {
                    "mode_contract": (
                        "Existing deterministic prefer_efficient post-policy "
                        "applied to raw_no_snap proposal."
                    ),
                    "derived_from": "raw_no_snap",
                    "post_snap": True,
                }
            )
            snap_scored = _score_equation(
                registry,
                prompt_row,
                mode="prefer_efficient_snap",
                equation=snap_equation,
                generation={
                    "derived_from": "raw_no_snap",
                    "generation_seed": generation_seed,
                },
                policy=snap_policy,
                unsupported_reason=snap_error,
            )
            mode_rows["prefer_efficient_snap"].append(snap_scored)

            if (index + 1) % 16 == 0 or index + 1 == len(prompt_rows):
                print(
                    f"CENSUS_PROGRESS {index + 1}/{len(prompt_rows)} "
                    f"raw={raw_equation!r} plant={plant_equation!r} "
                    f"snap={snap_equation!r}",
                    flush=True,
                )

    checkpoint_after = _file_identity(args.ckpt)
    unchanged = checkpoint_before == checkpoint_after
    if not unchanged:
        raise RuntimeError(
            "census_checkpoint_identity_changed:"
            f"before={checkpoint_before}:after={checkpoint_after}"
        )
    plant_artifact_after = (
        _file_identity(MASTER_RID_ARTIFACT)
        if MASTER_RID_ARTIFACT.is_file()
        else None
    )
    plant_artifact = {
        "before": plant_artifact_before,
        "after": plant_artifact_after,
        "unchanged_during_census": (
            plant_artifact_before == plant_artifact_after
        ),
        "declared_timestamp": (
            (plant_artifact_payload or {}).get("timestamp")
        ),
        "age_seconds_at_start": _artifact_timestamp_age_seconds(
            plant_artifact_payload,
            now=started,
        ),
        "refreshed_by_census": False,
    }

    aggregates = {
        mode: _aggregate_mode(
            mode,
            rows,
            bootstrap_reps=int(args.bootstrap_reps),
            seed=int(args.seed) + 10000 * mode_index,
        )
        for mode_index, (mode, rows) in enumerate(mode_rows.items(), start=1)
    }
    deltas = {
        mode: _matched_delta(
            mode_rows["raw_no_snap"],
            mode_rows[mode],
            bootstrap_reps=int(args.bootstrap_reps),
            seed=int(args.seed) + 20000 * mode_index,
        )
        for mode_index, mode in enumerate(
            ("plant_rid_policy", "prefer_efficient_snap"), start=1
        )
    }
    classification = _classify(aggregates, deltas)

    plant_policy_names = Counter(
        str(((row.get("policy") or {}).get("decision") or {}).get("policy"))
        for row in mode_rows["plant_rid_policy"]
    )
    plant_sources = Counter(
        str(
            (
                (
                    ((row.get("policy") or {}).get("decision") or {}).get(
                        "plant"
                    )
                    or {}
                ).get("source")
            )
        )
        for row in mode_rows["plant_rid_policy"]
    )
    plant_distinct = {
        "supported": (
            aggregates["plant_rid_policy"]["status"] == "SUPPORTED"
        ),
        "genuinely_distinct_generation_path": True,
        "hook": (
            "uml_speak_pressure.build_uml_speak_pressure -> "
            "lib.uml_thermal_route.decide_route_thermal -> "
            "lib.uml_route_governor.make_generate_logits_bias_fn"
        ),
        "soft_bias": True,
        "hard_mask": False,
        "scale": float(args.plant_scale),
        "post_snap": False,
        "policy_counts": dict(plant_policy_names),
        "plant_source_counts": dict(plant_sources),
        "plant_input_artifact": plant_artifact,
        "output_changed_vs_raw_count": deltas["plant_rid_policy"][
            "output_changed_count"
        ],
        "note": (
            "The policy read the existing master_rid artifact through "
            "read_plant_thermal. This receipt records its file identity and "
            "declared timestamp; the census did not refresh it."
        ),
    }

    finished = _utc_now()
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": "thesis_item_77_speak_cheap_census",
        "status": "PASS_MEASUREMENT_COMPLETE",
        "classification": classification,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "elapsed_seconds": (finished - started).total_seconds(),
        "measurement_only": True,
        "training_performed": False,
        "checkpoint_written": False,
        "checkpoint_identity": {
            "before": checkpoint_before,
            "after": checkpoint_after,
            "unchanged": unchanged,
        },
        "prompt_manifest": {
            "path": _path_text(manifest_path),
            "manifest_sha256": manifest["manifest_sha256"],
            "prompt_surface_sha256": manifest["prompt_surface_sha256"],
            "n": manifest["n"],
            "seed": manifest["seed"],
        },
        "exact_cli": [str(Path(sys.executable).resolve()), *sys.argv],
        "config": {
            "checkpoint": _path_text(args.ckpt),
            "n": int(args.n),
            "seed": int(args.seed),
            "device_requested": str(args.device),
            "device_effective": str(device),
            "max_new_tokens": int(args.max_new_tokens),
            "temperature": float(args.temperature),
            "deep_generation": (
                "speak_lanes.speak_viv lane=deep; current explore-then-lock "
                "schedule; identical per-row generator seeds in raw/plant."
            ),
            "plant_scale": float(args.plant_scale),
            "plant_hard_mask": False,
            "bootstrap_reps": int(args.bootstrap_reps),
            "bootstrap_scope": (
                "Percentile bootstrap over fixed prompt rows; generation seeds "
                "are fixed, so intervals do not estimate repeated-decode noise."
            ),
        },
        "runtime": {
            "python": platform.python_version(),
            "python_executable": str(Path(sys.executable).resolve()),
            "torch": str(torch.__version__),
            "runtime_config": runtime.as_dict(),
            "hardware": detect_hardware(),
            "grad_enabled_during_receipt_write": bool(
                torch.is_grad_enabled()
            ),
            "model_training_flag": bool(model.training),
        },
        "metric_definitions": {
            "destination_match": (
                "registry.decode_eq(proposed_equation) == sealed target_char"
            ),
            "cheap_route": (
                "lib.uml_route_governor.route_efficiency_error.kind == "
                "'valid_efficient'"
            ),
            "route_cost": {
                "name": "symbolic_cost",
                "units": "parsed UML AST nodes",
                "formula": (
                    "uml_engine.uml_cost: symbolic_cost = ast_nodes = "
                    "1 + sum(child AST nodes); each leaf is one node."
                ),
                "source": (
                    "lib.uml_equation_registry._symbolic_cost -> "
                    "lib.uml_engine.uml_cost()['symbolic_cost']"
                ),
                "mean_denominator": (
                    "Rows with a valid parsed proposed_cost; denominator "
                    "reported as route_cost_valid_n."
                ),
            },
            "route_error": {
                "formula": (
                    "invalid/nonmatching -> 1.0; otherwise "
                    "max(0, proposed_cost-cheapest_cost)/(proposed_cost+1)"
                ),
                "source": (
                    "lib.uml_route_governor.route_efficiency_error"
                ),
                "mean_denominator": "All manifest rows; unsupported rows score invalid.",
            },
            "route_federation": (
                "Existing lib.uml_equation_registry._domains_in_expr tags "
                "ordered A/S/M/D, or LIT."
            ),
        },
        "modes": {
            mode: {
                "aggregate": aggregates[mode],
                "rows": mode_rows[mode],
            }
            for mode in mode_rows
        },
        "matched_deltas_relative_to_raw": deltas,
        "plant_rid_mode": plant_distinct,
        "historical_comparability": _comparability_receipt(),
        "artifacts": {
            "run_dir": _path_text(run_dir),
            "prompt_manifest": _path_text(manifest_path),
            "census_json": _path_text(run_dir / "census.json"),
            "script": _path_text(Path(__file__)),
        },
        "safety": {
            "model_eval": not bool(model.training),
            "torch_inference_mode_used": True,
            "optimizer_created": False,
            "backward_called": False,
            "trainer_invoked": False,
            "checkpoint_hash_unchanged": unchanged,
            "checkpoint_size_mtime_unchanged": (
                checkpoint_before["size_bytes"]
                == checkpoint_after["size_bytes"]
                and checkpoint_before["mtime_ns"]
                == checkpoint_after["mtime_ns"]
            ),
        },
    }
    receipt["receipt_sha256"] = _canonical_json_sha(receipt)
    census_path = run_dir / "census.json"
    _write_json(census_path, receipt)

    print(
        "UML_SPEAK_CHEAP_CENSUS_"
        f"{classification['classification']} "
        + " ".join(
            f"{mode}=match:{float(aggregates[mode]['destination_match_rate']):.3f},"
            f"cheap:{float(aggregates[mode]['cheap_route_rate']):.3f},"
            f"cost:{float(aggregates[mode]['mean_route_cost'] or 0.0):.3f},"
            f"err:{float(aggregates[mode]['mean_route_error']):.3f}"
            for mode in mode_rows
        ),
        flush=True,
    )
    print(
        f"CENSUS_EVIDENCE manifest={manifest_path} census={census_path} "
        f"checkpoint_sha256={checkpoint_after['sha256']} unchanged={unchanged}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
