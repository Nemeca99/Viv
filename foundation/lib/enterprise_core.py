"""Deterministic CPU standards and compliance evaluation for AIOS.

The historical enterprise source mixes standards checking with audit-file
mutation, background monitoring, tenant/API-key administration, encryption,
and integrations.  This Viv slice evaluates caller-supplied source/config/
control evidence only.  It can produce a bounded report plan, but it does not
scan files, write reports, create audit records, administer identities, or
grant an integration authority.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any


MODULE_ID = "enterprise_core"
VERSION = "v1"
MANUAL_SOURCE = "F:/AIOS_Clean/AIOS_MANUAL.md"
MANUAL_SECTION = "3.7 enterprise_core"
SOURCE_ROOT = "F:/AIOS_Clean/enterprise_core"
MAX_SOURCE_CHARS = 2_000_000
MAX_OBSERVATIONS = 2_000
MAX_CONTROLS = 512
_PATH_PATTERN = re.compile(r"^[A-Za-z0-9_./\\:-]{1,260}$")
_CONTROL_STATES = frozenset({"PASS", "WARN", "FAIL", "UNKNOWN"})


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _flags() -> dict[str, bool]:
    return {
        "filesystem_scan_performed": False,
        "filesystem_write_performed": False,
        "audit_write_performed": False,
        "background_worker_started": False,
        "external_integration_performed": False,
        "llm_authority": False,
    }


def _result(ok: bool, **fields: Any) -> dict[str, Any]:
    result = {"ok": bool(ok), **fields}
    result.update(_flags())
    return result


def _path_value(path: Any) -> tuple[str, list[str]]:
    text = str(path or "").strip().replace("\\", "/")
    errors: list[str] = []
    if not text:
        errors.append("path_is_empty")
    elif not _PATH_PATTERN.fullmatch(text):
        errors.append("path_contains_unsupported_character")
    if ".." in [part for part in text.split("/") if part]:
        errors.append("path_traversal_segment")
    return text, errors


def _function_nodes(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _has_type_hints(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    args = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
    if function.args.vararg is not None:
        args.append(function.args.vararg)
    if function.args.kwarg is not None:
        args.append(function.args.kwarg)
    return all(arg.annotation is not None for arg in args) and function.returns is not None


def _check_python_source(source: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {
            "state": "FAIL",
            "score": 0.0,
            "checks": [{"name": "syntax", "state": "FAIL", "detail": str(exc)}],
            "function_count": 0,
            "class_count": 0,
        }

    module_doc = ast.get_docstring(tree, clean=False)
    checks.append(
        {
            "name": "file_header",
            "state": "PASS" if module_doc else "FAIL",
            "detail": "module docstring present" if module_doc else "module docstring missing",
        }
    )

    functions = _function_nodes(tree)
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    documented = sum(1 for node in [*functions, *classes] if ast.get_docstring(node, clean=False))
    checks.append(
        {
            "name": "docstrings",
            "state": "PASS" if documented == len(functions) + len(classes) else "WARN",
            "detail": f"{documented}/{len(functions) + len(classes)} definitions documented",
        }
    )

    typed = sum(1 for function in functions if _has_type_hints(function))
    checks.append(
        {
            "name": "type_hints",
            "state": "PASS" if typed == len(functions) else "WARN",
            "detail": f"{typed}/{len(functions)} functions fully annotated",
        }
    )

    bare_handlers = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and node.type is None
    ]
    try_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.Try)]
    checks.append(
        {
            "name": "error_handling",
            "state": "FAIL" if bare_handlers else "PASS" if try_nodes else "UNKNOWN",
            "detail": (
                f"{len(bare_handlers)} bare exception handlers"
                if bare_handlers
                else f"{len(try_nodes)} typed try blocks"
                if try_nodes
                else "no try block supplied for evaluation"
            ),
        }
    )

    logging_imported = any(
        isinstance(node, ast.Import) and any(alias.name == "logging" for alias in node.names)
        or isinstance(node, ast.ImportFrom) and node.module == "logging"
        for node in ast.walk(tree)
    )
    logging_called = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"debug", "info", "warning", "error", "exception", "critical"}
        for node in ast.walk(tree)
    )
    checks.append(
        {
            "name": "logging",
            "state": "PASS" if logging_imported and logging_called else "UNKNOWN",
            "detail": "logging import and call observed" if logging_imported and logging_called else "logging evidence not supplied",
        }
    )

    states = [str(check["state"]) for check in checks]
    passed = sum(state == "PASS" for state in states)
    failed = sum(state == "FAIL" for state in states)
    state = "FAIL" if failed else "WARN" if any(state in {"WARN", "UNKNOWN"} for state in states) else "PASS"
    return {
        "state": state,
        "score": round(passed / len(checks) * 100.0, 4) if checks else 0.0,
        "checks": checks,
        "function_count": len(functions),
        "class_count": len(classes),
    }


def evaluate_python_source(source: Any, *, path: str = "supplied.py") -> dict[str, Any]:
    """Evaluate supplied Python source without reading the named path."""
    path_text, path_errors = _path_value(path)
    if not isinstance(source, str):
        return _result(False, operation="python_source", state="ABSTAIN", path=path_text, errors=["source_must_be_string", *path_errors])
    if len(source) > MAX_SOURCE_CHARS:
        return _result(False, operation="python_source", state="ABSTAIN", path=path_text, errors=["source_exceeds_max_length", *path_errors])
    evaluation = _check_python_source(source)
    return _result(
        not path_errors and evaluation["state"] != "FAIL",
        operation="python_source",
        state=evaluation["state"] if not path_errors else "ABSTAIN",
        path=path_text,
        source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        errors=path_errors,
        **{key: value for key, value in evaluation.items() if key != "state"},
    )


def evaluate_json_config(
    value: Any,
    *,
    path: str = "supplied.json",
    required_keys: Iterable[str] = (),
) -> dict[str, Any]:
    """Validate supplied JSON text or mapping without opening ``path``."""
    path_text, path_errors = _path_value(path)
    errors = list(path_errors)
    parsed: Any = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid_json:{exc.msg}")
    if not isinstance(parsed, (dict, list)):
        errors.append("config_must_be_object_or_array")
    missing: list[str] = []
    if isinstance(parsed, Mapping):
        missing = [str(key) for key in required_keys if str(key) not in parsed]
        errors.extend("missing_required_key:" + key for key in missing)
    else:
        missing = [str(key) for key in required_keys]
    return _result(
        not errors,
        operation="json_config",
        state="PASS" if not errors else "FAIL",
        path=path_text,
        config_sha256=None if errors else _digest(parsed),
        required_keys=[str(key) for key in required_keys],
        missing_keys=missing,
        errors=errors,
    )


def summarize_observations(observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate caller-supplied standards observations; never scan a tree."""
    valid: list[dict[str, Any]] = []
    rejected: list[str] = []
    for raw in list(observations)[:MAX_OBSERVATIONS]:
        if not isinstance(raw, Mapping):
            rejected.append("observation_not_mapping")
            continue
        path = str(raw.get("path") or "").strip()
        state = str(raw.get("state") or "UNKNOWN").strip().upper()
        if not path:
            rejected.append("observation_path_missing")
            continue
        if state not in _CONTROL_STATES:
            rejected.append("observation_state_invalid:" + state)
            continue
        try:
            score = float(raw.get("score", 0.0))
        except (TypeError, ValueError):
            rejected.append("observation_score_invalid:" + path)
            continue
        valid.append({"path": path, "state": state, "score": max(0.0, min(100.0, round(score, 4)))})
    counts = {state: sum(row["state"] == state for row in valid) for state in sorted(_CONTROL_STATES)}
    return _result(
        True,
        operation="standards_summary",
        state="EMPTY" if not valid and not rejected else "PARTIAL" if rejected else "VERIFIED",
        observation_count=len(valid),
        rejected_count=len(rejected),
        rejected=rejected,
        state_counts=counts,
        average_score=round(sum(row["score"] for row in valid) / len(valid), 4) if valid else None,
        observations=valid,
        filesystem_scan_performed=False,
    )


