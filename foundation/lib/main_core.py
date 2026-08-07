"""Deterministic CPU planning primitives for the AIOS ``main_core``.

The historical main core discovers modules, imports them, routes commands,
starts services, and performs shutdown work.  Those effects belong to a
separately governed runtime.  This module ports the inspectable planning
boundary only: catalog discovery from file metadata, route selection,
health aggregation, and lifecycle step planning.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


MANUAL_SOURCE = "F:/AIOS_Clean/AIOS_MANUAL.md"
MANUAL_SECTION = "3.17 main_core"
DEFAULT_CORE_SUFFIX = "_core"
DEFAULT_EXCLUDED = frozenset({"archive_core", "test_core", "__pycache__"})


def _posix(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _as_tokens(args: Sequence[str] | str | None) -> list[str]:
    if args is None:
        return []
    if isinstance(args, str):
        return [part for part in args.split() if part]
    return [str(part) for part in args if str(part).strip()]


def _handler_declared(paths: Iterable[Path]) -> bool:
    for path in paths:
        try:
            if "def handle_command" in path.read_text(encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    return False


def discover_core_catalog(
    root: Path | str,
    *,
    suffix: str = DEFAULT_CORE_SUFFIX,
    excluded: Iterable[str] = DEFAULT_EXCLUDED,
) -> dict[str, Any]:
    """Inspect immediate core directories without importing or executing them."""
    base = Path(root)
    if not base.is_dir():
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "core_root_missing",
            "root": _posix(base),
            "cores": [],
            "writes_performed": False,
            "llm_authority": False,
        }

    excluded_names = {str(item).casefold() for item in excluded}
    rows: list[dict[str, Any]] = []
    try:
        children = sorted((item for item in base.iterdir() if item.is_dir()), key=lambda item: item.name.casefold())
    except OSError as exc:
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "core_root_unreadable",
            "error": str(exc),
            "root": _posix(base),
            "cores": [],
            "writes_performed": False,
            "llm_authority": False,
        }

    for child in children:
        core_id = child.name
        if not core_id.casefold().endswith(str(suffix).casefold()):
            continue
        if core_id.casefold() in excluded_names:
            continue
        init_path = child / "__init__.py"
        implementation_candidates = (
            child / f"{core_id}.py",
            child / "main.py",
            child / "core.py",
        )
        implementation = next((path for path in implementation_candidates if path.is_file()), None)
        handler_declared = _handler_declared(
            path for path in (init_path, implementation) if path is not None and path.is_file()
        )
        if not init_path.is_file():
            state = "INCOMPLETE_MISSING_INIT"
        elif implementation is None:
            state = "DISCOVERED_NO_IMPLEMENTATION"
        elif not handler_declared:
            state = "DISCOVERED_NO_HANDLER_DECLARATION"
        else:
            state = "DISCOVERED"
        rows.append(
            {
                "core_id": core_id,
                "root_relative": core_id,
                "has_init": init_path.is_file(),
                "implementation": implementation.name if implementation is not None else None,
                "handle_command_declared": handler_declared,
                "state": state,
            }
        )

    return {
        "ok": True,
        "state": "VERIFIED",
        "root": _posix(base),
        "suffix": str(suffix),
        "excluded": sorted(excluded_names),
        "cores": rows,
        "counts": {
            "discovered": sum(row["state"] == "DISCOVERED" for row in rows),
            "incomplete": sum(row["state"] != "DISCOVERED" for row in rows),
            "total": len(rows),
        },
        "imports_performed": False,
        "execution_performed": False,
        "writes_performed": False,
        "llm_authority": False,
    }


def plan_route(
    args: Sequence[str] | str | None,
    catalog: Mapping[str, Any],
    *,
    priority_cores: Sequence[str] = (),
    fallback_core: str = "support_core",
) -> dict[str, Any]:
    """Choose a deterministic route candidate without invoking a handler."""
    if not isinstance(catalog, Mapping) or catalog.get("state") != "VERIFIED":
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "catalog_not_verified",
            "handler_invoked": False,
            "execution_performed": False,
            "llm_authority": False,
        }
    rows = [row for row in (catalog.get("cores") or []) if isinstance(row, Mapping)]
    by_id = {str(row.get("core_id")): row for row in rows if str(row.get("core_id") or "").strip()}
    tokens = {token.casefold().lstrip("-") for token in _as_tokens(args)}
    explicit: list[str] = []
    for core_id in by_id:
        alias = core_id.removesuffix("_core")
        if core_id.casefold() in tokens or alias.casefold() in tokens:
            explicit.append(core_id)
    if len(explicit) > 1:
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "multiple_explicit_core_targets",
            "targets": sorted(explicit),
            "handler_invoked": False,
            "execution_performed": False,
            "llm_authority": False,
        }
    if explicit:
        candidates = explicit
        reason = "explicit_core_target"
    else:
        ordered = []
        for core_id in priority_cores:
            if str(core_id) in by_id and str(core_id) not in ordered:
                ordered.append(str(core_id))
        for core_id in sorted(by_id, key=str.casefold):
            if core_id not in ordered:
                ordered.append(core_id)
        if fallback_core in by_id and fallback_core not in ordered:
            ordered.append(fallback_core)
        candidates = ordered
        reason = "priority_then_discovery_order"
    selected = candidates[0] if candidates else None
    return {
        "ok": selected is not None,
        "state": "PLANNED" if selected is not None else "ABSTAIN",
        "reason": reason if selected is not None else "no_route_candidate",
        "args": _as_tokens(args),
        "candidates": candidates,
        "selected_core": selected,
        "handler_invoked": False,
        "execution_performed": False,
        "writes_performed": False,
        "llm_authority": False,
    }


def health_snapshot(
    statuses: Mapping[str, Any],
    *,
    minimum_required: Sequence[str] = (),
) -> dict[str, Any]:
    """Aggregate supplied component statuses without running health checks."""
    if not isinstance(statuses, Mapping) or not statuses:
        return {
            "ok": False,
            "state": "UNKNOWN",
            "reason": "no_statuses_supplied",
            "components": {},
            "checks_performed": False,
            "writes_performed": False,
            "llm_authority": False,
        }
    components: dict[str, bool] = {}
    for name, value in statuses.items():
        if isinstance(value, Mapping):
            components[str(name)] = bool(value.get("ok") is True or str(value.get("state", "")).upper() in {"HEALTHY", "PASS", "OK"})
        else:
            components[str(name)] = bool(value)
    failed = sorted(name for name, ok in components.items() if not ok)
    missing_required = sorted(str(name) for name in minimum_required if str(name) not in components)
    required_failed = sorted(name for name in minimum_required if name in components and not components[name])
    if missing_required or required_failed:
        state = "UNHEALTHY"
    elif failed:
        state = "DEGRADED"
    else:
        state = "HEALTHY"
    return {
        "ok": state == "HEALTHY",
        "state": state,
        "components": components,
        "failed": failed,
        "missing_required": missing_required,
        "required_failed": required_failed,
        "automatic_recovery": False,
        "checks_performed": False,
        "writes_performed": False,
        "llm_authority": False,
    }


def lifecycle_plan(
    event: str,
    *,
    save_state_on_shutdown: bool = True,
    graceful_shutdown_timeout_s: float = 10.0,
) -> dict[str, Any]:
    """Return the manual lifecycle sequence without performing it."""
    name = str(event or "").strip().casefold()
    try:
        timeout = max(0.0, float(graceful_shutdown_timeout_s))
    except (TypeError, ValueError):
        return {"ok": False, "state": "ABSTAIN", "reason": "invalid_shutdown_timeout"}
    sequences = {
        "boot": ["parse_arguments", "load_configuration", "discover_cores", "initialize_essential_cores", "health_check", "route_or_ready"],
        "startup": ["parse_arguments", "load_configuration", "discover_cores", "initialize_essential_cores", "health_check", "route_or_ready"],
        "shutdown": ["receive_shutdown_signal", "save_state" if save_state_on_shutdown else "skip_state_save", "close_connections", "stop_background_tasks", "cleanup_temp", "exit_gracefully"],
        "restart": ["shutdown_sequence", "startup_sequence"],
    }
    steps = sequences.get(name)
    if steps is None:
        return {
            "ok": False,
            "state": "ABSTAIN",
            "reason": "unsupported_lifecycle_event",
            "event": name,
            "writes_performed": False,
            "llm_authority": False,
        }
    return {
        "ok": True,
        "state": "PLANNED",
        "event": name,
        "steps": steps,
        "graceful_shutdown_timeout_s": timeout,
        "execution_performed": False,
        "writes_performed": False,
        "llm_authority": False,
    }


def module_status() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "main_core",
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
        "implemented": [
            "read_only_core_catalog_discovery",
            "deterministic_route_planning",
            "supplied_status_health_aggregation",
            "lifecycle_sequence_planning",
        ],
        "not_implemented": [
            "core_import_and_execution",
            "automatic_recovery",
            "background_service_loops",
            "durable_shutdown_state_writes",
        ],
        "llm_authority": False,
    }

