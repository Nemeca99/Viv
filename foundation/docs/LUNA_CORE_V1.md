# Luna core v1 — CPU communication boundary

Status: verified read-only planner and adapter boundary. The language model
and voice backend remain surface renderers only.

## Source triangulation

The Luna source trees in `F:/AIOS_Clean/luna_core` and
`D:/LocalAi/AIOS_V1/luna_core` contain overlapping systems for trait
classification, linguistic operators, response-value tiers, token budgeting,
personality blending, existential budgeting, and response assessment. The
historical tree also performs persistent state writes, random personality
changes, model/API calls, and learning updates. Those stateful behaviors were
not copied into the CPU boundary.

The current Viv implementation keeps the useful deterministic subset in
`foundation/lib/luna_core.py`:

- trait classification with stable keyword scoring;
- linguistic operator selection (`why`, `how`, `what`, `where`, `when`, and
  `who`);
- bounded response-value tiers and token budgets;
- deterministic soul-fragment routing through `consciousness_core`;
- telemetry containment assessment; and
- a grounded/unverified distinction that tells downstream reasoning when it
  must abstain.

## Adapter boundary

`foundation/lib/aios_adapter_luna.py:communication_plan()` now exposes that
planner through the registered Luna adapter. It accepts a prompt and a
retrieval-gate grounding result, returns structured CPU evidence, and does not
call the renderer, read live telemetry, write durable state, or execute the
historical Luna V2 tree. The adapter's existing `render_line()` remains a
fact-locked status line, not a general chatbot path.

The plan is useful twice:

1. Primary: route a request to the correct CPU fragment, operator, response
   budget, and grounding policy before any wording is generated.
2. Secondary: provide a deterministic replay/integrity record for testing
   whether different renderers received the same CPU-owned plan.

## Deliberate non-goals

This does not prove understanding, consciousness, general conversation, or
truth of a rendered answer. It does not import the historical existential
economy, karma/age transitions, random soul metrics, persistent learning, or
LLM/API authority. Those require separate contracts, immutable accounting
inputs, and explicit state-write authorization.

## Verification

```text
foundation/scripts/test_luna_core_v1.py
foundation/scripts/test_luna_adapter_communication_v1.py
foundation/scripts/test_cpu_core_dispatch_v1.py
foundation/scripts/test_cpu_reasoning_pipeline_v1.py
```

The adapter regression covers grounded and ungrounded plans, deterministic
`why`/guardian routing, empty-input abstention, renderer non-invocation, and
write/authority closures.
