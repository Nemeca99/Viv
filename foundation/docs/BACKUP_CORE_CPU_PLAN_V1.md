# `backup_core` CPU intent planner v1

## Existing governed executor

`foundation/lib/backup_core.py` already provides the effectful backup vault:
content-addressed objects, immutable parent-linked manifests, Rust/security
authorization, staged restore, pre-restore safety snapshots, and transactional
rollback. Its existing contract tests exercise those gates. That executor is
kept intact.

## New CPU boundary

`foundation/lib/cpu_backup_planner.py` is a separate effect-closed planning
surface. It accepts only caller-supplied intent or manifest evidence and can:

- validate snapshot source/catalog path intent without scanning or hashing files;
- build and verify a deterministic manifest from supplied file metadata;
- plan staged restore targets and require Architect approval without writing;
- identify retention candidates without deleting or rotating anything.

`foundation/lib/aios_adapter_backup.py::cpu_plan` composes the planner. The
existing `create`, `verify`, and `plan_restore` adapter methods continue to
route to the governed executor and are not called by the CPU planner tests.

## Invariants

The planner never reads the filesystem, writes the vault or staging area,
requests security authorization, commits a restore, deletes a candidate, or
grants an LLM authority. A `READY_FOR_GOVERNED_EXECUTOR` result is an intent
handoff, not permission to execute.

## Verification

```powershell
& 'L:\Continue\.venv\Scripts\python.exe' 'foundation\scripts\test_cpu_backup_planner_v1.py'
& 'L:\Continue\.venv\Scripts\python.exe' 'foundation\scripts\test_backup_adapter_cpu_plan_v1.py'
& 'L:\Continue\.venv\Scripts\python.exe' 'foundation\scripts\test_backup_core_automation_v1.py'
& 'L:\Continue\.venv\Scripts\python.exe' 'foundation\scripts\test_backup_core_contracts.py'
```

## Automation handoff

`foundation/scripts/run_backup_core_automation_v1.py` is the operator entrypoint.
It calls `cpu_plan`/`plan_automation` first, then the governed
`create_snapshot` executor with `deny_weight_packs=True`. Profiles:

- `uml_lane` — thesis + evidence snapshots + backup-core modules (bounded)
- `safe` — sovereign code/config/docs/audit + UML evidence
- `legacy_default` — historical default roots + UML evidence (still denies weights)

The full foundation preflight remains the release gate. Plan-only mode does not
write vault objects; execute mode does not start AIOS or commit restores.
