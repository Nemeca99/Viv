# Fractal Core v1

This CPU slice ports the policy-oriented part of the legacy fractal design
described in manual section 3.11. It provides deterministic multi-head query
classification, policy proposals, bounded knapsack span allocation, threshold
proposals, and cache-receipt summaries.

The slice is deliberately effect-closed. It does not read or write a cache,
learn telemetry, execute a task, call a model, alter thresholds, or persist
state. The existing `cpu_fractal_reasoner.py` remains the bounded recursive
decomposition surface used by the reasoning pipeline; this module adds the
policy and allocation boundary beside it.

Acceptance evidence is recorded in `CURRENT_TASK.json` and
`session_journal.md`. A green test or preflight result proves only the tested
boundary, not general intelligence or production autonomy.
