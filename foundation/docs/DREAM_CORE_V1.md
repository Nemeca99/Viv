# Dream core v1 — deterministic idle planning boundary

## Source triangulation

The AIOS manual describes Dream as an idle/sleep cycle with a 600-second
heartbeat check, idle and manual triggers, STM-to-LTM consolidation, pattern
review, index maintenance, and append-only historical preservation. The
legacy `F:/AIOS_Clean/dream_core` and `D:/LocalAi/AIOS_V1/dream_core` sources
also contain background loops, random meditation, direct memory mutation,
token-bypass middleware, and model calls. Those effects are not imported into
this slice.

## Implemented CPU boundary

`foundation/lib/dream_core.py` provides:

- deterministic trigger planning for manual, idle, interval, fragment, and
  heartbeat conditions;
- four documented phase plans: light scan, deep consolidation, REM pattern
  review, and awakening/index review;
- bounded exact-duplicate and lexical-overlap candidate detection from caller-
  supplied records;
- an append-only archive plan that never deletes or overwrites source records;
- source counts and exact-dedup projections explicitly marked as projections,
  not measured improvements.

`foundation/lib/aios_adapter_dream.py` exposes the planner through
`cycle_plan()` and `consolidation_plan()` while retaining the existing
artifact-read adapter. The live `lib/aios_dream.py` writer remains a separately
governed operational path and is not called by these tests.

## Boundaries

The CPU planner does not start a background loop, perform durable memory
commits, generate semantic summaries, invoke an LLM, delete archive material,
or claim that retrieval/storage improved. A planned phase is not a completed
phase. Any commit must receive a separate explicit authorization and produce
its own backup and evidence.

## Primary and secondary use

Primary use is to decide whether an idle consolidation task is eligible and
what bounded work an executor may later request. Secondary use is replayable
maintenance evidence: the same supplied trigger state and record set produce
the same plan, candidate IDs, archive policy, and projected counts.

## Verification

```text
foundation/scripts/test_dream_core_v1.py
foundation/scripts/test_cpu_dream_planner_v1.py
foundation/scripts/test_core_contracts_v1.py
foundation/scripts/test_cpu_core_dispatch_v1.py
```

The focused regression covers due/not-due/hold decisions, hot/cold phase
selection, duplicate candidate detection, explicit archive-commit gating, and
the no-write/no-execution/no-LLM closure.
