# data_core v1 — deterministic CPU boundary

## Source comparison

The primary source is section 3.4 of `F:/AIOS_Clean/AIOS_MANUAL.md`, with
the implementation surveyed under `F:/AIOS_Clean/data_core`. The historical
implementation combines storage initialization, import/export, cleanup,
statistics, database maintenance, and optional Rust execution. Those effects
are not copied into the first Viv boundary.

## Implemented

`foundation/lib/data_core.py` provides deterministic, write-free planning for:

- content-addressed records with schema, source, provenance, timestamp, and SHA-256;
- stable manifests and rejection of invalid records;
- statistics derived only from supplied records;
- import and export plans that require an explicit governed commit;
- retention cleanup candidates with backup-before-cleanup and no deletion;
- recovery comparison that reports missing, unexpected, or changed records.

`foundation/lib/aios_adapter_data.py` exposes `status()`, `cpu_plan()`, and a
fixed-fixture `run_smoke()` without creating evidence files or changing live
state. The CPU dispatcher and system/IDE maps identify the adapter as the
data_core surface.

## Deliberately out of scope

- creating storage directories or database files;
- importing or exporting files;
- deleting or overwriting records;
- SQLite vacuum/reindex/check execution;
- committing backup restore plans;
- LLM, embedding, or Rust authority.

Every returned plan reports `writes_performed: false` and
`execution_performed: false`. A drift result is an observation requiring a
separate governed backup executor, not an automatic repair.

## Verification

Focused tests:

- `foundation/scripts/test_data_core_v1.py`
- `foundation/scripts/test_data_adapter_cpu_plan_v1.py`

The slice is not considered integrated until the CPU dispatcher, architecture
boundary review, and full foundation preflight pass.