def evaluate_compliance(
    controls: Iterable[Mapping[str, Any]],
    *,
    standard: str = "soc2",
) -> dict[str, Any]:
    """Evaluate supplied compliance controls without asserting missing evidence."""
    rows: list[dict[str, Any]] = []
    rejected: list[str] = []
    for raw in list(controls)[:MAX_CONTROLS]:
        if not isinstance(raw, Mapping):
            rejected.append("control_not_mapping")
            continue
        control_id = str(raw.get("id") or raw.get("control_id") or "").strip()
        state = str(raw.get("state") or "UNKNOWN").strip().upper()
        if not control_id:
            rejected.append("control_id_missing")
            continue
        if state not in _CONTROL_STATES:
            rejected.append("control_state_invalid:" + control_id)
            continue
        rows.append(
            {
                "id": control_id,
                "state": state,
                "evidence": str(raw.get("evidence") or ""),
            }
        )
    counts = {state: sum(row["state"] == state for row in rows) for state in sorted(_CONTROL_STATES)}
    if not rows:
        disposition = "ABSTAIN"
    elif counts["FAIL"]:
        disposition = "NON_COMPLIANT"
    elif counts["WARN"] or counts["UNKNOWN"]:
        disposition = "PARTIAL"
    else:
        disposition = "COMPLIANT"
    return _result(
        bool(rows) and not rejected,
        operation="compliance_evaluation",
        standard=str(standard or "unknown").strip().casefold(),
        disposition=disposition,
        control_count=len(rows),
        rejected_count=len(rejected),
        rejected=rejected,
        state_counts=counts,
        pass_percent=round(counts["PASS"] / len(rows) * 100.0, 4) if rows else None,
        controls=rows,
    )


