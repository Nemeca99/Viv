# AIOS Triad Membrane and Engineering Governor

**Contract:** `viv_triad_contract_v1`  
**Authority:** Viv-local Rust `security_core` 0.2.9  
**Pillars:** RID/Vidi, AUTO/Vixi, UML/Intellexi

## Binding architecture

All governed AIOS Python packages bind to `lib.triad_kernel`. The kernel loads
the three pillar mains lazily, verifies their contract versions, and refuses a
request when Security or any pillar denies it.

```text
external or internal message
        |
        v
Rust Security IN
        |
        v
RID observation -> UML structure -> AUTO policy
        |
        v
bounded internal capability / optional GPU draft
        |
        v
UML result -> AUTO egress -> RID provenance
        |
        v
Rust Security OUT
        |
        v
user, tool, memory, training evidence, or log
```

The GPU mouth never receives tool authority. A draft must return through the
CPU Triad and Security OUT before speech.

## Public interfaces

- `TriadEnvelope.build(...)` creates a versioned, payload-hashed request.
- `open_context(...)` performs Security IN plus all three pillar checks.
- `authorize_operation(...)` authorizes a bounded internal or external action.
- `dispatch(...)` authorizes, executes, and receipts one handler.
- `emit(...)` performs the three-pillar return path and Security OUT.
- `verify_triad_ledger()` verifies the receipt hash chain.
- `EngineeringSpec` declares an externally authorized mutation.
- `begin_transaction(...)` inventories scope and creates a verified backup.
- `reconcile_transaction(...)` detects unexpected changes, records test
  evidence, classifies failures, and appends the session journal.

Contexts are process-local, expiring, and authenticity-bound. Stale, forged,
version-mismatched, malformed, or low-S_n contexts fail closed.

## Architecture enforcement

`triad_boundary_registry.json` is the frozen inventory of existing raw
filesystem, process, and network sites. Unified preflight fails if:

- a Python package is not bound to the Triad contract;
- a runtime module bypasses the membrane and imports `security_bridge`;
- the boundary registry drifts;
- a package contract, pillar version, or configuration version disagrees.

The registry makes existing migration debt explicit; it is not permission for
new boundary sites. Critical live paths now use the Triad directly:

- Architect inbox input;
- agentic artifact writes;
- CARMA writes;
- training request/reply records;
- GPU/deterministic voice generation and final egress.

Security bootstrap modules and deterministic security tests are the only
direct-bridge exceptions.

## Engineering transaction

Every future code, configuration, curriculum, training, or deployment change
uses:

```text
discover -> backup -> preflight -> authorize -> execute -> verify
         -> reconcile -> journal
```

The Governor does not let Viv rewrite protected source. Rust continues to block
self-modification. The Governor records external Architect/engineer changes
without weakening the constitutional boundary.

## Commands

```powershell
cd L:\Continue\Viv\foundation
$PY = "L:\Continue\.venv\Scripts\python.exe"

& $PY aios_main.py triad status
& $PY aios_main.py triad verify
& $PY aios_main.py triad architecture
& $PY aios_main.py governor
& $PY scripts\test_triad_kernel_contracts.py
& $PY scripts\test_triad_architecture.py
& $PY scripts\run_foundation_preflight.py
```

## Evidence

- `artifacts/auto/triad/milestone_report_v1.json`
- `artifacts/auto/triad/MILESTONE.md`
- `artifacts/auto/triad/triad_receipts.jsonl`
- `artifacts/auto/engineering_governor/transactions/`
- `artifacts/audit/session_journal.md`

Training and deployment are outside this milestone. Qwen remains the live
mouth, `validated_candidate` remains null, and `auto_deploy` remains false.
