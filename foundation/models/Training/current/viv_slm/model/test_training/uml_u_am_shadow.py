#!/usr/bin/env python3
"""Opt-in U_AM shadow observer.

The authoritative path remains ``uml_engine.evaluate``. This observer:
  - recognizes concrete variable-input shapes equivalent to ``(x+y)*z``;
  - executes the isolated U_AM DLL only in shadow;
  - fails closed on any parity mismatch;
  - aggregates bounded route-usage windows outside the service timing;
  - never returns, selects, caches, or installs the candidate result.

Production use requires an explicit experiment id, telemetry path, and source.
Unset/unused means zero overhead except one disabled observer check in evaluate.
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
for path in (FOUNDATION, MODEL, SANDBOX):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib import uml_engine
from lib.uml_guarded_canonicalize import federation_route_node
from uml_route_usage_telemetry import (
    VALID_FEDERATIONS,
    append_route_usage_window,
    build_route_usage_window,
)

DEFAULT_DLL = SANDBOX / "runs" / "uml_mixed_cost" / "uml_u_am_v1.dll"
DEFAULT_TELEMETRY = SANDBOX / "runs" / "uml_route_usage.jsonl"
_DOMAIN_KIND = {"add": "A", "sub": "S", "mul": "M", "div": "D"}
_SCALAR_KINDS = frozenset({"num", "var", "const"})
_I64_MIN = -(2**63)
_I64_MAX = 2**63 - 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _domains(node: uml_engine.Node) -> frozenset[str]:
    found: set[str] = set()

    def walk(current: uml_engine.Node) -> None:
        domain = _DOMAIN_KIND.get(current.kind)
        if domain:
            found.add(domain)
        for child in current.children:
            walk(child)

    walk(node)
    return frozenset(found)


def _federation(domains: frozenset[str]) -> str | None:
    if len(domains) < 2:
        return None
    label = "U_" + "".join(
        domain for domain in ("A", "S", "M", "D") if domain in domains
    )
    return label if label in VALID_FEDERATIONS else None


def _i64_scalar(node: uml_engine.Node) -> int | None:
    if node.kind not in _SCALAR_KINDS or node.children:
        return None
    value = node.value
    if isinstance(value, complex) or value is None:
        return None
    numeric = float(value)
    if not numeric.is_integer():
        return None
    integer = int(numeric)
    if integer < _I64_MIN or integer > _I64_MAX:
        return None
    return integer


def _u_am_inputs(node: uml_engine.Node) -> tuple[int, int, int] | None:
    """Return x,y,z only for one ADD feeding one MUL."""
    if node.kind != "mul" or len(node.children) != 2:
        return None
    left, right = node.children
    if left.kind == "add" and len(left.children) == 2:
        add_node, z_node = left, right
    elif right.kind == "add" and len(right.children) == 2:
        add_node, z_node = right, left
    else:
        return None
    x = _i64_scalar(add_node.children[0])
    y = _i64_scalar(add_node.children[1])
    z = _i64_scalar(z_node)
    if x is None or y is None or z is None:
        return None
    expected = (x + y) * z
    if expected < _I64_MIN or expected > _I64_MAX:
        return None
    return x, y, z


class UAMShadowObserver:
    """Aggregate observer installed as the sole UML evaluator shadow writer."""

    def __init__(
        self,
        *,
        experiment_id: str,
        source: str,
        telemetry_path: str | Path = DEFAULT_TELEMETRY,
        dll_path: str | Path = DEFAULT_DLL,
        flush_every: int = 10_000,
    ) -> None:
        self.experiment_id = str(experiment_id).strip()
        self.source = str(source).strip().lower()
        self.telemetry_path = Path(telemetry_path)
        self.dll_path = Path(dll_path)
        self.flush_every = int(flush_every)
        if not self.experiment_id:
            raise ValueError("uml_u_am_shadow_experiment_id_required")
        minimum = 1_000 if self.source == "production" else 1
        if self.flush_every < minimum or self.flush_every > 1_000_000:
            raise ValueError(
                f"uml_u_am_shadow_flush_every_out_of_range:{self.flush_every}:"
                f"minimum={minimum}"
            )
        if not self.dll_path.is_file():
            raise FileNotFoundError(self.dll_path)

        library = ctypes.CDLL(str(self.dll_path))
        function = library.uml_u_am_v1
        function.argtypes = (ctypes.c_int64, ctypes.c_int64, ctypes.c_int64)
        function.restype = ctypes.c_int64
        marker = library.uml_u_am_v1_contract
        marker.argtypes = ()
        marker.restype = ctypes.c_uint64
        if int(marker()) != 0x0055_5F41_4D5F_5631:
            raise RuntimeError("uml_u_am_shadow_contract_marker_mismatch")
        self._library = library
        self._function = function
        self._lock = threading.RLock()
        self._active = False
        self._reset_window()

    def _reset_window(self) -> None:
        self._window_started_at = _utc_now()
        self._window_started_ns = time.perf_counter_ns()
        self._total = 0
        self._counts: dict[str, int] = {}
        self._errors = 0
        self._candidate_checks = 0
        self._am_domain_nonmacro = 0

    def start(self) -> "UAMShadowObserver":
        with self._lock:
            if self._active:
                return self
            uml_engine.install_evaluation_observer(
                self,
                experiment_id=self.experiment_id,
                fail_closed=True,
            )
            self._active = True
        return self

    def __call__(
        self,
        expr: str,
        node: uml_engine.Node,
        authoritative_value: Any,
        _notation: str,
    ) -> None:
        with self._lock:
            self._total += 1
            # Macro shape checks use the raw AST. Federation demand uses
            # effective domains after guarded U cancel (default ON) so
            # (V*K)/K drag never counts as U_MD.
            raw_domains = _domains(node)
            _route_node, eff_domains, _cancel = federation_route_node(
                str(expr),
                node=node,
                authoritative_value=authoritative_value,
            )
            label = _federation(eff_domains)
            candidate_inputs = (
                _u_am_inputs(node) if raw_domains == {"A", "M"} else None
            )

            # Count U_AM only when this exact persistent macro could serve it.
            if candidate_inputs is not None:
                label = "U_AM"
                self._counts[label] = self._counts.get(label, 0) + 1
                x, y, z = candidate_inputs
                candidate_value = int(self._function(x, y, z))
                self._candidate_checks += 1
                if isinstance(authoritative_value, complex):
                    parity = False
                else:
                    parity = float(authoritative_value).is_integer() and (
                        int(authoritative_value) == candidate_value
                    )
                if not parity:
                    self._errors += 1
                    raise RuntimeError(
                        "uml_u_am_shadow_parity_mismatch:"
                        f"authoritative={authoritative_value!r}:candidate={candidate_value!r}"
                    )
            elif label == "U_AM":
                # A+M domains in a shape this macro cannot serve (e.g. (x*y)+z).
                # Diagnostic only: real federation demand, but not macro-eligible,
                # so it must not inflate the binding U_AM window count.
                self._am_domain_nonmacro += 1
            elif label is not None:
                self._counts[label] = self._counts.get(label, 0) + 1

            if self._total >= self.flush_every:
                self.flush()

    def flush(self) -> None:
        with self._lock:
            if self._total <= 0:
                return
            finished_at = _utc_now()
            duration_ns = time.perf_counter_ns() - self._window_started_ns
            outcome = "PASS" if self._errors == 0 else "FAIL"
            window = build_route_usage_window(
                source=self.source,
                experiment_id=self.experiment_id,
                actor="uml_u_am_shadow_v1",
                started_at=self._window_started_at,
                finished_at=finished_at,
                total_requests=self._total,
                federation_counts=self._counts or {"U_AM": 0},
                duration_ns=duration_ns,
                errors=self._errors,
                stalls=0,
                heartbeat_progressed=self._total > 0,
                outcome=outcome,
            )
            append_route_usage_window(self.telemetry_path, window)
            self._reset_window()

    def stop(self) -> None:
        with self._lock:
            if not self._active:
                return
            try:
                self.flush()
            finally:
                uml_engine.remove_evaluation_observer(
                    experiment_id=self.experiment_id
                )
                self._active = False

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active": self._active,
                "experiment_id": self.experiment_id,
                "source": self.source,
                "telemetry_path": str(self.telemetry_path).replace("\\", "/"),
                "window_total_requests": self._total,
                "window_candidate_checks": self._candidate_checks,
                "window_errors": self._errors,
                "window_federation_counts": dict(self._counts),
                "window_am_domain_nonmacro": self._am_domain_nonmacro,
            }


class UAMShadowSession(AbstractContextManager[UAMShadowObserver]):
    """Context manager that guarantees tail-window flush and observer removal."""

    def __init__(self, observer: UAMShadowObserver) -> None:
        self.observer = observer

    def __enter__(self) -> UAMShadowObserver:
        return self.observer.start()

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.observer.stop()
        return False


def shadow_session(
    *,
    experiment_id: str,
    source: str,
    telemetry_path: str | Path = DEFAULT_TELEMETRY,
    dll_path: str | Path = DEFAULT_DLL,
    flush_every: int = 10_000,
) -> UAMShadowSession:
    """Create an explicit shadow session; construction alone does not install it."""
    return UAMShadowSession(
        UAMShadowObserver(
            experiment_id=experiment_id,
            source=source,
            telemetry_path=telemetry_path,
            dll_path=dll_path,
            flush_every=flush_every,
        )
    )


__all__ = [
    "UAMShadowObserver",
    "UAMShadowSession",
    "shadow_session",
]
