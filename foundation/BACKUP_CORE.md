# Viv AIOS Backup Core

## Current state

Viv now owns a content-addressed backup vault at:

`L:\Continue\Viv\foundation\artifacts\auto\backup_core\vault`

The active security module is Viv-local:

`L:\Continue\Viv\security_core\runtime\security_core.pyd`

The shared `.venv` 0.2.5 module was not overwritten. Viv's Python bridge loads
the local 0.2.7 module only after its SHA-256 sidecar passes.

## Architecture

- SHA-256 objects are stored once and shared by immutable, parent-linked
  snapshot manifests.
- Changeable sovereign assets are copied. Large immutable GGUF/HF bases are
  catalogued by hash instead of duplicated.
- Rust authorizes `SNAPSHOT`, `VERIFY`, `RESTORE_STAGE`, `RESTORE_COMMIT`,
  `PRUNE`, and `REPLICATE`.
- Replication remains compiled closed until an external target is configured.
- Restore first reconstructs into `sandbox\restore_staging`. A live restore
  needs the exact Architect approval phrase bound to the restore-plan hash.
- A live restore creates a safety snapshot and reverses only its own changed
  files if post-write verification fails.
- Backup-ledger writes use an exclusive lock and a SHA-256 hash chain.
- Snapshot creation refuses to reduce L: below the 12 GiB reserve.

## Training integration

A verified pre-mutation snapshot is required before:

- Stage 1 frozen-registry creation;
- training run leases;
- validated-candidate pointer writes.

The backup gate does not authorize deployment. `DEPLOY` remains compiled
closed, `validated_candidate` remains null, and Qwen remains the live mouth.

## Evidence

- Milestone: `artifacts/auto/backup_core/milestone_report_v1.json`
- Human summary: `artifacts/auto/backup_core/MILESTONE.md`
- Bootstrap restore proof:
  `artifacts/auto/backup_core/bootstrap_restore_verification.json`
- Backup security ledger: `artifacts/audit/security_backup_events.jsonl`

Bootstrap snapshot:
`903c052b6b4f386913a79aabaf9e5b4dee51e701768c9de8bedb5ac16ff7b6d4`

## Operator commands

```powershell
cd L:\Continue\Viv\foundation
L:\Continue\.venv\Scripts\python.exe scripts\test_backup_core_contracts.py
L:\Continue\.venv\Scripts\python.exe -c "from lib.aios_adapter_backup import run_smoke; print(run_smoke())"
```

### Local backup automation (safe, non-destructive)

One-command governed snapshot through the existing vault executor. Default
profile copies sovereign code/config/docs/audit plus the UML evidence lane and
**denies** `models/gpu`, weight suffixes (`.pt`/`.pth`/`.gguf`/`.safetensors`),
and `test_training/runs`. Receipts land under
`artifacts/auto/backup_core/receipts/<stamp>/`.

```powershell
cd L:\Continue\Viv\foundation
# Plan only (no vault write):
L:\Continue\.venv\Scripts\python.exe scripts\run_backup_core_automation_v1.py --plan-only --profile uml_lane
# Execute bounded UML+backup-core lane:
L:\Continue\.venv\Scripts\python.exe scripts\run_backup_core_automation_v1.py --profile uml_lane
# Execute safe sovereign+UML set (still denies weight packs):
L:\Continue\.venv\Scripts\python.exe scripts\run_backup_core_automation_v1.py --profile safe
# Optional operator gate: hash-catalog GGUF/HF bases (still no weight copy):
L:\Continue\.venv\Scripts\python.exe scripts\run_backup_core_automation_v1.py --profile safe --catalog-models
```

Selftests:

```powershell
L:\Continue\.venv\Scripts\python.exe scripts\test_cpu_backup_planner_v1.py
L:\Continue\.venv\Scripts\python.exe scripts\test_backup_adapter_cpu_plan_v1.py
L:\Continue\.venv\Scripts\python.exe scripts\test_backup_core_automation_v1.py
L:\Continue\.venv\Scripts\python.exe scripts\test_backup_core_contracts.py
```

No schedule hook is installed yet. Cadence, off-L: destination, and retention
deletion remain operator decisions (`REPLICATE` is compiled closed; retention
planner only lists candidates).

Build without installation:

```powershell
L:\Continue\Viv\security_core\scripts\build.ps1
```

The explicit `-Install` path requires a verified snapshot containing the
currently active module. Installation is staged, hash-checked, smoked in a new
Python process, and rolled back on failure.

## Honest limitation

The vault is inside Viv and on the same L: volume. It protects against bad
edits, failed module swaps, and bounded software corruption; it is not yet
protection against physical L: failure. The attempted external
`L:\Continue\Viv_Backup` creation was rejected by the desktop approval service.
`rclone` is not installed, so off-disk replication remains future work.

