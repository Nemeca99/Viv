# support_core v1 — deterministic CPU diagnostics boundary

## Source comparison

The primary source is section 3.5 of `F:/AIOS_Clean/AIOS_MANUAL.md`, with
legacy implementations surveyed under `F:/AIOS_Clean/support_core` and
`D:/LocalAi/AIOS_V1/support_core`. They combine health polling, cache and
embedding operations, recovery, logging, PII handling, and mutable backup
behavior. The active Viv adapter already mirrors foundation health and the
legacy tree read-only; the new CPU module adds deterministic evaluation of
supplied evidence without importing or executing legacy support code.

## Implemented

`foundation/lib/support_core.py` provides:

- supplied health-check aggregation into `HEALTHY`, `DEGRADED`, `CRITICAL`, or `ABSTAIN`;
- content-addressed cache-entry validation and statistics;
- deterministic email and phone redaction on a derived text copy;
- a diagnostic packet combining health, cache, and optional redaction evidence.

`foundation/lib/aios_adapter_support.py` exposes `cpu_plan()` for this
write-free boundary and includes the CPU planner in status evidence.

## Deliberately out of scope

- background health threads or live network/database probes;
- durable log writes;
- cache mutation, embedding generation, or cache recovery;
- backup creation or restore commits;
- model or LLM authority.

All CPU plans report `live_probe_performed: false`, `writes_performed: false`,
and `llm_authority: false`.

## Verification

- `foundation/scripts/test_support_core_v1.py`
- `foundation/scripts/test_support_adapter_cpu_plan_v1.py`

The slice requires dispatcher, boundary-registry, and full-foundation
preflight verification before being recorded as complete.
