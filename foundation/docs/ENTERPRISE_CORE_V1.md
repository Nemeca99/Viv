# `enterprise_core` v1 CPU boundary

## Purpose

The manual defines `enterprise_core` as the standards, configuration,
compliance, and audit-quality layer. The F-tree implementation also contains
tenant administration, API-key and encryption operations, background audit
workers, mutable audit files, and external integrations. `D:\LocalAi\AIOS_V1`
has no `enterprise_core` source tree in the current comparison.

## Implemented boundary

`foundation/lib/enterprise_core.py` evaluates only evidence supplied by the
caller:

- `evaluate_python_source` parses supplied Python text and checks syntax,
  headers/docstrings, annotations, exception handling, and logging evidence;
- `evaluate_json_config` validates supplied JSON text/mappings and required
  keys without opening a path;
- `summarize_observations` aggregates explicit standards observations without
  scanning a directory;
- `evaluate_compliance` classifies explicit controls as compliant, partial,
  non-compliant, or abstain when evidence is missing;
- `make_audit_event` creates a content-addressed event candidate without
  appending it;
- `plan_report` builds a quality/security/compliance report plan without
  writing the report.

`foundation/lib/aios_adapter_audit.py::cpu_plan` composes these functions.
The adapter's existing `status`, `tail`, and `search` operations remain a
separate read-only view of Viv audit artifacts; they do not grant the CPU
planner a write path.

## Explicit non-goals

This boundary does not scan the filesystem, write audit/report files, start a
monitor, manage tenants or keys, perform encryption or external integration,
call the F-tree/D-tree implementations, or grant an LLM authority. Those
effects require separately governed runtime surfaces with backup, lease,
audit, and rollback evidence.

## Verification

Run from `L:\Continue\Viv`:

```powershell
& 'L:\Continue\.venv\Scripts\python.exe' 'foundation\scripts\test_enterprise_core_v1.py'
& 'L:\Continue\.venv\Scripts\python.exe' 'foundation\scripts\test_enterprise_adapter_cpu_plan_v1.py'
```

The full foundation preflight remains the release gate. No training,
promotion, deployment, audit append, or live policy mutation is implied by
this slice.
