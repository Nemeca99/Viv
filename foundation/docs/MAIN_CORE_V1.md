# Main core v1 — deterministic kernel planning boundary

Status: verified read-only planning slice. It does not replace the governed
runtime entrypoints yet.

## Source triangulation

The manual defines `main_core` as the AIOS orchestrator: discover cores, route
commands, manage startup/shutdown, monitor health, and degrade gracefully when
a core fails. The Windows sources in `F:/AIOS_Clean/main_core` and
`D:/LocalAi/AIOS_V1/main_core` implement those roles inside a large
stateful orchestrator that also imports subsystems, calls model/API paths,
writes state, and controls background services.

The safe first port is `foundation/lib/main_core.py`. It performs no imports of
discovered cores and no execution. It provides:

- metadata-only `_core` directory discovery with `__init__.py`, implementation,
  and `handle_command` declaration checks;
- deterministic explicit-target and priority-order route planning;
- supplied-status aggregation into `HEALTHY`, `DEGRADED`, `UNHEALTHY`, or
  `UNKNOWN` without running checks or automatic recovery; and
- boot, shutdown, and restart step plans without performing lifecycle work.

## Primary and secondary use

Primary use is a CPU-owned kernel plan before any handler, service, renderer,
or model is invoked. Secondary use is replayable integrity evidence: the same
catalog, arguments, status map, and lifecycle event must produce the same
selected route, health state, and step sequence.

## Deliberate non-goals

Core imports/execution, automatic recovery, background service loops, durable
shutdown writes, and LLM/API authority remain out of this slice. A `PLANNED`
route is not a completed action, and a `HEALTHY` aggregate means only that the
supplied statuses were healthy; it is not a live health check.

## Verification

```text
foundation/scripts/test_main_core_v1.py
foundation/scripts/test_core_contracts_v1.py
foundation/scripts/test_cpu_core_dispatch_v1.py
```

The focused regression covers deterministic discovery, explicit and priority
routing, conflicting-target abstention, healthy/degraded/unhealthy aggregation,
unknown lifecycle abstention, and execution/write/authority closures.
