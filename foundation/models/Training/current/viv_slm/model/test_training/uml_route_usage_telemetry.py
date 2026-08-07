#!/usr/bin/env python3
"""Schema-locked aggregate route telemetry for promotion-frequency evidence.

The service kernel must not log every request; that would destroy the measured
nanosecond economics and generate unbounded logs. A supervising runtime records
bounded windows after execution:

  event = uml_route_window
  total_requests
  federation_counts (including U_AM)
  duration_ns / errors / stalls / heartbeat_progressed

Only rows with ``source="production"`` count toward promotion. Test and sandbox
rows use the same schema but are rejected by the promotion gate.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

SCHEMA_VERSION = "uml_route_usage_v1"
EVENT = "uml_route_window"
VALID_SOURCES = frozenset({"production", "test", "sandbox"})
VALID_FEDERATIONS = frozenset(
    {
        "U_AS",
        "U_AM",
        "U_AD",
        "U_SM",
        "U_SD",
        "U_MD",
        "U_ASM",
        "U_ASD",
        "U_AMD",
        "U_SMD",
        "U_ASMD",
    }
)
_WRITE_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RouteUsageWindow:
    schema_version: str
    event: str
    source: str
    experiment_id: str
    window_id: str
    actor: str
    started_at: str
    finished_at: str
    total_requests: int
    federation_counts: dict[str, int]
    duration_ns: int
    errors: int
    stalls: int
    heartbeat_progressed: bool
    outcome: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_route_usage_window(
    *,
    source: str,
    experiment_id: str,
    actor: str,
    started_at: str,
    total_requests: int,
    federation_counts: Mapping[str, int],
    duration_ns: int,
    errors: int = 0,
    stalls: int = 0,
    heartbeat_progressed: bool = True,
    outcome: str = "PASS",
    finished_at: str | None = None,
    window_id: str | None = None,
) -> RouteUsageWindow:
    """Validate and build one aggregate telemetry window."""
    source_norm = str(source).strip().lower()
    if source_norm not in VALID_SOURCES:
        raise ValueError(f"uml_route_usage_invalid_source:{source!r}")
    experiment = str(experiment_id).strip()
    if not experiment:
        raise ValueError("uml_route_usage_experiment_id_required")
    actor_norm = str(actor).strip()
    if not actor_norm:
        raise ValueError("uml_route_usage_actor_required")
    if int(total_requests) <= 0:
        raise ValueError("uml_route_usage_total_requests_must_be_positive")
    if int(duration_ns) < 0 or int(errors) < 0 or int(stalls) < 0:
        raise ValueError("uml_route_usage_negative_counter")

    normalized: dict[str, int] = {}
    for label, count in federation_counts.items():
        federation = str(label).strip().replace("+", "_")
        if federation not in VALID_FEDERATIONS:
            raise ValueError(f"uml_route_usage_unknown_federation:{label!r}")
        value = int(count)
        if value < 0:
            raise ValueError(f"uml_route_usage_negative_federation_count:{federation}")
        normalized[federation] = normalized.get(federation, 0) + value
    if not normalized:
        raise ValueError("uml_route_usage_federation_counts_required")
    if sum(normalized.values()) > int(total_requests):
        raise ValueError("uml_route_usage_counts_exceed_total")

    outcome_norm = str(outcome).strip().upper()
    if outcome_norm not in {"PASS", "DEGRADED", "FAIL", "INCONCLUSIVE"}:
        raise ValueError(f"uml_route_usage_invalid_outcome:{outcome!r}")
    return RouteUsageWindow(
        schema_version=SCHEMA_VERSION,
        event=EVENT,
        source=source_norm,
        experiment_id=experiment,
        window_id=str(window_id or uuid.uuid4()),
        actor=actor_norm,
        started_at=str(started_at),
        finished_at=str(finished_at or _utc_now()),
        total_requests=int(total_requests),
        federation_counts=normalized,
        duration_ns=int(duration_ns),
        errors=int(errors),
        stalls=int(stalls),
        heartbeat_progressed=bool(heartbeat_progressed),
        outcome=outcome_norm,
    )


def append_route_usage_window(path: str | Path, window: RouteUsageWindow) -> Path:
    """Append one validated JSONL row with flush+fsync audit durability."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(window.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
    with _WRITE_LOCK:
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    return target


__all__ = [
    "EVENT",
    "SCHEMA_VERSION",
    "RouteUsageWindow",
    "append_route_usage_window",
    "build_route_usage_window",
]
