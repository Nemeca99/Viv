# Consciousness Core v1 — bounded CPU slice

Status: implemented as a read-only, deterministic CPU slice; historical
biological loops and GPU/LLM authority remain out of scope.

## Purpose

The rebuilt slice gives Viv a small, testable CPU boundary for identity mode,
bounded short-term memory, explicit in-memory consolidation, deterministic
reflection, and a scheduled pulse. Its primary use is to provide structured
state for AIOS reasoning. Its secondary use is a regression and integrity
surface: the same inputs must produce the same fragment, graph metrics, and
commit decision without asking a language model to invent an inner state.

## Source triangulation

The implementation was compared against the source material in:

- `F:/AIOS_Clean/consciousness_core`
- `D:/LocalAi/AIOS_V1/consciousness_core`
- the surveyed `L:/Continue/FSAA/Luna/AIOS_V2/consciousness_core` location

The historical sources contain useful roles—soul fragments, STM/LTM,
brainstem routing, reflection, and pulse scheduling—but also contain LLM
thought generation, automatic loops, persistence, and stubs. Those behaviors
were not copied into the CPU foundation as authority.

## Implemented contract

- `select_soul_fragment(text)` selects one of seven identity fragments using
  deterministic keyword scoring and stable priority ties.
- `ShortTermMemory` is bounded at 100 records and refuses silent overflow.
- `consolidate_once()` prepares a lossless record package, returns `HOLD`
  until explicit memory-commit authorization, and only clears STM after a
  successful in-memory commit with matching record IDs.
- `ReflectionGraph` accepts finite typed nodes and three-part edges, rejects
  malformed values, and computes bounded compression and motive-coherence
  metrics.
- `ConsciousnessPulse` schedules reflection at a configurable frequency and
  reports `DISABLED_CPU_ONLY` for autonomous thought.
- `aios_adapter_consciousness.consciousness_cycle()` runs one isolated pulse,
  reflection, and commit-gate evaluation without durable writes.

All of these surfaces explicitly report `llm_authority: false` and
`writes_performed: false` for the isolated cycle.

## Deliberate non-goals

This slice does not prove consciousness, autonomy, semantic understanding, or
general intelligence. It does not execute the historical biological heartbeat,
does not generate private thoughts through an LLM, does not automatically
persist or semantically compress memory, and does not grant the mouth authority
over facts or actions. The Luna/AIOS_V2 source remains a read-only reference
until its communication and safety boundary is separately specified.

## Automation handoff

`aios_adapter_consciousness.cpu_plan()` wraps one isolated cycle with commit
hold and optional READY_FOR_GOVERNED_EXECUTOR handoff metadata (still no durable
write). Operator entrypoints:

```text
foundation/scripts/run_consciousness_automation_v1.py --plan-only
foundation/scripts/run_cognitive_cores_automation_v1.py --profile consciousness|both --plan-only
```

Receipts: `foundation/artifacts/auto/cognitive_cores_automation/`. Execute is
refused by the automation runner; V2 biological loops remain out of scope.

## Verification

Focused checks:

```text
foundation/scripts/test_consciousness_core_v1.py
foundation/scripts/test_consciousness_cycle_v1.py
foundation/scripts/test_consciousness_adapter_cpu_plan_v1.py
foundation/scripts/test_cognitive_cores_automation_v1.py
foundation/scripts/test_cpu_core_dispatch_v1.py
foundation/scripts/test_cpu_reasoning_pipeline_v1.py
```

The cycle regression covers deterministic graph metrics, malformed-input
rejection, reflection scheduling, the explicit commit hold, successful
in-memory commit, and adapter integration. Full foundation preflight remains
the final integration gate after this slice is recorded.