def make_audit_event(
    action: str,
    *,
    actor: str = "cpu",
    outcome: str = "observed",
    evidence: Any = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    """Build an immutable audit-event candidate without appending it."""
    action_text = str(action or "").strip()
    actor_text = str(actor or "").strip()
    outcome_text = str(outcome or "").strip()
    if not action_text or not actor_text or not outcome_text:
        raise ValueError("audit_event_identity_missing")
    payload: dict[str, Any] = {
        "schema_version": "enterprise.audit.v1",
        "actor": actor_text,
        "action": action_text,
        "outcome": outcome_text,
        "evidence": evidence,
    }
    if occurred_at is not None:
        payload["occurred_at"] = str(occurred_at).strip()
    digest = _digest(payload)
    return {
        "event_id": digest[:24],
        **payload,
        "sha256": digest,
        **_flags(),
        "append_performed": False,
    }


def plan_report(
    report_type: str,
    *,
    observations: Iterable[Mapping[str, Any]] = (),
    controls: Iterable[Mapping[str, Any]] = (),
    standard: str = "soc2",
) -> dict[str, Any]:
    """Prepare a quality/security/compliance report from supplied evidence."""
    kind = str(report_type or "").strip().casefold()
    if kind == "quality":
        body = summarize_observations(observations)
    elif kind in {"security", "compliance"}:
        body = evaluate_compliance(controls, standard=standard)
    else:
        return _result(False, operation="report_plan", state="ABSTAIN", report_type=kind, errors=["report_type_not_allowlisted"])
    return _result(
        bool(body.get("ok")),
        operation="report_plan",
        state=body.get("disposition") or body.get("state"),
        report_type=kind,
        standard=str(standard or "unknown").strip().casefold(),
        body=body,
        report_write_planned=True,
        report_write_performed=False,
    )


def module_status() -> dict[str, Any]:
    return {
        "ok": True,
        "module": MODULE_ID,
        "version": VERSION,
        "manual_source": MANUAL_SOURCE,
        "manual_section": MANUAL_SECTION,
        "implemented": [
            "supplied_python_standards_evaluation",
            "supplied_json_config_validation",
            "standards_observation_summary",
            "compliance_control_evaluation",
            "content_addressed_audit_event_planning",
            "quality_security_compliance_report_planning",
        ],
        "not_implemented": [
            "filesystem_tree_scan",
            "report_or_audit_file_write",
            "background_compliance_monitor",
            "tenant_or_identity_administration",
            "key_generation_or_rotation",
            "external_integration",
            "llm_authority",
        ],
        **_flags(),
    }


__all__ = [
    "evaluate_compliance",
    "evaluate_json_config",
    "evaluate_python_source",
    "make_audit_event",
    "module_status",
    "plan_report",
    "summarize_observations",
]
