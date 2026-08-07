# U_AM Shadow Experiment

## Purpose

Collect real workload frequency and parity evidence without serving from or
promoting `U_AM`.

The dynamic `uml_engine.evaluate` result remains authoritative. The isolated
Rust macro executes only in shadow. Any mismatch fails the named experiment.

## Safety contract

- Default: off; importing the modules does not install an observer.
- One observer only; competing writers raise and halt the experiment.
- Production requires an explicit experiment ID and `source="production"`.
- Telemetry is aggregated into bounded windows; there is no per-request log.
- Only healthy production windows count: PASS, heartbeat progressed, zero
  errors, zero stalls.
- Test/sandbox windows are rejected by the promotion gate.
- Rollback: leave/close the context or call `observer.stop()`.
- Shadow never returns, selects, caches, or installs the candidate result.

## Integration

In the operator-selected production runner (the same process that calls
`uml_engine.evaluate`), construct `UAMShadowObserver` with:

- `experiment_id="u_am_prod_shadow_v1"`
- `source="production"`
- `telemetry_path="runs/uml_route_usage.jsonl"`
- `flush_every=10_000`

Call `start()` immediately before its existing workload loop and `stop()` in
that runner's existing `finally`/shutdown path. No workload is supplied by the
observer; it must not synthesize traffic or relabel tests as production.

Each JSONL row follows `uml_route_usage_v1` and records total requests,
federation counts, duration, errors, stalls, heartbeat state, actor, and
experiment ID.

## Replay

```powershell
L:\Continue\.venv\Scripts\python.exe -B test_uml_u_am_shadow.py
L:\Continue\.venv\Scripts\python.exe -B run_uml_am_candidate_gate.py
```

Current isolated lifecycle threshold at the first measured crossover:

- dynamic break-even: 20,073,951 `U_AM` requests
- mono/LIT break-even: 139,511,395 `U_AM` requests
- binding threshold: 139,511,395 healthy production requests

Crossing the threshold does not itself promote. Explicit authority is still
required, and `.pt` runtime equivalence is not claimed.
