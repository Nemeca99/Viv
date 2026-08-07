# CARMA core v1 — provenance and memory-planning boundary

## Source triangulation

The AIOS manual defines CARMA as the semantic memory layer: it stores
conversation fragments, extracts concepts, links related records, retrieves
relevant context, and coordinates STM→LTM consolidation. The sources in
`F:/AIOS_Clean/carma_core` and the surveyed V2 CARMA implementation also
contain embedding grids, clustering, compression, decay, persistence, and
deletion. Those behaviors are not automatically authoritative merely because
they produce a score or summary.

Viv already had a gated plain-text memory writer in `memory_core` and a small
lexical fragment planner in `foundation/lib/carma_core.py`. This revision
closes the CPU contract around those pieces.

## Implemented CPU boundary

`foundation/lib/carma_core.py` now provides:

- fragment identity, content-hash, provenance, and deterministic concept
  validation;
- a source-bearing lexical retrieval packet with deterministic ranking and
  explicit `semantic_authority=false`;
- STM→LTM threshold planning with `NOT_DUE`, `HOLD`, and
  `READY_FOR_GOVERNED_EXECUTOR` states, without performing a durable commit;
- overlap-link and consolidation-package planning that marks semantic
  compression as not performed.

`foundation/lib/aios_adapter_carma.py` exposes `cpu_plan()` for this
read-only path. The existing `remember()`/`recall()` methods remain the
separately governed live memory path; the CPU planner does not call them.

## Boundaries

CARMA does not invent facts, treat lexical overlap as semantic truth, silently
write LTM, delete duplicates, or grant an LLM memory authority. A retrieval
hit is a source fragment with provenance, not an independently verified fact.
Any durable consolidation must be executed by a separately authorized memory
executor with its own backup and receipt.

## Primary and secondary use

Primary use is CPU-owned memory admission/retrieval/consolidation planning.
Secondary use is replayable integrity evidence: the same fragment set produces
the same hashes, concepts, ranks, links, and threshold disposition.

## Automation handoff

`foundation/scripts/run_carma_automation_v1.py --plan-only` (and
`run_cognitive_cores_automation_v1.py --profile carma|both --plan-only`) call
`cpu_plan` on fixtures and write receipts under
`foundation/artifacts/auto/cognitive_cores_automation/`. Plan-only never calls
live `remember()`/`recall()`. Execute is refused; durable consolidation needs a
separately authorized memory executor.

## Verification

```text
foundation/scripts/test_carma_core_v1.py
foundation/scripts/test_carma_retrieval_ranker_v1.py
foundation/scripts/test_carma_adapter_cpu_plan_v1.py
foundation/scripts/test_cognitive_cores_automation_v1.py
foundation/scripts/test_core_contracts_v1.py
foundation/scripts/test_cpu_core_dispatch_v1.py
```
