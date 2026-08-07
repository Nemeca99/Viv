# `utils_core` v1 CPU boundary

## Purpose

`utils_core` is the AIOS plumbing layer for validation, resilience, timestamp
freshness, bounded path policy, message integrity, and bridge planning. The
manual describes a larger legacy module that also writes files, starts
PowerShell/Rust subprocesses, maintains mutable caches, and appends monitoring
logs. Those effects are not part of this first Viv CPU slice.

## Implemented boundary

`foundation/lib/utils_core.py` provides deterministic functions that operate
only on caller-supplied values:

- `validate_input` checks JSON/text/record/path values and returns a digest;
- `plan_retry` calculates bounded delays without sleeping or retrying;
- `timestamp_age` compares two explicit timezone-aware timestamps without
  consulting the system clock;
- `classify_path` and `plan_file_operation` enforce a declared root and reject
  traversal/effectful operations without resolving the filesystem;
- `make_message_envelope` and `validate_message_envelope` provide a
  content-addressed inter-core message contract;
- `plan_bridge_call` describes Rust/PowerShell work but never executes it;
- `module_status` records the closed authority surface.

`foundation/lib/aios_adapter_utils.py::cpu_plan` composes those functions. Its
legacy adapter status and smoke path remain separate read-mirror/inventory
behavior and are not treated as CPU authority.

## Explicit non-goals

This boundary does not read or write files, resolve path existence, sleep,
launch workers, invoke subprocesses, probe the network, mutate caches or logs,
call Rust/PowerShell, or grant an LLM authority. Runtime effects require a
separate governed layer with its own lease, audit, and rollback evidence.

## Verification

Run from `L:\Continue\Viv`:

```powershell
& 'L:\Continue\.venv\Scripts\python.exe' 'foundation\scripts\test_utils_core_v1.py'
& 'L:\Continue\.venv\Scripts\python.exe' 'foundation\scripts\test_utils_adapter_cpu_plan_v1.py'
```

The full foundation preflight remains the release gate. No training,
promotion, deployment, or live model mutation is implied by this slice.
